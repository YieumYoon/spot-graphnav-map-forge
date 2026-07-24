(() => {
  "use strict";

  const model = globalThis.OrbitSiteMapEditorModel;
  if (!model) return;

  const KINDS = Object.freeze([
    "waypoint",
    "edge",
    "recording",
    "area",
    "dock",
    "fiducial",
    "action",
  ]);

  function text(value) {
    return String(value ?? "").trim().toLocaleLowerCase();
  }

  function tokens(value) {
    const result = [];
    const pattern = /(?:[^\s"]+|"[^"]*")+/g;
    for (const match of String(value || "").match(pattern) || []) {
      const normalized = match.startsWith('"') && match.endsWith('"')
        ? match.slice(1, -1)
        : match;
      if (normalized) result.push(normalized);
    }
    return result;
  }

  function parseQuery(value) {
    const predicates = [];
    const freeText = [];
    for (const token of tokens(value)) {
      const comparison = token.match(
        /^([a-zA-Z][\w-]*)(<=|>=|!=|=|<|>|:)(.*)$/,
      );
      if (!comparison) {
        freeText.push(token);
        continue;
      }
      const [, rawField, operator, rawValue] = comparison;
      predicates.push({
        field: rawField.toLocaleLowerCase(),
        operator,
        value: rawValue.replace(/^"(.*)"$/, "$1"),
      });
    }
    return { predicates, freeText };
  }

  function recordingRecords(snapshot) {
    return [...model.buildGraph(snapshot).recordingById.values()].map((recording) => ({
      kind: "recording",
      id: recording.id,
      name: recording.name || "",
      recordingId: recording.id,
      recordingName: recording.name || "",
      robot: recording.robotNickname || recording.robotSerial || "",
      waypointCount: recording.waypointCount,
      waypointIds: (snapshot?.waypoints || [])
        .filter((waypoint) => waypoint.recordingId === recording.id)
        .map((waypoint) => waypoint.id),
      edgeIds: [],
    }));
  }

  function universalRecords(snapshot) {
    const graph = model.buildGraph(snapshot || {});
    const result = [];
    for (const waypoint of snapshot?.waypoints || []) {
      result.push({
        kind: "waypoint",
        id: waypoint.id,
        name: waypoint.name || "",
        recordingId: waypoint.recordingId || "",
        recordingName: waypoint.recordingName || "",
        robot: waypoint.robotNickname || waypoint.robotSerial || "",
        degree: graph.neighbors.get(waypoint.id)?.size || 0,
        position: waypoint.position || null,
        status: waypoint.archived ? "archived" : waypoint.disabled ? "disabled" : "active",
        waypointIds: [waypoint.id],
        edgeIds: [],
        raw: waypoint,
      });
    }
    for (const edge of snapshot?.edges || []) {
      const from = graph.waypointById.get(edge.from);
      const to = graph.waypointById.get(edge.to);
      result.push({
        kind: "edge",
        id: edge.id || model.edgeKey(edge.from, edge.to),
        name:
          `${from?.name || model.shortId(edge.from)} ↔ ` +
          `${to?.name || model.shortId(edge.to)}`,
        source: edge.source || "unknown",
        manual: edge.manual ?? edge.source === "manual",
        crossRecording: Boolean(edge.crossRecording),
        recordingId:
          from?.recordingId === to?.recordingId ? from?.recordingId || "" : "",
        recordingName:
          from?.recordingId === to?.recordingId ? from?.recordingName || "" : "",
        settings: edge.settings || {},
        status: edge.archived ? "archived" : edge.disabled ? "disabled" : "active",
        length: edge.length,
        waypointIds: [edge.from, edge.to],
        edgeIds: [edge.id || model.edgeKey(edge.from, edge.to)],
        raw: edge,
      });
    }
    result.push(...recordingRecords(snapshot));
    for (const kind of ["area", "dock", "fiducial", "action"]) {
      const plural = `${kind}s`;
      for (const entity of snapshot?.[plural] || []) {
        result.push({
          kind,
          id: entity.id,
          name: entity.name || entity.displayName || "",
          recordingId: entity.recordingId || "",
          status: entity.catalogPresent === false
            ? "referenced-only"
            : entity.archived
              ? "archived"
              : entity.disabled
                ? "disabled"
                : "active",
          serviceName: entity.serviceName || "",
          entityType: entity.type || "",
          waypointIds: [...new Set([
            ...(entity.waypointIds || []),
            ...(entity.waypointId ? [entity.waypointId] : []),
          ])],
          edgeIds: [...new Set(entity.edgeIds || [])],
          position: entity.position || null,
          raw: entity,
        });
      }
    }
    return result;
  }

  function fieldValue(record, field) {
    const aliases = {
      type: "kind",
      recording: "recordingId",
      recordingname: "recordingName",
      "recording-name": "recordingName",
      crossrecording: "crossRecording",
      "cross-recording": "crossRecording",
      setting: "settings",
    };
    const key = aliases[field] || field;
    if (key === "settings") {
      return Object.entries(record.settings || {})
        .filter(([, value]) => Boolean(value))
        .map(([name]) => name);
    }
    return record[key] ?? record.raw?.[key];
  }

  function compare(actual, operator, expected) {
    if (Array.isArray(actual)) {
      return operator === "!="
        ? actual.every((item) => !compare(item, ":", expected))
        : actual.some((item) => compare(item, ":", expected));
    }
    if ([">", ">=", "<", "<="].includes(operator)) {
      const left = Number(actual);
      const right = Number(expected);
      if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
      if (operator === ">") return left > right;
      if (operator === ">=") return left >= right;
      if (operator === "<") return left < right;
      return left <= right;
    }
    const left = text(actual);
    const right = text(expected);
    if (operator === "=") return left === right;
    if (operator === "!=") return left !== right;
    return left.includes(right);
  }

  function recordText(record) {
    return text([
      record.kind,
      record.id,
      record.name,
      record.recordingId,
      record.recordingName,
      record.robot,
      record.source,
      record.status,
      record.serviceName,
      record.entityType,
      ...(record.waypointIds || []),
      ...(record.edgeIds || []),
      ...Object.keys(record.settings || {}),
    ].join(" "));
  }

  function matchesParsedQuery(record, parsed) {
    if (
      !parsed.predicates.every((predicate) =>
        compare(fieldValue(record, predicate.field), predicate.operator, predicate.value)
      )
    ) return false;
    const haystack = recordText(record);
    return parsed.freeText.every((value) => haystack.includes(text(value)));
  }

  function rankRecord(record, parsed) {
    const queryText = text(parsed.freeText.join(" "));
    if (!queryText) return 3;
    if (text(record.id) === queryText) return 0;
    if (text(record.name) === queryText) return 1;
    if (text(record.id).startsWith(queryText) || text(record.name).startsWith(queryText)) {
      return 2;
    }
    return 3;
  }

  function querySnapshot(
    snapshot,
    query,
    { kind = "all", limit = 250, sortBy = "rank", descending = false } = {},
  ) {
    const parsed = parseQuery(query);
    const kindFilter = kind === "all" ? "" : kind;
    const matches = universalRecords(snapshot)
      .filter((record) => !kindFilter || record.kind === kindFilter)
      .filter((record) => matchesParsedQuery(record, parsed))
      .map((record) => ({ ...record, rank: rankRecord(record, parsed) }));
    const direction = descending ? -1 : 1;
    matches.sort((left, right) => {
      const leftValue = sortBy === "rank" ? left.rank : left[sortBy];
      const rightValue = sortBy === "rank" ? right.rank : right[sortBy];
      const numeric = Number(leftValue) - Number(rightValue);
      if (
        Number.isFinite(Number(leftValue)) &&
        Number.isFinite(Number(rightValue)) &&
        numeric !== 0
      ) return numeric * direction;
      const lexical = String(leftValue ?? "").localeCompare(String(rightValue ?? ""));
      return lexical * direction ||
        left.kind.localeCompare(right.kind) ||
        left.id.localeCompare(right.id);
    });
    return matches.slice(0, Math.max(1, Math.min(5000, limit)));
  }

  globalThis.OrbitSiteMapEditorQuery = Object.freeze({
    KINDS,
    compare,
    matchesParsedQuery,
    parseQuery,
    querySnapshot,
    universalRecords,
  });
})();
