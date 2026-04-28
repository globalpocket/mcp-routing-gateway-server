# 📖 MCP Routing Gateway - ユーザーマニュアル

## 1. はじめに

**MCP Routing Gateway** は、AIエージェント（Cline、Claude Desktop など）とバックエンドのインフラの複雑さを完全に分離するために設計された、ステートレスなルーターおよび **Pure Proxy（純粋なプロキシ）** です。

AIエージェントに対しては本ゲートウェイが「単一のインテリジェントなMCPサーバー」として振る舞います。公式SDKに基づき標準入出力（`stdio`）による通信を仲介し、背後にある複数のMCPサーバー群へルーティングを行うと同時に、AIが使用できるツールを厳格に管理・制御します。

## 2. 主な機能

* **ゼロ・ペイロード干渉 (Pure Proxy):** ツール呼び出し（`tools/call`）を転送する際、ルーティングのためにツール名のみを書き換えますが、IDや引数などのペイロードは一切変更せずに透過させます。
* **ツールのフィルタリングと仮想化 (Facade Pattern):** ブロックリストを使用して特定のツールをAIから完全に隠蔽したり、安全にラップされた「仮想ツール」を提供したりできます。
* **スマートな名前空間解決:** 複数のサーバー間でツール名が競合した場合、プレフィックス付きエイリアス（例: `serverA_read_file`）とベース名の両方を提供します。
* **公式プロトコル準拠:** バックエンドの起動からフロントエンドの通信まで、すべてMCP公式SDKで管理されるため、100%仕様に準拠した堅牢な動作を保証します。

## 3. インストール

本プロジェクトは Python 3.10 以上を必要とします。

```bash
# 1. 仮想環境の作成と有効化
python3 -m venv .venv
source .venv/bin/activate

# 2. パッケージのインストール
pip install -e .
```

## 4. 設定と反映

すべての設定は JSON 形式で完結します。
**設定ファイルを変更した場合は、MCP Routing Gatewayのプロセスを再起動（AIエージェント側の再起動など）することで新しい設定が読み込まれます。**

### ① `mcp_config.json` (バックエンド定義)

Gatewayが背後で起動・接続するMCPサーバー群（stdioプロセス）を定義します。公式のMCPクライアント設定と同じフォーマットです。

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

### ② `gateway_config.json` (ルーティング・フィルタ定義)

どのツールをAIに見せるか、どのサーバーに送るかを制御します。デフォルトは最小構成の `{"version": "0.2.1"}` です。以下は設定の記述例です。

```json
{
  "version": "0.2.1",
  "virtual_tools": {
    "safe_query": {
      "description": "読み取り専用でDBを照会します。",
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

## 5. 使い方

CLI を使用してゲートウェイを起動します。

```bash
# 標準的な起動 (カレントディレクトリのjsonを読み込む)
mcp-gateway --config gateway_config.json --mcp-config mcp_config.json
```

*注: ゲートウェイはAIエージェントと `stdio` で通信します。JSON-RPCのペイロードを汚染しないよう、ログはすべて `stderr` に出力されます。*

## 6. AIエージェントとの統合

Claude Desktop や Cline で本ゲートウェイを使用するには、設定ファイルに標準的な `stdio` MCPサーバーとして登録してください。

**設定例 (Claude Desktop):**

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
