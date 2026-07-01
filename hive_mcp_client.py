"""
蜂巢·灵壳 MCP客户端 v1.0
========================
Model Context Protocol (MCP) 客户端 — 连接外部工具服务器，无限扩展灵壳能力。

协议: JSON-RPC 2.0 over stdio
规范: https://spec.modelcontextprotocol.io/

用法:
  from agents.hive_mcp_client import MCPManager

  manager = MCPManager()
  manager.connect("filesystem", "npx", ["-y", "@modelcontextprotocol/server-filesystem", "/path"])
  tools = manager.list_all_tools()
  result = manager.call_tool("filesystem", "read_file", {"path": "/tmp/test.txt"})
"""

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any


class MCPClient:
    """单个MCP服务器连接"""

    def __init__(self, name: str, command: str, args: List[str] = None,
                 env: Dict[str, str] = None, timeout: int = 30):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.timeout = timeout
        self.process = None
        self.tools = []
        self._request_id = 0
        self._lock = threading.Lock()
        self._connected = False

    def connect(self) -> bool:
        """启动MCP服务器进程并完成握手"""
        try:
            import os
            full_env = os.environ.copy()
            full_env.update(self.env)

            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=full_env,
            )

            # 握手: initialize
            resp = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "hiveshell", "version": "3.0.0"}
            })

            if resp and "result" in resp:
                # 发送 initialized 通知
                self._send_notification("notifications/initialized", {})
                self._connected = True
                # 发现工具
                self._discover_tools()
                return True

            return False
        except FileNotFoundError:
            # 命令不存在（如 npx 未安装）
            return False
        except Exception as e:
            return False

    def _discover_tools(self):
        """发现服务器提供的工具"""
        resp = self._send_request("tools/list", {})
        if resp and "result" in resp:
            server_tools = resp["result"].get("tools", [])
            # 转换为灵壳工具格式，加上命名空间前缀
            for t in server_tools:
                mcp_tool = {
                    "type": "function",
                    "function": {
                        "name": f"mcp_{self.name}_{t['name']}",
                        "description": t.get("description", f"MCP工具: {t['name']}"),
                        "parameters": t.get("inputSchema", {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }),
                    },
                    "_mcp_server": self.name,
                    "_mcp_original_name": t["name"],
                }
                self.tools.append(mcp_tool)

    def _send_request(self, method: str, params: dict) -> Optional[dict]:
        """发送JSON-RPC请求并等待响应"""
        with self._lock:
            self._request_id += 1
            req_id = self._request_id

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }, ensure_ascii=False)

        try:
            if self.process and self.process.stdin:
                self.process.stdin.write(request + "\n")
                self.process.stdin.flush()
            else:
                return None
        except (BrokenPipeError, OSError):
            self._connected = False
            return None

        # 读取响应（单行JSON）
        try:
            if self.process and self.process.stdout:
                line = self.process.stdout.readline()
                if line:
                    return json.loads(line.strip())
        except Exception:
            pass

        return None

    def _send_notification(self, method: str, params: dict):
        """发送JSON-RPC通知（无需响应）"""
        notification = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }, ensure_ascii=False)

        try:
            if self.process and self.process.stdin:
                self.process.stdin.write(notification + "\n")
                self.process.stdin.flush()
        except Exception:
            pass

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用MCP工具"""
        resp = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        if resp is None:
            return json.dumps({"error": f"MCP服务器'{self.name}'无响应"}, ensure_ascii=False)

        if "error" in resp:
            return json.dumps({"error": resp["error"].get("message", str(resp["error"]))}, ensure_ascii=False)

        result = resp.get("result", {})
        content = result.get("content", [])

        # 提取文本内容
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)

        return "\n".join(texts) if texts else json.dumps(result, ensure_ascii=False)

    def is_connected(self) -> bool:
        """检查连接状态"""
        if not self._connected or not self.process:
            return False
        return self.process.poll() is None

    def disconnect(self):
        """断开连接"""
        if self.process:
            try:
                self.process.stdin.close()
                self.process.stdout.close()
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except:
                    pass
        self._connected = False


class MCPManager:
    """MCP管理器 — 管理多个MCP服务器连接"""

    def __init__(self, tool_executor=None):
        self.clients: Dict[str, MCPClient] = {}
        self.tool_executor = tool_executor

    def connect(self, name: str, command: str, args: List[str] = None,
                env: Dict[str, str] = None) -> bool:
        """连接MCP服务器"""
        client = MCPClient(name, command, args, env)
        if client.connect():
            self.clients[name] = client
            return True
        return False

    def disconnect(self, name: str):
        """断开指定服务器"""
        if name in self.clients:
            self.clients[name].disconnect()
            del self.clients[name]

    def disconnect_all(self):
        """断开所有连接"""
        for name in list(self.clients.keys()):
            self.disconnect(name)

    def list_all_tools(self) -> List[dict]:
        """列出所有MCP服务器的工具"""
        all_tools = []
        for client in self.clients.values():
            all_tools.extend(client.tools)
        return all_tools

    def call_tool(self, full_name: str, arguments: dict) -> str:
        """
        调用MCP工具。
        full_name格式: mcp_{server_name}_{tool_name}
        """
        # 解析工具名
        if not full_name.startswith("mcp_"):
            return json.dumps({"error": f"非MCP工具: {full_name}"}, ensure_ascii=False)

        parts = full_name.split("_", 2)  # ["mcp", "server", "tool_name"]
        if len(parts) < 3:
            return json.dumps({"error": f"无效MCP工具名: {full_name}"}, ensure_ascii=False)

        server_name = parts[1]
        original_name = parts[2]

        if server_name not in self.clients:
            return json.dumps({"error": f"MCP服务器'{server_name}'未连接"}, ensure_ascii=False)

        return self.clients[server_name].call_tool(original_name, arguments)

    def get_status(self) -> dict:
        """获取MCP连接状态"""
        servers = {}
        for name, client in self.clients.items():
            servers[name] = {
                "connected": client.is_connected(),
                "tools_count": len(client.tools),
                "tools": [t["function"]["name"] for t in client.tools],
            }
        return {
            "total_servers": len(self.clients),
            "total_tools": sum(len(c.tools) for c in self.clients.values()),
            "servers": servers,
        }


# ============================================================
# 已知可用的MCP服务器（自动发现）
# ============================================================
KNOWN_MCP_SERVERS = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        "description": "文件系统访问 — 需要指定根目录路径作为参数",
        "note": "需安装Node.js/npx",
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "description": "GitHub API访问 — 需要GITHUB_PERSONAL_ACCESS_TOKEN环境变量",
        "note": "需安装Node.js/npx",
    },
    "brave_search": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "description": "Brave搜索引擎 — 需要BRAVE_API_KEY环境变量",
        "note": "需安装Node.js/npx",
    },
    "sqlite": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sqlite"],
        "description": "SQLite数据库访问",
        "note": "需安装Node.js/npx",
    },
    "puppeteer": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "description": "浏览器自动化(Puppeteer)",
        "note": "需安装Node.js/npx",
    },
}
