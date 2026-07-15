from __future__ import annotations

import json
import re
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any

from bosdyn.api.graph_nav import map_pb2

from .geometry import WaypointCoordinate, connected_components, load_graph
from .planner import (
    create_plan,
    selection_dependency_waypoint_ids,
    selection_only_edge_keys,
)

MAX_REQUEST_BYTES = 1_000_000
ASSET_TYPES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/assets/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/assets/favicon.svg": ("favicon.svg", "image/svg+xml"),
}


def build_workspace_payload(workspace: Path) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    metadata = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    graph = load_graph(workspace / "graph")
    map_view = json.loads((workspace / "map_view.json").read_text(encoding="utf-8"))
    coordinates = {
        row["id"]: WaypointCoordinate(
            waypoint_id=row["id"],
            x=float(row["x"]),
            y=float(row["y"]),
            source=row["source"],
        )
        for row in map_view["waypoints"]
    }
    components = connected_components(graph)
    component_by_waypoint: dict[str, int] = {}
    for index, component in enumerate(components):
        for waypoint_id in component:
            component_by_waypoint[waypoint_id] = index

    action_rows = metadata["actions"]
    action_counts = Counter(action["waypoint_id"] for action in action_rows)
    edge_source_enum = map_pb2.Edge.Annotations.DESCRIPTOR.fields_by_name["edge_source"].enum_type
    edge_source_names = {value.number: value.name for value in edge_source_enum.values}
    selection_only_keys = selection_only_edge_keys(metadata)

    return {
        "site_map": metadata["site_map"],
        "counts": {
            **metadata["counts"],
            "components": len(components),
            "largest_component": len(components[0]) if components else 0,
            "unanchored_waypoints": sum(
                coordinate.source == "waypoint_tform_ko_unanchored"
                for coordinate in coordinates.values()
            ),
        },
        "component_sizes": [len(component) for component in components],
        "waypoints": [
            {
                "id": waypoint_id,
                "x": coordinate.x,
                "y": coordinate.y,
                "source": coordinate.source,
                "component": component_by_waypoint[waypoint_id],
                "actions": action_counts[waypoint_id],
            }
            for waypoint_id, coordinate in coordinates.items()
        ],
        "edges": [
            {
                "from": edge.id.from_waypoint,
                "to": edge.id.to_waypoint,
                "source": edge_source_names.get(
                    edge.annotations.edge_source, str(edge.annotations.edge_source)
                ),
                "transport": (
                    "selection_only"
                    if (edge.id.from_waypoint, edge.id.to_waypoint) in selection_only_keys
                    else "walk"
                ),
            }
            for edge in graph.edges
        ],
        "actions": [
            {
                "id": action["id"],
                "name": action["name"],
                "waypoint_id": action["waypoint_id"],
                "images": len(action["image_paths"]),
                "source": "site_element",
            }
            for action in action_rows
        ],
        "selection_dependency_waypoint_ids": sorted(selection_dependency_waypoint_ids(metadata)),
        "edge_transport": metadata.get("edge_transport", {}),
    }


def save_plan(workspace: Path, request: dict[str, Any]) -> tuple[Path, dict[str, object]]:
    zone_name = str(request.get("zone_name", "")).strip()
    if not zone_name or len(zone_name) > 80:
        raise ValueError("zone_name must contain 1 to 80 characters")
    raw_polygon = request.get("polygon")
    if not isinstance(raw_polygon, list) or not 3 <= len(raw_polygon) <= 500:
        raise ValueError("polygon must contain 3 to 500 [x, y] vertices")
    try:
        polygon = [(float(point[0]), float(point[1])) for point in raw_polygon]
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError("every polygon vertex must be [x, y]") from exc
    halo_hops = int(request.get("halo_hops", 1))
    if not 0 <= halo_hops <= 10:
        raise ValueError("halo_hops must be between 0 and 10")

    plan = create_plan(
        workspace=workspace,
        polygon=polygon,
        zone_name=zone_name,
        halo_hops=halo_hops,
        clone_halo_actions=bool(request.get("clone_halo_actions", False)),
        excluded_triggered_action_ids=request.get("excluded_triggered_action_ids", []),
        triggered_action_exclusion_reason=request.get("triggered_action_exclusion_reason"),
        exclude_unanchored_waypoints=bool(request.get("exclude_unanchored_waypoints", False)),
        exclude_dependency_free_components=bool(
            request.get("exclude_dependency_free_components", False)
        ),
        include_selection_only_edges=bool(request.get("include_selection_only_edges", False)),
    )
    plans_dir = workspace / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", zone_name.casefold()).strip("-") or "zone"
    path = plans_dir / f"{slug}.plan.json"
    if path.exists() and not bool(request.get("overwrite", False)):
        raise FileExistsError(f"plan already exists: {path.name}")
    path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path, plan


class EditorServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], workspace: Path):
        super().__init__(address, EditorRequestHandler)
        self.workspace = workspace.expanduser().resolve()
        self.workspace_payload = json.dumps(
            build_workspace_payload(self.workspace),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")


class EditorRequestHandler(BaseHTTPRequestHandler):
    server: EditorServer
    server_version = "MapForge"
    sys_version = ""

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/workspace":
            self._send(
                HTTPStatus.OK, self.server.workspace_payload, "application/json; charset=utf-8"
            )
            return
        asset = ASSET_TYPES.get(path)
        if asset is None:
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        name, content_type = asset
        payload = files("spot_graphnav_map_forge.web_assets").joinpath(name).read_bytes()
        self._send(HTTPStatus.OK, payload, content_type)

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/plans":
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
            return
        if not 0 < length <= MAX_REQUEST_BYTES:
            self._json_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body is too large")
            return
        try:
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise ValueError("request body must be a JSON object")
            path, plan = save_plan(self.server.workspace, request)
        except FileExistsError as exc:
            self._json_error(HTTPStatus.CONFLICT, str(exc))
            return
        except (json.JSONDecodeError, ValueError) as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        payload = json.dumps(
            {"path": str(path), "plan": plan}, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        self._send(HTTPStatus.CREATED, payload, "application/json; charset=utf-8")

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _json_error(self, status: HTTPStatus, message: str) -> None:
        payload = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self._send(status, payload, "application/json; charset=utf-8")

    def _send(self, status: HTTPStatus, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(payload)


def serve_editor(workspace: Path, host: str, port: int) -> None:
    server = EditorServer((host, port), workspace)
    actual_host, actual_port = server.server_address[:2]
    print(f"Map Forge editor: http://{actual_host}:{actual_port}")
    print("Press Ctrl-C to stop. No server import APIs are enabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
