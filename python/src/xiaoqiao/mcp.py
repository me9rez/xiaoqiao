"""MCP server configuration and tool construction.

Reads the ``mcpServers`` section from ``~/.xiaoqiao/settings.json`` and
constructs ``agent_framework`` MCP tool wrappers for each configured server.
"""

from __future__ import annotations

import logging
from typing import Any

from xiaoqiao.settings import Settings
from xiaoqiao.settings import load as load_settings
from xiaoqiao.settings import save as save_settings

logger = logging.getLogger(__name__)

# Built-in connectors with descriptions
BUILTIN_CONNECTORS: dict[str, dict[str, str]] = {
    "brave-search": {
        "description": "Brave Search API",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-brave-search",
    },
    "sqlite": {
        "description": "SQLite database operations",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-sqlite /path/to/database.db",
    },
    "puppeteer": {
        "description": "Browser automation",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-puppeteer",
    },
    "memory": {
        "description": "Memory storage",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-memory",
    },
    "github": {
        "description": "GitHub API integration",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-github",
    },
    "slack": {
        "description": "Slack integration",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-slack",
    },
    "fetch": {
        "description": "HTTP fetch",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-fetch",
    },
    "playwright": {
        "description": "Browser automation",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-playwright",
    },
    "notion": {
        "description": "Notion integration",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-notion",
    },
    "postgres": {
        "description": "PostgreSQL database",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-postgres",
    },
    "docker": {
        "description": "Docker management",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-docker",
    },
    "sentry": {
        "description": "Sentry integration",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-sentry",
    },
    "linear": {
        "description": "Linear project management",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-linear",
    },
    "chrome-devtools": {
        "description": "Chrome DevTools",
        "type": "stdio",
        "command": "npx",
        "args": "-y @modelcontextprotocol/server-chrome-devtools",
    },
    "abu-browser-bridge": {
        "description": "Abu browser bridge",
        "type": "stdio",
        "command": "npx",
        "args": "-y @anthropic/abu-browser-bridge",
    },
}


def format_mcp_tools_for_prompt(tools: list[Any]) -> str:
    """Format registered MCP tools for inclusion in the system prompt.

    This helps the model understand which MCP servers are available and when
    to use them.
    """
    if not tools:
        return ""

    lines = [
        "## Available MCP Servers",
        "",
        "The following external MCP servers are available. Their tools are listed below; "
        "use them when the user's request requires capabilities outside the local project "
        "(e.g. web search, external APIs).",
        "",
    ]
    for tool in tools:
        name = getattr(tool, "name", "unknown")
        description = getattr(tool, "description", "") or ""
        functions = getattr(tool, "functions", [])
        lines.append(f"- **{name}**: {description}")
        for func in functions:
            func_name = getattr(func, "name", "unknown")
            func_desc = getattr(func, "description", "")
            lines.append(f"  - `{func_name}`: {func_desc}")
        lines.append("")

    return "\n".join(lines)


def create_mcp_tools(settings: Settings) -> list[Any]:
    """Create MCP tool wrappers from settings.json ``mcpServers``.

    Example ``settings.json`` entries::

        {
          "mcpServers": {
            "filesystem": {
              "command": "npx",
              "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
            },
            "exa": {
              "type": "streamable-http",
              "url": "https://mcp.exa.ai/mcp"
            }
          }
        }

    Parameters
    ----------
    settings:
        Loaded settings object.

    Returns
    -------
    List of ``MCPTool`` instances ready to be passed to ``Agent(tools=...)``.
    """
    from agent_framework import MCPStdioTool, MCPStreamableHTTPTool

    tools: list[Any] = []
    servers = getattr(settings, "mcp_servers", None) or {}
    if not isinstance(servers, dict):
        logger.warning("mcpServers is not a dict, skipping MCP tool creation")
        return tools

    for name, config in servers.items():
        if not isinstance(config, dict):
            logger.warning("MCP server %s config is not a dict, skipping", name)
            continue

        server_type = config.get("type", "stdio")
        description = config.get("description") or f"MCP server: {name}"
        allowed_tools = config.get("allowedTools")

        try:
            if server_type == "streamable-http":
                url = config.get("url")
                if not url:
                    logger.warning("MCP server %s missing 'url', skipping", name)
                    continue
                tool = MCPStreamableHTTPTool(
                    name=name,
                    url=str(url),
                    description=description,
                    allowed_tools=list(allowed_tools) if allowed_tools else None,
                )
                logger.info("Registered MCP server: %s (type=streamable-http, url=%s)", name, url)
            else:
                command = config.get("command")
                if not command:
                    logger.warning("MCP server %s missing 'command', skipping", name)
                    continue
                args = config.get("args") or []
                env = config.get("env")
                tool = MCPStdioTool(
                    name=name,
                    command=str(command),
                    args=[str(a) for a in args],
                    env={str(k): str(v) for k, v in env.items()} if env else None,
                    description=description,
                    allowed_tools=list(allowed_tools) if allowed_tools else None,
                )
                logger.info("Registered MCP server: %s (type=stdio, command=%s)", name, command)
            tools.append(tool)
        except Exception as exc:
            logger.warning("Failed to create MCP tool %s: %s", name, exc)

    return tools


