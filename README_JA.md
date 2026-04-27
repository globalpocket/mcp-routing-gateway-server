# MCP Routing Gateway

MCP Routing Gateway は、現在主流のAIエージェント（Claude Desktop, Cline 等）が抱えている**「LLMがユーザーの意図しないツール選択をしてしまう問題」を解決するため**に設計された、ステートレスなルーターおよび Pure Proxy（純粋なプロキシ）です。

## 🌟 存在意義 (Why MCP Routing Gateway?)

標準的なAIエージェントに直接複数のMCPサーバーを登録すると、LLMはすべてのツールを自由に閲覧・実行できてしまい、予期せぬ破壊的操作や不要なツールの呼び出しを引き起こすリスクがあります。

当プロジェクトは、AIエージェントと実際のMCPサーバー群の間に立ち、通信を仲介することで、**「安全にキュレーション（フィルタリング・仮想化）されたツールのみをLLMに提示する」**というコントロール層を提供します。

## 🏗️ アーキテクチャ (Architecture)

当プロジェクトは内部に「MCP Server」と「MCP Client」の両方の機能を備えています。

```text
AI Agent (MCP Client) → | [MCP Server] Gateway [MCP Client] | → Backend MCP Servers
```

1. **フロントエンド (MCP Server):** AIエージェントに対して「単一の安全なMCPサーバー」として振る舞い、標準入出力 (`stdio`) で接続を受け付けます。
2. **バックエンド (MCP Client):** `mcp_config.json` を読み込み、そこに定義された複数のMCPサーバー（`stdio` 起動プロセスや `SSE` 接続）を自動で起動・管理します。

## 🎯 設計思想 (Design Philosophy)

本プロジェクトは**「Router であり Pure Proxy」**であるという厳格な思想に基づいています。

1. **基本はパススルー (Zero Payload Interference)**
   リクエストのIDや引数などのペイロードには一切干渉しません。通信の中継に徹し、純粋なパイプとして機能します。
2. **フィルタリングとツールの上書き (Facade Pattern)**
   Gatewayが介入するのは `tools/list`（ツール一覧の提示）と `tools/call`（ツールの呼び出し）のルーティングのみです。設定ファイルに基づき、危険なツールの隠蔽や、安全な仮想ツールへの置き換えを行います。

## ⚙️ 設定 (Configuration)

すべての設定は JSON 形式で完結します。

1. **`mcp_config.json` (バックエンド定義):**
   標準的なMCPクライアントの設定ファイルフォーマットです。Gatewayが背後で接続・起動するMCPサーバー群を定義します。
2. **`gateway_config.json` (ルーティング・フィルタ定義):**
   Gateway独自のルール設定ファイルです。「どのツールを隠蔽するか（Blocked Tools）」「どのツールを仮想化するか（Virtual Tools）」を定義します。
