"""Unit tests for MCP tool construction (server definitions live in ``mcp.json``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao.mcp import create_mcp_tools
from xiaoqiao.mcp_config import save_mcp_servers


@pytest.fixture
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``XIAOQIAO_HOME`` at a temp dir so ``mcp.json`` is hermetic."""
    monkeypatch.setenv("XIAOQIAO_HOME", str(tmp_path))
    return tmp_path


class TestCreateMcpTools:
    def test_empty_mcp_servers(self, state_home: Path) -> None:
        assert create_mcp_tools() == []

    def test_stdio_mcp_server(self, state_home: Path) -> None:
        save_mcp_servers(
            {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                    "env": {"FOO": "bar"},
                    "description": "Filesystem access",
                }
            }
        )
        tools = create_mcp_tools()
        assert len(tools) == 1
        from agent_framework._mcp import MCPStdioTool

        assert isinstance(tools[0], MCPStdioTool)
        assert tools[0].name == "filesystem"
        assert tools[0].command == "npx"
        assert tools[0].args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert tools[0].env == {"FOO": "bar"}

    def test_streamable_http_mcp_server(self, state_home: Path) -> None:
        save_mcp_servers({"exa": {"url": "https://mcp.exa.ai/mcp", "description": "Exa web search"}})
        tools = create_mcp_tools()
        assert len(tools) == 1
        from agent_framework._mcp import MCPStreamableHTTPTool

        assert isinstance(tools[0], MCPStreamableHTTPTool)
        assert tools[0].name == "exa"
        assert tools[0].url == "https://mcp.exa.ai/mcp"

    def test_legacy_type_key_is_still_understood(self, state_home: Path) -> None:
        """A hand-written ``type = "streamable-http"`` entry keeps working."""
        save_mcp_servers({"legacy": {"type": "streamable-http", "url": "https://example.com/mcp"}})
        tools = create_mcp_tools()
        assert len(tools) == 1
        assert tools[0].url == "https://example.com/mcp"

    def test_invalid_mcp_config_is_skipped(self, state_home: Path) -> None:
        save_mcp_servers(
            {
                "bad_stdio": {"args": ["only-args"]},  # missing command
                "bad_http": {"transport": "streamable-http"},  # missing url
            }
        )
        assert create_mcp_tools() == []
