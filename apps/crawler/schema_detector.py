import json

from bs4 import BeautifulSoup


def detect_schema_types(html: str) -> dict:
    soup = BeautifulSoup(html or "", "lxml")
    types_detected = set()
    schemas_raw = []

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for item in _flatten_schema(parsed):
            schema_type = item.get("@type")
            if isinstance(schema_type, list):
                types_detected.update(str(value) for value in schema_type)
            elif schema_type:
                types_detected.add(str(schema_type))
            schemas_raw.append(item)

    return {
        "types_detected": sorted(types_detected),
        "schemas_raw": schemas_raw,
    }


def _flatten_schema(parsed):
    if isinstance(parsed, list):
        for item in parsed:
            yield from _flatten_schema(item)
    elif isinstance(parsed, dict):
        graph = parsed.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _flatten_schema(item)
        else:
            yield parsed
