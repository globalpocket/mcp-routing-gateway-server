# 📖 MCP Routing Gateway - User Manual

## 1. Introduction

**MCP Routing Gateway** is a stateless router and **Pure Proxy** designed to completely decouple AI agents (such as Cline, Claude Desktop, etc.) from the complexity of the underlying infrastructure.

Acting as a "single, secure MCP server" to the AI agent, it aggregates multiple backend MCP servers and presents only safely curated (filtered and virtualized) tools to the LLM.

## 2. Key Features

* **Zero Payload Interference (Pure Proxy):** Functions as a pure pipe, relaying communication without modifying request IDs or arguments.
* **Tool Filtering and Virtualization (Facade Pattern):** Hide dangerous tools (Blocked Tools) or provide safe wrappers (Virtual Tools) via configuration.
* **Smart Namespace Resolution:** Handles tool name conflicts by providing both prefixed aliases (e.g., `serverA_read_file`) and base names.
* **Official Protocol Compliance:** Built with the official MCP SDK, ensuring 100% specification compliance and stable communication.

## 3. Installation

This project requires Python 3.10 or higher.

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install the package
pip install -e .
```

## 4. Configuration and Reloading

All configurations are entirely managed in JSON format.
**To apply changes to configuration files, simply restart the MCP Routing Gateway process (e.g., by restarting the AI agent).**

### ① `mcp_config.json` (Backend Definition)

Defines the group of MCP servers (stdio processes) that the Gateway launches and connects to. This follows the standard MCP client configuration format.

```json
{
  "mcpServers": {
    "sqlite-server": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "test.db"]
    },
    "github-server": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"]
    }
  }
}
```

### ② `gateway_config.json` (Routing & Filter Definition)

Controls which tools are presented to the AI and how they are routed. The default file is a minimal `{ "version": "0.2.0" }`. The following is an **example** of how to define advanced rules:

```json
{
  "version": "0.2.0",
  "virtual_tools": {
    "safe_query": {
      "description": "Query the database in read-only mode.",
      "target_server": "sqlite-server"
    }
  },
  "explicit_routing": {
    "read_file": "github-server"
  },
  "blocked_tools": [
    "sqlite-server_drop_table",
    "github-server_delete_repo"
  ]
}
```

## 5. Usage

Start the gateway using the CLI.

```bash
# Basic startup (loading JSON configs from current directory)
mcp-gateway --config gateway_config.json --mcp-config mcp_config.json
```

*Note: The gateway communicates with the AI agent via `stdio`. All logs are output to `stderr` to avoid polluting the JSON-RPC payload.*

## 6. AI Agent Integration (Claude Desktop Example)

Register the gateway as a standard `stdio` MCP server in your configuration file.

```json
{
  "mcpServers": {
    "mcp-routing-gateway": {
      "command": "mcp-gateway",
      "args": [
        "--config", "/absolute/path/to/gateway_config.json",
        "--mcp-config", "/absolute/path/to/mcp_config.json"
      ]
    }
  }
}
```