def list_connectors() -> list[dict[str, Any]]:
    """List all available connectors (builtin + configured).

    Returns
    -------
    List of connector info dicts.
    """
    settings = load_settings()
    configured = getattr(settings, "mcp_servers", None) or {}
    connectors: list[dict[str, Any]] = []

    # Add built-in connectors
    for name, info in BUILTIN_CONNECTORS.items():
        connectors.append(
            {
                "name": name,
                "description": info["description"],
                "installed": name in configured,
                "type": "builtin",
            }
        )

    # Add custom configured connectors (not in builtin list)
    for name, config in configured.items():
        if name not in BUILTIN_CONNECTORS:
            connectors.append(
                {
                    "name": name,
                    "description": config.get("description", f"MCP server: {name}"),
                    "installed": True,
                    "type": "custom",
                }
            )

    return connectors


def get_connector(name: str) -> dict[str, Any] | None:
    """Get connector detail including config.

    Parameters
    ----------
    name:
        Connector name.

    Returns
    -------
    Connector info dict with config, or None if not found.
    """
    settings = load_settings()
    configured = getattr(settings, "mcp_servers", None) or {}

    # Check builtin first
    if name in BUILTIN_CONNECTORS:
        info = BUILTIN_CONNECTORS[name]
        config = configured.get(
            name,
            {
                "type": info["type"],
                "command": info.get("command", ""),
                "args": info.get("args", "").split() if info.get("args") else [],
            },
        )
        return {
            "name": name,
            "description": info["description"],
            "installed": name in configured,
            "type": "builtin",
            "config": config,
        }

    # Check custom
    if name in configured:
        config = configured[name]
        return {
            "name": name,
            "description": config.get("description", f"MCP server: {name}"),
            "installed": True,
            "type": "custom",
            "config": config,
        }

    return None


def install_connector(name: str, config: dict[str, Any] | None = None) -> bool:
    """Install a connector by adding to settings.

    Parameters
    ----------
    name:
        Connector name.
    config:
        Custom config. If None, uses builtin default.

    Returns
    -------
    True if installed successfully.
    """
    settings = load_settings()
    if settings.mcp_servers is None:
        settings.mcp_servers = {}

    if config is None and name in BUILTIN_CONNECTORS:
        builtin = BUILTIN_CONNECTORS[name]
        config = {
            "type": builtin.get("type", "stdio"),
            "command": builtin.get("command", ""),
            "args": builtin.get("args", "").split() if builtin.get("args") else [],
        }
    elif config is None:
        return False

    settings.mcp_servers[name] = config
    save_settings(settings)
    return True


def uninstall_connector(name: str) -> bool:
    """Uninstall a connector by removing from settings.

    Parameters
    ----------
    name:
        Connector name.

    Returns
    -------
    True if uninstalled, False if not found.
    """
    settings = load_settings()
    if settings.mcp_servers and name in settings.mcp_servers:
        del settings.mcp_servers[name]
        save_settings(settings)
        return True
    return False


def update_connector_config(name: str, config: dict[str, Any]) -> bool:
    """Update a connector's configuration.

    Parameters
    ----------
    name:
        Connector name.
    config:
        New configuration.

    Returns
    -------
    True if updated, False if not found.
    """
    settings = load_settings()
    if settings.mcp_servers is None:
        settings.mcp_servers = {}

    settings.mcp_servers[name] = config
    save_settings(settings)
    return True
