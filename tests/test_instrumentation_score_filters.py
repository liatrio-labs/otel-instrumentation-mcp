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

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client

from otel_instrumentation_mcp.main import mcp


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args, expected",
    [
        (
            {"rule_ids": "RES-001,SPA-001"},
            {"rule_ids": ["RES-001", "SPA-001"]},
        ),
        (
            {"rule_ids": "RES-001, SPA-001"},
            {"rule_ids": ["RES-001", "SPA-001"]},
        ),
        (
            {"impact_levels": " Critical ,Important, "},
            {"impact_levels": ["Critical", "Important"]},
        ),
        (
            {"targets": "Resource,  Span"},
            {"targets": ["Resource", "Span"]},
        ),
        (
            {"rule_ids": " , "},
            {"rule_ids": None},
        ),
    ],
)
async def test_filters_are_trimmed(args, expected):
    """Comma-separated filters ignore whitespace and empty entries (#23)."""
    fetch = AsyncMock(
        return_value={
            "rules": {},
            "metadata": {"fetched": 0, "filtered_out": 0, "total_available": 0},
        }
    )
    with patch(
        "otel_instrumentation_mcp.main.fetch_instrumentation_score_rules", fetch
    ):
        async with Client(mcp) as client:
            await client.call_tool("get_instrumentation_score_rules", args)

    called = {"rule_ids": None, "impact_levels": None, "targets": None}
    called.update(expected)
    fetch.assert_awaited_once_with(**called)
