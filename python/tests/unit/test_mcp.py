"""Unit tests for MCP tool construction."""

from __future__ import annotations

from xiaoqiao.mcp import create_mcp_tools
from xiaoqiao.settings import Settings


class TestCreateMcpTools:
    def test_empty_mcp_servers(self) -> None:
        settings = Settings()
        assert create_mcp_tools(settings) == []

    def test_stdio_mcp_server(self) -> None:
        settings = Settings()
        settings.mcp_servers = {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "env": {"FOO": "bar"},
                "description": "Filesystem access",
            }
        }
        tools = create_mcp_tools(settings)
        assert len(tools) == 1
        from agent_framework._mcp import MCPStdioTool

        assert isinstance(tools[0], MCPStdioTool)
        assert tools[0].name == "filesystem"
        assert tools[0].command == "npx"
        assert tools[0].args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert tools[0].env == {"FOO": "bar"}

    def test_streamable_http_mcp_server(self) -> None:
        settings = Settings()
        settings.mcp_servers = {
            "exa": {
                "type": "streamable-http",
                "url": "https://mcp.exa.ai/mcp",
                "description": "Exa web search",
            }
        }
        tools = create_mcp_tools(settings)
        assert len(tools) == 1
        from agent_framework._mcp import MCPStreamableHTTPTool

        assert isinstance(tools[0], MCPStreamableHTTPTool)
        assert tools[0].name == "exa"
        assert tools[0].url == "https://mcp.exa.ai/mcp"

    def test_invalid_mcp_config_is_skipped(self) -> None:
        settings = Settings()
        settings.mcp_servers = {
            "bad_stdio": {"args": ["only-args"]},  # missing command
            "bad_http": {"type": "streamable-http"},  # missing url
        }
        assert create_mcp_tools(settings) == []
