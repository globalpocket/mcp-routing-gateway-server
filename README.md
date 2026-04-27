# MCP Routing Gateway

MCP Routing Gateway is a pure, stateless routing proxy and facade layer designed to completely decouple AI agents (like Cline, Brownie, etc.) from underlying infrastructure complexity. 

It acts as a **"Single, Intelligent MCP Server"**, curating exactly what tools the AI agent can see and use, while transparently multiplexing standard `stdio` communication to multiple backend MCP servers via HTTP/SSE.

## 🌟 Why MCP Routing Gateway?
When connecting AI agents to real-world infrastructure, you don't want to expose raw, potentially dangerous backend tools directly. Furthermore, you want the LLM to focus purely on reasoning, completely unaware of routing, session management, or container IDs.

MCP Routing Gateway solves this by allowing you to **filter backend tools** and provide securely wrapped **"Virtual Tools"**. The LLM interacts with a clean, curated list of tools via standard `stdio`, while the Gateway acts as a pure conduit—handling the messy reality of HTTP/SSE multiplexing, routing, and namespace conflicts in the background without interfering with the payload.

## 🏗️ Architecture & Core Features

### 1. Tool Filtering & Virtualization (Facade Pattern)
- **Virtual Tools:** Define custom, abstract tools in `gateway_config.yaml` that map to specific backend routes (e.g., exposing a safe `run_command` that secretly routes to an isolated, ephemeral sandbox).
- **Explicit Filtering:** Pass-through only the tools you want. Hide or intercept tools from backend servers to prevent the AI from accessing unnecessary or dangerous capabilities.

### 2. Smart Registry & Hybrid Namespace Resolution
- **Dynamic Discovery:** Automatically fetches tool lists from newly provisioned backend servers.
- **Hybrid Namespace Management:** Prevents collisions by providing both **Namespaced Aliases** (e.g., `serverA_read_file`) and **Base Names** (e.g., `read_file`).
- **Deterministic Routing:** Base names are resolved using an implicit "Last-Write-Wins" policy, but can be strictly locked to a specific server using static routing overrides in `gateway_config.yaml` (Highest Priority).

### 3. Dual-Plane Architecture & Full-Duplex Multiplexer
- **Data Plane (Agent Interface):** A pure `stdio` to `HTTP/SSE` multiplexer. It performs **Zero Payload Interference**. It only rewrites the tool name for routing and seamlessly bypasses the exact JSON-RPC payloads (including IDs). It also maintains persistent SSE streams, allowing transparent reverse-requests (e.g., `sampling`) from the backend to the LLM.
- **Control Plane (Admin Interface):** Provides a REST API for orchestration workflows to dynamically provision or tear down backend routes without restarting the gateway. The Gateway remains completely stateless, pushing all infrastructure state (like container IDs) to the external routing layer (e.g., Reverse Proxy, L7 Load Balancer).
