import pytest
import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.asyncio
async def test_list_opentelemetry_repos_tool():
    """Test the list_opentelemetry_repos MCP tool."""
    server_params = StdioServerParameters(
        command="uv", args=["run", "python", "-m", "otel_instrumentation_mcp.main"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            assert "list_opentelemetry_repos" in tool_names

            # Call the list_opentelemetry_repos tool
            result = await session.call_tool("list_opentelemetry_repos", {})
            assert "repositories" in str(result.content)


@pytest.mark.asyncio
async def test_list_opentelemetry_issues_tool():
    """Test the list_opentelemetry_issues MCP tool."""
    server_params = StdioServerParameters(
        command="uv", args=["run", "python", "-m", "otel_instrumentation_mcp.main"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Call the list_opentelemetry_issues tool
            result = await session.call_tool(
                "list_opentelemetry_issues", {"repo": "opentelemetry-python"}
            )
            content = str(result.content)
            assert "issues" in content


@pytest.mark.asyncio
async def test_get_opentelemetry_examples_tool():
    """Test the get_opentelemetry_examples MCP tool."""
    server_params = StdioServerParameters(
        command="uv", args=["run", "python", "-m", "otel_instrumentation_mcp.main"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Call the get_opentelemetry_examples tool
            result = await session.call_tool("get_opentelemetry_examples", {})
            content = str(result.content)
            assert "examples" in content


@pytest.mark.asyncio
async def test_get_semantic_conventions_tool():
    """Test the get_semantic_conventions MCP tool."""
    server_params = StdioServerParameters(
        command="uv", args=["run", "python", "-m", "otel_instrumentation_mcp.main"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools to ensure our new tool is registered
            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            assert "get_semantic_conventions" in tool_names

            # Call the get_semantic_conventions tool with default parameters
            result = await session.call_tool("get_semantic_conventions", {})
            content = str(result.content)
            assert "conventions" in content

            # Test with category filter
            result = await session.call_tool(
                "get_semantic_conventions",
                {"category": "http", "count": 10},
            )
            content = str(result.content)
            assert "conventions" in content


@pytest.mark.asyncio
async def test_get_instrumentation_score_spec_tool():
    """Test the get_instrumentation_score_spec MCP tool."""
    server_params = StdioServerParameters(
        command="uv", args=["run", "python", "-m", "otel_instrumentation_mcp.main"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools to ensure our new tool is registered
            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            assert "get_instrumentation_score_spec" in tool_names

            # Call the get_instrumentation_score_spec tool
            result = await session.call_tool("get_instrumentation_score_spec", {})
            content = str(result.content)
            assert "specification" in content
            # Check for key content from the specification
            assert "Instrumentation Score" in content
            assert "OpenTelemetry" in content


@pytest.mark.asyncio
async def test_get_instrumentation_score_rules_tool():
    """Test the get_instrumentation_score_rules MCP tool."""
    server_params = StdioServerParameters(
        command="uv", args=["run", "python", "-m", "otel_instrumentation_mcp.main"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools to ensure our new tool is registered
            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            assert "get_instrumentation_score_rules" in tool_names

            # Call the get_instrumentation_score_rules tool with no filters
            result = await session.call_tool("get_instrumentation_score_rules", {})
            content = str(result.content)
            assert "rules" in content
            assert "metadata" in content

            # Test with specific rule ID filter
            result = await session.call_tool(
                "get_instrumentation_score_rules",
                {"rule_ids": "RES-001"},
            )
            content = str(result.content)
            assert "rules" in content
            assert "RES-001" in content

            # Test with impact level filter
            result = await session.call_tool(
                "get_instrumentation_score_rules",
                {"impact_levels": "Critical"},
            )
            content = str(result.content)
            assert "rules" in content

            # Test with target filter
            result = await session.call_tool(
                "get_instrumentation_score_rules",
                {"targets": "Resource"},
            )
            content = str(result.content)
            assert "rules" in content
