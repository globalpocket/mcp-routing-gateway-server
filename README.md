# MCP Routing Gateway

The MCP Routing Gateway is a stateless router and Pure Proxy designed to **solve the problem of "LLMs selecting tools unintended by the user,"** which is a common issue faced by current mainstream AI agents (e.g., Claude Desktop, Cline).

## 🌟 Why MCP Routing Gateway?

When multiple MCP servers are registered directly to a standard AI agent, the LLM can freely browse and execute all tools, posing the risk of triggering unexpected destructive operations or unnecessary tool calls.

This project sits between the AI agent and the actual group of MCP servers, mediating the communication to provide a control layer that **"presents only safely curated (filtered and virtualized) tools to the LLM."**

## 🏗️ Architecture

This project incorporates both "MCP Server" and "MCP Client" functionalities internally.

```text
AI Agent (MCP Client) → | [MCP Server] Gateway [MCP Client] | → Backend MCP Servers
```

1. **Frontend (MCP Server):** Acts as a "single, secure MCP server" to the AI agent, accepting connections via standard input/output (`stdio`).
2. **Backend (MCP Client):** Reads `mcp_config.json` and automatically launches and manages multiple MCP servers defined within it (via `stdio` spawned processes).

## 🎯 Design Philosophy

This project is built on the strict philosophy of being a **"Router and Pure Proxy."**

1. **Zero Payload Interference (Pass-through):**
   It does not interfere with payloads such as request IDs or arguments. It focuses entirely on relaying communication, functioning as a pure pipe.
2. **Facade Pattern (Filtering and Tool Overrides):**
   The Gateway only intervenes in the routing of `tools/list` (presenting the tool list) and `tools/call` (tool invocation). Based on the configuration file, it hides dangerous tools or replaces them with secure virtual tools.

## ⚙️ Configuration

All configurations are entirely managed in JSON format.

1. **`mcp_config.json` (Backend Definition):**
   The standard configuration file format for MCP clients. It defines the group of MCP servers that the Gateway connects to and launches in the background.
2. **`gateway_config.json` (Routing and Filter Definition):**
   A rule configuration file unique to the Gateway. It defines "which tools to hide (Blocked Tools)" and "which tools to virtualize (Virtual Tools)."
