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
from fastmcp import Client
from pydantic import TypeAdapter

from otel_instrumentation_mcp.main import mcp


@pytest.mark.asyncio
async def test_null_default_parameters_accept_null():
    """Every tool parameter that advertises "default": null must accept null.

    Only the schemas and argument types are checked; no tool is called.
    """
    async with Client(mcp) as client:
        tools = await client.list_tools()

    registered = await mcp.get_tools()
    checked = []
    for tool in tools:
        params = inspect.signature(registered[tool.name].fn).parameters
        for name, prop in tool.inputSchema.get("properties", {}).items():
            if "default" not in prop or prop["default"] is not None:
                continue
            checked.append(f"{tool.name}.{name}")
            types = [prop.get("type")] + [o.get("type") for o in prop.get("anyOf", [])]
            assert (
                "null" in types
            ), f"{tool.name}.{name} defaults to null but rejects it"
            TypeAdapter(params[name].annotation).validate_python(None)

    assert checked, "expected at least one parameter with a null default"
