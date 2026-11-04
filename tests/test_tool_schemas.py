# Copyright 2025 Liatrio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import inspect

import pytest
from pydantic import TypeAdapter

from otel_instrumentation_mcp.main import mcp


def schema_accepts_null(prop: dict) -> bool:
    """Whether a JSON schema property allows null.

    Handles both `"type": "null"` / `"type": ["string", "null"]` and
    `anyOf` / `oneOf` members.
    """
    types = prop.get("type")
    if types == "null" or (isinstance(types, list) and "null" in types):
        return True
    members = prop.get("anyOf", []) + prop.get("oneOf", [])
    return any(schema_accepts_null(member) for member in members)


@pytest.mark.parametrize(
    "prop, expected",
    [
        ({"anyOf": [{"type": "string"}, {"type": "null"}]}, True),
        ({"type": ["string", "null"]}, True),
        ({"oneOf": [{"type": "integer"}, {"type": "null"}]}, True),
        ({"type": "string"}, False),
        ({"anyOf": [{"type": "string"}, {"type": "integer"}]}, False),
    ],
)
def test_schema_accepts_null(prop, expected):
    assert schema_accepts_null(prop) is expected


@pytest.mark.asyncio
async def test_none_default_parameters_accept_null():
    """Every tool parameter that defaults to None must accept null.

    Driven by the Python signatures rather than the generated schema, so a
    parameter is checked even if its schema omits `"default": null`.
    Only the schemas and argument types are checked; no tool is called.
    """
    checked = []
    for name, tool in (await mcp.get_tools()).items():
        properties = tool.parameters.get("properties", {})
        for param in inspect.signature(tool.fn).parameters.values():
            if param.default is not None:
                continue
            checked.append(f"{name}.{param.name}")
            assert schema_accepts_null(
                properties[param.name]
            ), f"{name}.{param.name} defaults to None but its schema rejects null"
            TypeAdapter(param.annotation).validate_python(None)

    assert checked, "expected at least one parameter with a None default"
