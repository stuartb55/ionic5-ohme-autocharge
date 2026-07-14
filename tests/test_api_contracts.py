"""Keep the dashboard's TypeScript boundary aligned with FastAPI OpenAPI."""

from __future__ import annotations

import re
from pathlib import Path

import api


_FRONTEND_TYPES = Path(__file__).parents[1] / "frontend" / "src" / "api" / "types.ts"


def _typescript_interfaces(source: str) -> dict[str, tuple[list[str], set[str]]]:
    """Return direct parents and top-level properties for exported interfaces."""
    interfaces: dict[str, tuple[list[str], set[str]]] = {}
    pattern = re.compile(
        r"export\s+interface\s+(\w+)(?:\s+extends\s+([^\{]+))?\s*\{"
    )
    for match in pattern.finditer(source):
        depth = 1
        cursor = match.end()
        while depth and cursor < len(source):
            if source[cursor] == "{":
                depth += 1
            elif source[cursor] == "}":
                depth -= 1
            cursor += 1
        body = source[match.end() : cursor - 1]
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
        body = re.sub(r"//.*", "", body)
        properties: set[str] = set()
        nested = 0
        for line in body.splitlines():
            if nested == 0:
                field = re.match(r"\s*(\w+)\??\s*:", line)
                if field:
                    properties.add(field.group(1))
            nested += line.count("{") - line.count("}")
        parents = [part.strip() for part in (match.group(2) or "").split(",") if part.strip()]
        interfaces[match.group(1)] = (parents, properties)
    return interfaces


def _all_typescript_properties(
    name: str, interfaces: dict[str, tuple[list[str], set[str]]]
) -> set[str]:
    parents, direct = interfaces[name]
    return direct | set().union(
        *(_all_typescript_properties(parent, interfaces) for parent in parents)
    )


def test_frontend_top_level_contracts_match_openapi():
    """Catch API fields added, removed, or renamed on either side of the SPA boundary."""
    source = _FRONTEND_TYPES.read_text()
    interfaces = _typescript_interfaces(source)
    schemas = api.app.openapi()["components"]["schemas"]
    pairs = {
        "StatusResponseModel": "StatusResponse",
        "ScheduleResponseModel": "ScheduleResponse",
        "SessionsResponseModel": "SessionsResponse",
        "VehiclesResponseModel": "VehiclesResponse",
        "TargetUpdateResponseModel": "TargetUpdateResponse",
        "ReadyByUpdateResponseModel": "ReadyByUpdateResponse",
        "DayTargetsUpdateResponseModel": "DayTargetsUpdateResponse",
        "TripModeUpdateResponseModel": "TripModeUpdateResponse",
        "NotificationPreferencesUpdateResponseModel": (
            "NotificationPreferencesUpdateResponse"
        ),
        "VehicleUpdateResponseModel": "VehicleUpdateResponse",
        "VehicleProfileUpdateResponseModel": "VehicleProfileUpdateResponse",
        "ChargeActionResponseModel": "ChargeActionResponse",
        "RefreshResponseModel": "RefreshResponse",
    }

    for schema_name, interface_name in pairs.items():
        openapi_fields = set(schemas[schema_name]["properties"])
        frontend_fields = _all_typescript_properties(interface_name, interfaces)
        assert frontend_fields == openapi_fields, schema_name


def test_core_routes_publish_typed_openapi_responses():
    schema = api.app.openapi()
    expected = {
        "/api/status": "StatusResponseModel",
        "/api/schedule": "ScheduleResponseModel",
        "/api/sessions": "SessionsResponseModel",
        "/api/vehicles": "VehiclesResponseModel",
        "/api/settings/target": "TargetUpdateResponseModel",
    }
    for path, model in expected.items():
        operation = "get" if path in {
            "/api/status",
            "/api/schedule",
            "/api/sessions",
            "/api/vehicles",
        } else "put"
        response_schema = schema["paths"][path][operation]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema == {"$ref": f"#/components/schemas/{model}"}
