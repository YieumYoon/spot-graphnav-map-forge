from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from bosdyn.api.graph_nav import map_pb2

Point = tuple[float, float]


@dataclass(frozen=True)
class WaypointCoordinate:
    waypoint_id: str
    x: float
    y: float
    source: str


@dataclass(frozen=True)
class Pose:
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]  # x, y, z, w


def waypoint_coordinates(
    graph: map_pb2.Graph,
    *,
    direct_anchor_source: str = "graph_anchor",
    propagated_anchor_source: str = "propagated_graph_anchor",
) -> dict[str, WaypointCoordinate]:
    propagated = _propagate_anchor_poses(graph)
    direct_anchor_ids = {anchor.id for anchor in graph.anchoring.anchors}
    result: dict[str, WaypointCoordinate] = {}
    for waypoint in graph.waypoints:
        if waypoint.id in propagated:
            position = propagated[waypoint.id].position
            source = (
                direct_anchor_source
                if waypoint.id in direct_anchor_ids
                else propagated_anchor_source
            )
        else:
            ko_position = waypoint.waypoint_tform_ko.position
            position = (ko_position.x, ko_position.y, ko_position.z)
            source = "waypoint_tform_ko_unanchored"
        result[waypoint.id] = WaypointCoordinate(
            waypoint_id=waypoint.id,
            x=position[0],
            y=position[1],
            source=source,
        )
    return result


def point_in_polygon(point: Point, polygon: Iterable[Point]) -> bool:
    vertices = tuple(polygon)
    if len(vertices) < 3:
        raise ValueError("polygon needs at least three vertices")
    x, y = point
    inside = False
    previous = vertices[-1]
    for current in vertices:
        x1, y1 = previous
        x2, y2 = current
        if _on_segment(point, previous, current):
            return True
        crosses = (y1 > y) != (y2 > y)
        if crosses:
            intersection_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection_x:
                inside = not inside
        previous = current
    return inside


def select_core(graph: map_pb2.Graph, polygon: Iterable[Point]) -> set[str]:
    coordinates = waypoint_coordinates(graph)
    return {
        waypoint_id
        for waypoint_id, coordinate in coordinates.items()
        if point_in_polygon((coordinate.x, coordinate.y), polygon)
    }


def connectivity_halo(graph: map_pb2.Graph, core: set[str], hops: int) -> set[str]:
    if hops < 0:
        raise ValueError("halo hops cannot be negative")
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        source = edge.id.from_waypoint
        target = edge.id.to_waypoint
        adjacency[source].add(target)
        adjacency[target].add(source)
    distances: dict[str, int] = {waypoint_id: 0 for waypoint_id in core}
    queue: deque[str] = deque(core)
    while queue:
        waypoint_id = queue.popleft()
        distance = distances[waypoint_id]
        if distance >= hops:
            continue
        for neighbor in adjacency[waypoint_id]:
            if neighbor not in distances:
                distances[neighbor] = distance + 1
                queue.append(neighbor)
    return set(distances) - core


def connected_components(
    graph: map_pb2.Graph, waypoint_ids: set[str] | None = None
) -> list[set[str]]:
    selected = (
        {waypoint.id for waypoint in graph.waypoints} if waypoint_ids is None else set(waypoint_ids)
    )
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        source = edge.id.from_waypoint
        target = edge.id.to_waypoint
        if source in selected and target in selected:
            adjacency[source].add(target)
            adjacency[target].add(source)
    remaining = set(selected)
    components: list[set[str]] = []
    while remaining:
        root = next(iter(remaining))
        component = {root}
        queue: deque[str] = deque([root])
        remaining.remove(root)
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current] & remaining:
                remaining.remove(neighbor)
                component.add(neighbor)
                queue.append(neighbor)
        components.append(component)
    return sorted(components, key=len, reverse=True)


def _on_segment(point: Point, start: Point, end: Point, tolerance: float = 1e-9) -> bool:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > tolerance:
        return False
    return (
        min(x1, x2) - tolerance <= x <= max(x1, x2) + tolerance
        and min(y1, y2) - tolerance <= y <= max(y1, y2) + tolerance
    )


def load_graph(path: Any) -> map_pb2.Graph:
    graph = map_pb2.Graph()
    graph.ParseFromString(path.read_bytes())
    return graph


def _propagate_anchor_poses(graph: map_pb2.Graph) -> dict[str, Pose]:
    adjacency: dict[str, list[tuple[str, Pose]]] = defaultdict(list)
    for edge in graph.edges:
        source = edge.id.from_waypoint
        target = edge.id.to_waypoint
        transform = _pose_from_proto(edge.from_tform_to)
        adjacency[source].append((target, transform))
        adjacency[target].append((source, _inverse(transform)))

    poses: dict[str, Pose] = {}
    queue: deque[str] = deque()
    for anchor in graph.anchoring.anchors:
        if anchor.id in poses:
            continue
        poses[anchor.id] = _pose_from_proto(anchor.seed_tform_waypoint)
        queue.append(anchor.id)
    while queue:
        current = queue.popleft()
        for neighbor, current_tform_neighbor in adjacency[current]:
            if neighbor in poses:
                continue
            poses[neighbor] = _compose(poses[current], current_tform_neighbor)
            queue.append(neighbor)
    return poses


def _pose_from_proto(proto: Any) -> Pose:
    return Pose(
        position=(proto.position.x, proto.position.y, proto.position.z),
        rotation=(proto.rotation.x, proto.rotation.y, proto.rotation.z, proto.rotation.w),
    )


def _compose(left: Pose, right: Pose) -> Pose:
    rotated = _rotate(left.rotation, right.position)
    return Pose(
        position=tuple(left.position[index] + rotated[index] for index in range(3)),
        rotation=_normalize_quaternion(_multiply_quaternion(left.rotation, right.rotation)),
    )


def _inverse(pose: Pose) -> Pose:
    x, y, z, w = _normalize_quaternion(pose.rotation)
    inverse_rotation = (-x, -y, -z, w)
    inverse_position = _rotate(
        inverse_rotation,
        (-pose.position[0], -pose.position[1], -pose.position[2]),
    )
    return Pose(position=inverse_position, rotation=inverse_rotation)


def _multiply_quaternion(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def _rotate(
    rotation: tuple[float, float, float, float],
    point: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z, w = _normalize_quaternion(rotation)
    px, py, pz = point
    dot = x * px + y * py + z * pz
    cross_x = y * pz - z * py
    cross_y = z * px - x * pz
    cross_z = x * py - y * px
    scale = w * w - (x * x + y * y + z * z)
    return (
        2.0 * dot * x + scale * px + 2.0 * w * cross_x,
        2.0 * dot * y + scale * py + 2.0 * w * cross_y,
        2.0 * dot * z + scale * pz + 2.0 * w * cross_z,
    )


def _normalize_quaternion(
    rotation: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    norm = math.sqrt(sum(value * value for value in rotation))
    if norm < 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(value / norm for value in rotation)
