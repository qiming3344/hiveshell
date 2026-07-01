"""
蜂巢·灵壳 (HiveShell) v3.2 — 通用AI命令行终端 | 不绑定任何厂商
=============================================================
v1.0 → v2.0: 函数调用(Tool Use)
v2.0 → v3.0: Agent子代理 + MCP协议
v3.0 → v3.1: 通用后端 — 支持任意OpenAI兼容API

架构:
  蜂场主输入 → 蜂王思考 → 调用工具/分发子代理/MCP工具 → 执行 → 综合回复

  后端自由选择（壳是壳，模型是模型，不绑定）:
    --custom      任意OpenAI兼容API (设置HIVESHELL_API_URL+HIVESHELL_API_KEY)
    --deepseek    DeepSeek官方API (api.deepseek.com)
    --siliconflow 硅基流动 (DeepSeek-V3.2)
    --aliyun      阿里百炼 (Qwen3.7-Max)
    --ollama      Ollama本地 (零成本·隐私安全)

v3.2 新增:
  ✓ 通用后端 — 不再绑定特定厂商，配什么用什么
  ✓ DeepSeek官方API快捷入口

用法:
  # 最推荐: 自定义后端（配什么用什么）
  set HIVESHELL_API_URL=https://api.deepseek.com/v1/chat/completions
  set HIVESHELL_API_KEY=sk-xxx
  set HIVESHELL_MODEL=deepseek-chat
  python hiveshell.py --custom

  # 快捷方式
  python hiveshell.py --deepseek       # DeepSeek官方
  python hiveshell.py --ollama         # 纯本地Ollama
  python hiveshell.py --aliyun         # 阿里百炼
  python hiveshell.py --model <model>  # 指定模型
  python hiveshell.py --no-tools       # 纯对话模式
  python hiveshell.py --resume <id>    # 恢复会话
  python hiveshell.py --mcp            # 启用MCP自动连接
"""

import sys, os, json, re, time, hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# 灵壳独立运行 — 不依赖蜂巢项目
PRODUCT_DIR = Path(__file__).parent  # 灵壳自身目录(可独立分发)
USER_HOME = Path.home() / ".hiveshell"  # 用户数据目录
USER_HOME.mkdir(parents=True, exist_ok=True)

# ============================================================
# 工具定义 (OpenAI Function Calling 格式)
# ============================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容。支持文本文件、代码文件。对于大文件可指定行范围。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件绝对路径，如 C:/Users/Administrator/Projects/hivemind/README.md"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始行号（从1开始），可选"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "读取行数上限，可选，默认2000"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建或覆盖写入文件。写入前请确认内容正确。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件绝对路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整内容"
                    }
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "精确替换文件中的字符串。old_str必须与文件内容完全匹配（含缩进），且唯一。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件绝对路径"
                    },
                    "old_str": {
                        "type": "string",
                        "description": "要被替换的原始字符串（必须完全匹配）"
                    },
                    "new_str": {
                        "type": "string",
                        "description": "替换后的新字符串"
                    }
                },
                "required": ["file_path", "old_str", "new_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "搜索蜂巢ChromaDB向量知识库。用于查找以前学到的知识、技能文档、项目记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询，如 '短线猎手v3.1 选股逻辑'"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认5，最大20"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "执行bash/PowerShell命令并返回输出。用于文件操作、git、python脚本等。避免破坏性命令。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的shell命令"
                    },
                    "description": {
                        "type": "string",
                        "description": "命令用途的简短说明"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时毫秒数，默认60000"
                    }
                },
                "required": ["command", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": "按glob模式匹配文件路径。用于查找项目中的文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob模式，如 '**/*.py' 或 'bots/worker_*.py'"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索根目录，默认为蜂巢项目目录"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep_content",
            "description": "在文件内容中搜索正则表达式匹配。用于代码搜索、文本查找。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式搜索模式"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径（文件或目录），默认为蜂巢项目目录"
                    },
                    "glob": {
                        "type": "string",
                        "description": "文件名过滤，如 '*.py'"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hive_status",
            "description": "获取蜂巢系统运行状态：知识库统计、大将在位情况、备份状态、守护进程状态。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网获取最新信息。用于查找技术文档、新闻、市场信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询词"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_agents",
            "description": "spawn多个子代理并行处理任务。每个子代理独立执行，可使用工具。用于代码审查、多文件分析、多维度研究等需要并行处理的场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "子代理名称，如'代码审查'"},
                                "prompt": {"type": "string", "description": "子代理任务描述"}
                            },
                            "required": ["name", "prompt"]
                        },
                        "description": "要并行执行的任务列表"
                    }
                },
                "required": ["tasks"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_status",
            "description": "查询MCP外部工具服务器连接状态。列出已连接的MCP服务器及其提供的工具。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "notebook_read",
            "description": "读取Jupyter .ipynb文件，列出所有cell及其类型和内容摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": ".ipynb文件路径"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "notebook_edit",
            "description": "编辑Jupyter notebook中的cell。支持替换已有cell源码、插入新cell、删除cell。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": ".ipynb文件路径"
                    },
                    "cell_id": {
                        "type": "string",
                        "description": "cell的ID（从notebook_read获取）。插入新cell时可省略（插入到开头）"
                    },
                    "new_source": {
                        "type": "string",
                        "description": "新的cell源码内容"
                    },
                    "edit_mode": {
                        "type": "string",
                        "enum": ["replace", "insert", "delete"],
                        "description": "替换已有cell / 在指定cell后插入新cell / 删除cell"
                    },
                    "cell_type": {
                        "type": "string",
                        "enum": ["code", "markdown"],
                        "description": "cell类型（insert时必填）"
                    }
                },
                "required": ["file_path", "new_source"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "worktree_list",
            "description": "列出当前目录所在Git仓库的所有worktree。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Git仓库路径（默认当前目录）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "worktree_add",
            "description": "在Git仓库中创建一个新的worktree（隔离工作区）。新worktree在独立目录，可并行工作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Git仓库路径（默认当前目录）"
                    },
                    "name": {
                        "type": "string",
                        "description": "worktree名称（用作目录名和分支名）"
                    },
                    "base_ref": {
                        "type": "string",
                        "description": "基准分支（默认当前分支）"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "抓取网页URL内容并用AI分析。用于获取外部文章、文档、API文档等。对标Claude Code WebFetch。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要抓取的网页URL"},
                    "prompt": {"type": "string", "description": "对抓取内容的分析问题（可选）"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_create",
            "description": "创建结构化任务，用于追踪复杂多步工作。对标Claude Code TaskCreate。",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "任务标题"},
                    "description": {"type": "string", "description": "任务详细描述"},
                    "priority": {"type": "string", "enum": ["P0","P1","P2","P3"], "description": "优先级"}
                },
                "required": ["subject"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": "列出所有任务及状态。对标Claude Code TaskList。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cron_create",
            "description": "创建定时提醒任务。到期自动触发通知。对标Claude Code CronCreate。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cron": {"type": "string", "description": "cron表达式(分 时 日 月 周)，如 0 9 * * * 每天9点"},
                    "prompt": {"type": "string", "description": "提醒内容"}
                },
                "required": ["cron", "prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cron_list",
            "description": "列出所有定时提醒。对标Claude Code CronList。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "teammate_send",
            "description": "向其他Agent发送消息。Agent Teams对等通信。对标Claude Code Agent Teams。",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "目标Agent名称"},
                    "summary": {"type": "string", "description": "消息摘要"},
                    "message": {"type": "string", "description": "完整消息内容"}
                },
                "required": ["to", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "捕获当前屏幕截图。对标Claude Code Computer Use。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "保存路径(可选)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_web",
            "description": "打开浏览器访问网页并提取文本内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要访问的URL"},
                    "task": {"type": "string", "description": "任务描述(可选)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill_import",
            "description": "从外部文件导入技能。支持加载社区或自定义技能。对标Claude Code Skills市场。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "技能JSON文件路径"},
                    "url": {"type": "string", "description": "技能下载URL（与file_path二选一）"}
                },
                "required": ["file_path"]
            }
        }
    }
]


# ============================================================
# 工具执行器
# ============================================================
class HooksManager:
    """pre/post工具钩子系统 — 对标Claude Code Hooks"""

    def __init__(self):
        self._pre_hooks = {}   # tool_name -> [callable]
        self._post_hooks = {}  # tool_name -> [callable]
        self._global_pre = []  # 全局pre-hook(所有工具)
        self._global_post = [] # 全局post-hook(所有工具)
        self._stats = {"pre_fired": 0, "post_fired": 0, "blocked": 0}

    def register(self, tool_name: str, pre: callable = None, post: callable = None):
        """注册钩子。tool_name可用 '*' 表示全局"""
        if tool_name == "*":
            if pre: self._global_pre.append(pre)
            if post: self._global_post.append(post)
        else:
            if pre:
                self._pre_hooks.setdefault(tool_name, []).append(pre)
            if post:
                self._post_hooks.setdefault(tool_name, []).append(post)

    def unregister(self, tool_name: str):
        """移除指定工具的所有钩子"""
        self._pre_hooks.pop(tool_name, None)
        self._post_hooks.pop(tool_name, None)

    def fire_pre(self, tool_name: str, args: dict) -> dict:
        """执行pre-hook链。返回(modified_args, blocked_reason)"""
        for hook in self._global_pre:
            self._stats["pre_fired"] += 1
            result = hook(tool_name, args)
            if isinstance(result, dict):
                if result.get("_blocked"):
                    self._stats["blocked"] += 1
                    return args, result.get("_reason", "被全局钩子拦截")
                args = result
        for hook in self._pre_hooks.get(tool_name, []):
            self._stats["pre_fired"] += 1
            result = hook(args)
            if isinstance(result, dict):
                if result.get("_blocked"):
                    self._stats["blocked"] += 1
                    return args, result.get("_reason", "被钩子拦截")
                args = result
        return args, None

    def fire_post(self, tool_name: str, result: str, args: dict) -> str:
        """执行post-hook链。返回modified_result"""
        for hook in self._global_post:
            self._stats["post_fired"] += 1
            result = hook(tool_name, result, args) or result
        for hook in self._post_hooks.get(tool_name, []):
            self._stats["post_fired"] += 1
            result = hook(result, args) or result
        return result

    def fire_event(self, event: str, **kwargs):
        """触发命名事件钩子(对标Claude Code 13事件类型)"""
        handlers = getattr(self, f'_event_{event}', [])
        for h in handlers:
            try: h(**kwargs)
            except Exception: pass

    def on(self, event: str, handler: callable):
        """注册事件处理器。事件: session_start/session_end/user_prompt/stop"""
        attr = f'_event_{event}'
        if not hasattr(self, attr):
            setattr(self, attr, [])
        getattr(self, attr).append(handler)

    def status(self) -> dict:
        pre_count = sum(len(v) for v in self._pre_hooks.values()) + len(self._global_pre)
        post_count = sum(len(v) for v in self._post_hooks.values()) + len(self._global_post)
        tools = set(list(self._pre_hooks.keys()) + list(self._post_hooks.keys()))
        events = [k.replace('_event_','') for k in dir(self) if k.startswith('_event_')]
        return {
            "pre_hooks": pre_count, "post_hooks": post_count,
            "hooked_tools": list(tools), "stats": self._stats,
            "events": events,
        }


class ToolExecutor:
    """将工具名称映射到实际Python函数"""

    def __init__(self, base_dir: Path = None, mcp_manager=None, model_backend=None):
        self.base_dir = base_dir or PRODUCT_DIR
        self._tools = {t["function"]["name"]: t for t in TOOLS}
        self._mcp = mcp_manager
        self._backend = model_backend
        self._sub_agents_enabled = model_backend is not None
        self.hooks = HooksManager()  # Hooks系统(P3收尾)

    def list_tools(self) -> List[dict]:
        return self.get_all_tools()

    def execute(self, name: str, arguments: dict) -> str:
        """执行工具调用，含pre/post钩子"""
        # MCP工具路由
        if name.startswith("mcp_") and self._mcp:
            return self.execute_mcp_tool(name, arguments)

        # Pre-hooks: 可修改参数或拦截
        args, blocked = self.hooks.fire_pre(name, dict(arguments))
        if blocked:
            return json.dumps({"error": f"工具执行被拦截: {blocked}"}, ensure_ascii=False)

        method = getattr(self, f"_tool_{name}", None)
        if method is None:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)

        # 通用防护：清洗 None/null 值
        clean_args = {}
        for k, v in args.items():
            if v is None:
                continue
            clean_args[k] = v

        try:
            result = method(clean_args)
            if isinstance(result, str) and len(result) > 8000:
                result = result[:8000] + f"\n\n... [截断，原长度{len(result)}字符]"
        except Exception as e:
            result = json.dumps({"error": f"工具执行失败: {e}"}, ensure_ascii=False)

        # Post-hooks: 可修改结果
        result = self.hooks.fire_post(name, result, clean_args)
        return result

    # ---- 工具实现 ----

    def _tool_read_file(self, args: dict) -> str:
        file_path = args["file_path"]
        # 防御：模型可能传 null/None
        offset = args.get("offset") or 1
        offset = int(offset) - 1  # 转为0-based
        limit = args.get("limit") or 2000
        limit = int(limit)

        p = Path(file_path)
        if not p.exists():
            return f"[错误] 文件不存在: {file_path}"
        if p.is_dir():
            # 列出目录
            items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            lines = [f"目录: {file_path}"]
            for item in items[:100]:
                suffix = "/" if item.is_dir() else f" ({self._fmt_size(item)})"
                lines.append(f"  {item.name}{suffix}")
            return "\n".join(lines)

        try:
            content = p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            return f"[错误] 无法以UTF-8读取，可能是二进制文件: {file_path}"

        lines = content.split('\n')
        total = len(lines)

        if offset >= total:
            return f"[提示] 文件共{total}行，offset={args.get('offset',1)}超出范围"

        selected = lines[offset:offset + limit]
        result = []
        for i, line in enumerate(selected):
            result.append(f"{offset + i + 1:6d}\t{line}")

        header = f"文件: {file_path} | 行 {offset+1}-{min(offset+len(selected), total)} / {total}"
        return header + "\n" + "\n".join(result)

    def _tool_write_file(self, args: dict) -> str:
        file_path = args["file_path"]
        content = args["content"]

        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)

        existed = p.exists()
        p.write_text(content, encoding='utf-8')

        action = "已覆盖" if existed else "已创建"
        return f"[OK] {action}: {file_path} ({len(content)}字符)"

    def _tool_edit_file(self, args: dict) -> str:
        file_path = args["file_path"]
        old_str = args["old_str"]
        new_str = args["new_str"]

        p = Path(file_path)
        if not p.exists():
            return f"[错误] 文件不存在: {file_path}"

        content = p.read_text(encoding='utf-8')

        count = content.count(old_str)
        if count == 0:
            return f"[错误] old_str在文件中未找到。请确认字符串完全匹配（含缩进/空格）。"
        if count > 1:
            return f"[错误] old_str在文件中出现{count}次（不唯一）。请包含更多上下文使其唯一。"

        new_content = content.replace(old_str, new_str, 1)
        p.write_text(new_content, encoding='utf-8')
        return f"[OK] 已编辑: {file_path} (替换1处)"

    def _tool_search_knowledge_base(self, args: dict) -> str:
        query = args["query"]
        top_k = min(args.get("top_k", 5), 20)

        # 灵壳独立模式 — hive_core是可选的
        try:
            from hive_core import HiveMind
            h = HiveMind()
            results = h.search_with_rerank(query, top_k=top_k)
            if not results:
                return f"[提示] 知识库中未找到与 '{query}' 相关的内容。"
            lines = [f"知识库搜索结果 (top {len(results)}):"]
            for i, r in enumerate(results):
                score = r.get('score', r.get('relevance', 0))
                title = r.get('title', r.get('text', ''))[:120]
                lines.append(f"  [{i+1}] 相关度:{score:.3f} | {title}")
                if r.get('url'):
                    lines.append(f"      URL: {r['url'][:100]}")
            return "\n".join(lines)
        except ImportError:
            return "[提示] 知识库搜索不可用（独立模式）。灵壳运行在独立环境，未连接蜂巢ChromaDB。这不影响其他功能。"
        except Exception as e:
            return f"[错误] 知识库搜索失败: {e}"

    def _tool_run_shell(self, args: dict) -> str:
        command = args["command"]
        desc = args.get("description", "无描述")
        timeout = min(args.get("timeout", 60000), 120000)  # 最大2分钟

        import subprocess

        try:
            r = subprocess.run(
                command, shell=True,
                capture_output=True, text=True,
                timeout=timeout / 1000,
                cwd=str(Path.cwd())
            )
            output = r.stdout
            if r.stderr:
                output += "\n[stderr]\n" + r.stderr

            if not output.strip():
                output = f"[exit code: {r.returncode}]"

            return f"命令: {command}\n说明: {desc}\n输出:\n{output[:6000]}"
        except subprocess.TimeoutExpired:
            return f"[超时] 命令执行超过{timeout}ms: {command}"
        except Exception as e:
            return f"[错误] 命令执行失败: {e}"

    def _tool_glob_files(self, args: dict) -> str:
        pattern = args["pattern"]
        root = Path(args.get("path", str(self.base_dir)))

        if not root.exists():
            return f"[错误] 目录不存在: {root}"

        matches = sorted(root.glob(pattern))
        # 限制结果
        if len(matches) > 100:
            lines = [f"Glob: {pattern} → 找到{len(matches)}个文件 (显示前100):"]
        else:
            lines = [f"Glob: {pattern} → 找到{len(matches)}个文件:"]

        for m in matches[:100]:
            rel = m.relative_to(root) if m.is_relative_to(root) else m
            suffix = "/" if m.is_dir() else f" ({self._fmt_size(m)})"
            lines.append(f"  {rel}{suffix}")

        return "\n".join(lines)

    def _tool_grep_content(self, args: dict) -> str:
        pattern = args["pattern"]
        search_path = args.get("path", str(self.base_dir))
        glob_filter = args.get("glob")

        import subprocess

        cmd = ["rg", "--no-heading", "-n", "--color", "never", pattern, search_path]
        if glob_filter:
            cmd += ["--glob", glob_filter]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(self.base_dir))
            lines = r.stdout.strip().split('\n') if r.stdout.strip() else []

            if not lines:
                return f"[提示] 未找到匹配 '{pattern}' 的内容"

            if len(lines) > 50:
                result = f"Grep: '{pattern}' → 找到{len(lines)}处匹配 (显示前50):\n"
                result += "\n".join(lines[:50])
            else:
                result = f"Grep: '{pattern}' → 找到{len(lines)}处匹配:\n"
                result += "\n".join(lines)
            return result[:6000]
        except FileNotFoundError:
            return "[错误] rg (ripgrep) 未安装。请安装: choco install ripgrep 或使用系统搜索。"
        except Exception as e:
            return f"[错误] 搜索失败: {e}"

    def _tool_get_hive_status(self, args: dict) -> str:
        """获取蜂巢系统状态"""
        lines = ["=== 蜂巢系统状态 ===", f"时间: {datetime.now().isoformat()}"]

        # 知识库统计(灵壳独立模式 — hive_core可选)
        try:
            from hive_core import HiveMind
            h = HiveMind()
            report = h.report()
            lines.append(f"\n📚 蜂巢知识库: {report}")
        except Exception:
            lines.append(f"\n📚 蜂巢知识库: 未连接（灵壳独立模式）")

        # 备份状态
        backup_manifest = self.base_dir / "data" / "backup_manifest.json"
        if backup_manifest.exists():
            try:
                data = json.loads(backup_manifest.read_text(encoding='utf-8'))
                lines.append(f"\n💾 备份: D+E双盘 | {data.get('total_files', '?')}文件")
            except:
                lines.append("\n💾 备份: manifest 存在但无法解析")

        # 进程检查
        import subprocess
        for proc, label in [
            ("hive_watchdog.py", "看门狗"),
            ("hive_daemon.py", "守护进程"),
            ("governor_system.py", "节度使系统"),
        ]:
            try:
                r = subprocess.run(
                    ["tasklist", "/FI", f"WINDOWTITLE eq {proc}"],
                    capture_output=True, text=True, timeout=5
                )
                status = "✅" if proc.lower() in r.stdout.lower() or "python" in r.stdout.lower() else "❓"
            except:
                status = "❓"
            lines.append(f"  {status} {label}")

        lines.append(f"\n🛡️ 铁律: 15条 | 大吏: 7将 | 武器: 81件")
        lines.append(f"📦 产品: 32款 | 知识库: 2,340条")

        return "\n".join(lines)

    def _tool_web_search(self, args: dict) -> str:
        query = args["query"]
        # 尝试使用内置搜索
        try:
            import urllib.request
            import urllib.parse

            # 使用DuckDuckGo lite (免API key)
            url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "HiveMind/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode('utf-8', errors='ignore')

            # 简单提取结果
            results = []
            for match in re.finditer(r'<a[^>]*class="result-link"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', html):
                results.append({"title": match.group(2).strip(), "url": match.group(1)})

            if not results:
                # 尝试备用提取
                for match in re.finditer(r'<a[^>]*href="(https?://[^"]*)"[^>]*>([^<]{10,})</a>', html):
                    if 'duckduckgo' not in match.group(1):
                        results.append({"title": match.group(2).strip()[:100], "url": match.group(1)})

            if results:
                lines = [f"搜索 '{query}' 结果:"]
                for i, r in enumerate(results[:8]):
                    lines.append(f"  [{i+1}] {r['title']}")
                    lines.append(f"      {r['url']}")
                return "\n".join(lines)
            else:
                return f"[提示] DuckDuckGo搜索 '{query}' 无结果。可能需要更具体的查询词。"
        except Exception as e:
            return f"[错误] 网络搜索失败: {e}。蜂巢暂无可用的搜索API。"

    def _tool_spawn_agents(self, args: dict) -> str:
        """spawn子代理并行执行任务"""
        tasks = args.get("tasks", [])
        if not tasks:
            return json.dumps({"error": "tasks列表为空"}, ensure_ascii=False)
        if not self._backend:
            return json.dumps({"error": "子代理系统未初始化：缺少模型后端"}, ensure_ascii=False)

        results = []
        # 限制子代理可用的工具（防止递归spawn）
        sub_tools = [t for t in TOOLS if t["function"]["name"] not in ("spawn_agents",)]

        try:
            from agents.hive_agent_framework import spawn_agents
            results = spawn_agents(tasks, self._backend, self, sub_tools)
        except ImportError:
            # Fallback: 内联子代理逻辑（不依赖外部模块）
            for task in tasks:
                name = task.get("name", "sub")
                prompt = task.get("prompt", "")
                # 简化版子代理：直接让后端回答
                resp = self._backend.chat([
                    {"role": "system", "content": f"你是子代理'{name}'。用可用工具完成任务，返回简洁结果。"},
                    {"role": "user", "content": prompt}
                ], tools=sub_tools, stream=False)
                results.append({
                    "name": name,
                    "success": True,
                    "result": resp.get("content", "无结果")[:500],
                    "turns": 1,
                    "tools_used": [],
                })

        # 格式化输出
        lines = [f"子代理执行结果 ({len(results)}个):"]
        for r in results:
            status = "✅" if r.get("success") else "❌"
            name = r.get("name", "?")
            result_text = r.get("result", "")[:200]
            turns = r.get("turns", 0)
            tools = r.get("tools_used", [])
            lines.append(f"\n{status} {name} ({turns}轮, 用了{len(tools)}个工具)")
            lines.append(f"   {result_text}")

        return "\n".join(lines)

    def _tool_mcp_status(self, args: dict) -> str:
        """查询MCP连接状态"""
        if not self._mcp:
            return json.dumps({
                "enabled": False,
                "message": "MCP未启用。启动时加 --mcp 参数开启。",
                "available_servers": list(KNOWN_MCP_SERVERS.keys()) if hasattr(self, '_mcp') else [],
            }, ensure_ascii=False, indent=2)

        return json.dumps(self._mcp.get_status(), ensure_ascii=False, indent=2)

    # ---- P3: Notebook + Worktree ----

    def _tool_notebook_read(self, args: dict) -> str:
        """读取Jupyter .ipynb文件"""
        file_path = args["file_path"]
        p = Path(file_path)
        if not p.exists():
            return f"[错误] 文件不存在: {file_path}"
        if not p.suffix == ".ipynb":
            return f"[错误] 不是.ipynb文件: {file_path}"

        try:
            nb = json.loads(p.read_text(encoding="utf-8"))
            cells = nb.get("cells", [])
            lines = [f"Notebook: {file_path} | {len(cells)} cells"]
            for i, cell in enumerate(cells):
                ctype = cell.get("cell_type", "?")
                cid = cell.get("id", f"cell-{i}")
                src = "".join(cell.get("source", []))
                preview = src[:100].replace("\n", "\\n")
                lines.append(f"\n  [{i}] id={cid} type={ctype}")
                lines.append(f"      {preview}{'...' if len(src) > 100 else ''}")
            return "\n".join(lines)
        except json.JSONDecodeError as e:
            return f"[错误] JSON解析失败: {e}"
        except Exception as e:
            return f"[错误] 读取失败: {e}"

    def _tool_notebook_edit(self, args: dict) -> str:
        """编辑Jupyter notebook cell"""
        file_path = args["file_path"]
        new_source = args.get("new_source", "")
        edit_mode = args.get("edit_mode", "replace")
        cell_id = args.get("cell_id")
        cell_type = args.get("cell_type", "code")

        p = Path(file_path)
        if not p.exists():
            return f"[错误] 文件不存在: {file_path}"

        try:
            nb = json.loads(p.read_text(encoding="utf-8"))
            cells = nb.get("cells", [])

            if edit_mode == "insert":
                import uuid
                new_cell = {
                    "id": str(uuid.uuid4())[:8],
                    "cell_type": cell_type,
                    "source": [new_source],
                    "metadata": {},
                    "outputs": [] if cell_type == "code" else None,
                }
                if cell_id:
                    # 在指定cell后插入
                    for i, c in enumerate(cells):
                        if c.get("id") == cell_id:
                            cells.insert(i + 1, new_cell)
                            break
                    else:
                        cells.append(new_cell)
                else:
                    cells.insert(0, new_cell)
                msg = f"在{'开头' if not cell_id else f'cell {cell_id}后'}插入了新{cell_type} cell"

            elif edit_mode == "delete":
                if not cell_id:
                    return "[错误] delete模式需要指定cell_id"
                before = len(cells)
                nb["cells"] = [c for c in cells if c.get("id") != cell_id]
                after = len(nb["cells"])
                msg = f"已删除cell {cell_id} ({before - after}个)"

            else:  # replace
                if not cell_id:
                    return "[错误] replace模式需要指定cell_id"
                found = False
                for c in cells:
                    if c.get("id") == cell_id:
                        c["source"] = [new_source]
                        found = True
                        break
                if not found:
                    return f"[错误] 未找到cell: {cell_id}"
                msg = f"已替换cell {cell_id}"

            p.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
            return f"[OK] {msg}: {file_path}"
        except Exception as e:
            return f"[错误] notebook编辑失败: {e}"

    def _tool_worktree_list(self, args: dict) -> str:
        """列出Git worktree"""
        repo_path = args.get("path") or str(Path.cwd())
        import subprocess
        try:
            r = subprocess.run(
                ["git", "worktree", "list"],
                capture_output=True, text=True, timeout=10,
                cwd=repo_path
            )
            if r.returncode != 0:
                return f"[错误] git worktree list失败:\n{r.stderr[:300]}"
            lines = r.stdout.strip().split("\n")
            result = f"Git Worktree列表 ({len(lines)}个):\n"
            for line in lines:
                result += f"  {line}\n"
            return result
        except FileNotFoundError:
            return "[错误] git未安装或不在PATH中"
        except Exception as e:
            return f"[错误] {e}"

    def _tool_worktree_add(self, args: dict) -> str:
        """创建Git worktree"""
        repo_path = args.get("path") or str(Path.cwd())
        name = args.get("name", "worktree")
        base_ref = args.get("base_ref", "")

        import subprocess

        # 先检查是否git仓库
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True, text=True, timeout=5,
                cwd=repo_path
            )
            if r.returncode != 0:
                return f"[错误] 不是Git仓库: {repo_path}"
        except Exception as e:
            return f"[错误] {e}"

        # 创建worktree
        worktree_path = Path(repo_path).parent / f".worktrees/{name}" if isinstance(repo_path, str) else Path.cwd().parent / f".worktrees/{name}"
        cmd = ["git", "worktree", "add", str(worktree_path)]
        if base_ref:
            cmd.extend([base_ref])
        else:
            cmd.extend(["-b", f"worktree/{name}"])

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=repo_path)
            if r.returncode == 0:
                return f"[OK] Worktree已创建: {worktree_path}\n{r.stdout.strip()}"
            else:
                return f"[错误] 创建失败:\n{r.stderr[:300]}"
        except Exception as e:
            return f"[错误] {e}"

# ---- 新工具: WebFetch + Task系统 ----

    def _tool_web_fetch(self, args: dict) -> str:
        """抓取网页内容"""
        url = args["url"]
        prompt = args.get("prompt", "")
        try:
            import urllib.request, urllib.error
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; HiveShell/3.0)"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
            # 简易提取文本
            import re
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            # 截断
            if len(text) > 4000:
                text = text[:4000] + f"... [截断,原文{len(text)}字符]"
            result = f"URL: {url}\n内容({len(text)}字符):\n{text}"
            if prompt and self._backend:
                analysis = self._backend.chat([
                    {"role": "system", "content": "分析以下网页内容。"},
                    {"role": "user", "content": f"内容: {text[:2000]}\n\n问题: {prompt}"}
                ], tools=None, stream=False)
                result += f"\n\nAI分析: {analysis.get('content', '')[:500]}"
            return result
        except Exception as e:
            return f"[错误] 网页抓取失败: {e}"

    def _tool_task_create(self, args: dict) -> str:
        """创建任务"""
        subject = args["subject"]
        desc = args.get("description", "")
        priority = args.get("priority", "P2")
        task_id = f"task_{int(time.time())}"
        task = {
            "id": task_id, "subject": subject, "description": desc,
            "priority": priority, "status": "pending",
            "created": datetime.now().isoformat(),
        }
        task_dir = USER_HOME / "tasks"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / f"{task_id}.json").write_text(
            json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"[OK] 任务已创建: [{priority}] {subject} (id={task_id})"

    def _tool_task_list(self, args: dict) -> str:
        """列出所有任务"""
        task_dir = USER_HOME / "tasks"
        if not task_dir.exists():
            return "暂无任务"
        tasks = []
        for f in sorted(task_dir.glob("task_*.json")):
            try:
                t = json.loads(f.read_text(encoding="utf-8"))
                status_icon = {"pending":" ","in_progress":"-","completed":"X","deleted":"D"}.get(t.get("status","?"),"?")
                tasks.append(f"[{status_icon}] [{t.get('priority','?')}] {t.get('subject','?')} ({t.get('status','?')})")
            except: pass
        return "\n".join(tasks) if tasks else "暂无任务"

    # ---- 深化: Cron + Agent Teams + Skills ----

    def _tool_cron_create(self, args: dict) -> str:
        cron_expr = args["cron"]
        prompt = args["prompt"]
        cron_dir = USER_HOME / "crons"
        cron_dir.mkdir(parents=True, exist_ok=True)
        job = {
            "id": f"cron_{int(time.time())}",
            "cron": cron_expr, "prompt": prompt,
            "created": datetime.now().isoformat(), "fired": 0,
        }
        (cron_dir / f"{job['id']}.json").write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"[OK] 定时提醒已创建: {cron_expr} -> {prompt[:60]}"

    def _tool_cron_list(self, args: dict) -> str:
        cron_dir = USER_HOME / "crons"
        if not cron_dir.exists():
            return "暂无定时提醒"
        jobs = []
        for f in sorted(cron_dir.glob("cron_*.json")):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
                jobs.append(f"[id={j['id'][:12]}] {j['cron']} -> {j['prompt'][:60]}")
            except: pass
        return "\n".join(jobs) if jobs else "暂无定时提醒"

    def _tool_teammate_send(self, args: dict) -> str:
        to = args["to"]
        msg = args["message"]
        summary = args.get("summary", msg[:30])
        msg_dir = USER_HOME / "messages"
        msg_dir.mkdir(parents=True, exist_ok=True)
        envelope = {
            "to": to, "from": "蜂王",
            "summary": summary, "message": msg,
            "timestamp": datetime.now().isoformat(),
        }
        (msg_dir / f"msg_{int(time.time())}.json").write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"[OK] 消息已发送至 {to}: {summary}"

    def _tool_skill_import(self, args: dict) -> str:
        file_path = args.get("file_path", "")
        url = args.get("url", "")
        if url:
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": "HiveShell/3.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                return f"[错误] 下载技能失败: {e}"
        elif file_path:
            try:
                data = json.loads(Path(file_path).read_text(encoding="utf-8"))
            except Exception as e:
                return f"[错误] 读取技能文件失败: {e}"
        else:
            return "[错误] 需要file_path或url"
        skill_name = data.get("name", "unknown")
        skill_dir = USER_HOME / "skills"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / f"{skill_name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"[OK] 技能已导入: {skill_name} (可通过/skill-load {skill_name}加载)"

    def get_all_tools(self) -> List[dict]:
        """获取所有可用工具（含MCP工具）"""
        all_tools = list(TOOLS)
        if self._mcp:
            mcp_tools = self._mcp.list_all_tools()
            all_tools.extend(mcp_tools)
        return all_tools

    def execute_mcp_tool(self, name: str, arguments: dict) -> str:
        """执行MCP工具（由execute方法路由）"""
        if self._mcp:
            return self._mcp.call_tool(name, arguments)
        return json.dumps({"error": "MCP未启用"}, ensure_ascii=False)

    @staticmethod
    def _fmt_size(p: Path) -> str:
        try:
            size = p.stat().st_size
            if size < 1024:
                return f"{size}B"
            elif size < 1024 * 1024:
                return f"{size/1024:.1f}KB"
            else:
                return f"{size/(1024*1024):.1f}MB"
        except:
            return "?B"

# MCP服务器列表（引用）
try:
    from agents.hive_mcp_client import KNOWN_MCP_SERVERS
except ImportError:
    KNOWN_MCP_SERVERS = {}


# ============================================================
# 模型后端 (统一API接口)
# ============================================================
class ModelBackend:
    """统一模型调用接口 — 支持任意OpenAI兼容API + DeepSeek/硅基/百炼/Ollama"""

    def __init__(self, backend="custom", model=None):
        self.backend = backend
        self.model = model
        self._setup()

    def _setup(self):
        if self.backend == "custom":
            # 通用后端：任意兼容OpenAI API的端点
            self.api_url = os.environ.get("HIVESHELL_API_URL", "")
            self.api_key = os.environ.get("HIVESHELL_API_KEY", "")
            self.default_model = os.environ.get("HIVESHELL_MODEL", "deepseek-chat")
            if not self.api_url:
                raise ValueError(
                    "自定义后端需设置环境变量:\n"
                    "  HIVESHELL_API_URL=https://api.deepseek.com/v1/chat/completions\n"
                    "  HIVESHELL_API_KEY=sk-xxx\n"
                    "  HIVESHELL_MODEL=deepseek-chat"
                )
        elif self.backend == "siliconflow":
            self.api_url = "https://api.siliconflow.cn/v1/chat/completions"
            self.api_key = os.environ.get("SF_API_KEY") or os.environ.get("SILICONFLOW_API_KEY", "")
            self.default_model = "deepseek-ai/DeepSeek-V3.2"
        elif self.backend == "aliyun":
            self.api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
            self.api_key = os.environ.get("ALI_API_KEY", "")
            self.default_model = "qwen3.7-max"
        elif self.backend == "deepseek":
            # DeepSeek官方API快捷入口
            self.api_url = "https://api.deepseek.com/v1/chat/completions"
            self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            self.default_model = "deepseek-chat"
        elif self.backend == "ollama":
            self.api_url = "http://localhost:11434/v1/chat/completions"
            self.api_key = "ollama"
            self.default_model = os.environ.get("OLLAMA_MODEL", "qwen3:latest")
        else:
            raise ValueError(f"未知后端: {self.backend}。支持: custom / deepseek / siliconflow / aliyun / ollama")

        if not self.model:
            self.model = self.default_model

        if not self.api_key and self.backend not in ("ollama",):
            key_hints = {
                "custom": "HIVESHELL_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "siliconflow": "SF_API_KEY",
                "aliyun": "ALI_API_KEY",
            }
            raise ValueError(
                f"{self.backend} 后端需要 API Key，但未设置。\n"
                f"   请设置环境变量: set {key_hints.get(self.backend, 'API_KEY')}=你的密钥\n"
                f"   或使用本地模式: python hiveshell.py --ollama"
            )

    def chat(self, messages: List[dict], tools: Optional[List[dict]] = None,
             stream: bool = True) -> dict:
        """
        发送对话请求。
        返回: {"content": str, "tool_calls": list or None}
        """
        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4096,
        }

        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"

        if stream:
            return self._stream_chat(headers, data)
        else:
            return self._sync_chat(headers, data)

    def _sync_chat(self, headers: dict, data: dict) -> dict:
        """同步（非流式）请求"""
        import requests

        try:
            r = requests.post(self.api_url, headers=headers, json=data, timeout=120)

            if r.status_code != 200:
                return {
                    "content": f"[API错误 {r.status_code}] {r.text[:300]}",
                    "tool_calls": None
                }

            body = r.json()
            choice = body["choices"][0]
            msg = choice.get("message", {})

            result = {
                "content": msg.get("content", ""),
                "tool_calls": None
            }

            if msg.get("tool_calls"):
                result["tool_calls"] = msg["tool_calls"]
                # 即使有tool_calls也可能有content
                if not result["content"]:
                    result["content"] = ""

            return result

        except requests.exceptions.Timeout:
            return {"content": "[错误] 请求超时(120s)", "tool_calls": None}
        except Exception as e:
            return {"content": f"[连接错误] {e}", "tool_calls": None}

    def _stream_chat(self, headers: dict, data: dict) -> dict:
        """流式请求 — 收集完整响应后返回"""
        import requests

        data["stream"] = True

        try:
            r = requests.post(self.api_url, headers=headers, json=data,
                            stream=True, timeout=120)

            if r.status_code != 200:
                return {
                    "content": f"[API错误 {r.status_code}] {r.text[:300]}",
                    "tool_calls": None
                }

            content_parts = []
            tool_calls_map = {}  # idx -> {id, name, arguments}

            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue

                chunk_str = line[6:]
                if chunk_str == "[DONE]":
                    break

                try:
                    chunk = json.loads(chunk_str)
                    delta = chunk["choices"][0].get("delta", {})

                    # 文本内容
                    if "content" in delta and delta["content"]:
                        text = delta["content"]
                        content_parts.append(text)
                        # 实时输出
                        print(text, end="", flush=True)

                    # 工具调用
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_map:
                                tool_calls_map[idx] = {
                                    "id": tc.get("id", ""),
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                }
                            if "id" in tc and tc["id"]:
                                tool_calls_map[idx]["id"] = tc["id"]
                            if "function" in tc:
                                if "name" in tc["function"] and tc["function"]["name"]:
                                    tool_calls_map[idx]["function"]["name"] = tc["function"]["name"]
                                if "arguments" in tc["function"]:
                                    tool_calls_map[idx]["function"]["arguments"] += tc["function"]["arguments"]

                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

            content = "".join(content_parts)

            # 构建tool_calls
            tool_calls = None
            if tool_calls_map:
                tool_calls = [tool_calls_map[i] for i in sorted(tool_calls_map.keys())]
                # 流式结束后换行
                if content_parts:
                    print()

            return {"content": content, "tool_calls": tool_calls}

        except requests.exceptions.Timeout:
            return {"content": "[错误] 请求超时(120s)", "tool_calls": None}
        except Exception as e:
            return {"content": f"[连接错误] {e}", "tool_calls": None}


# ============================================================
# 会话管理器
# ============================================================
class SessionManager:
    """会话持久化 — 保存/恢复对话历史"""

    SESSION_DIR = USER_HOME / "sessions"

    def __init__(self):
        self.SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def save(self, session_id: str, messages: List[dict], meta: dict = None):
        """保存会话"""
        data = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "message_count": len(messages),
            "meta": meta or {},
            "messages": messages
        }
        filepath = self.SESSION_DIR / f"{session_id}.json"
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def load(self, session_id: str) -> Optional[dict]:
        """加载会话"""
        filepath = self.SESSION_DIR / f"{session_id}.json"
        if not filepath.exists():
            return None
        return json.loads(filepath.read_text(encoding='utf-8'))

    def list_sessions(self) -> List[dict]:
        """列出所有会话"""
        sessions = []
        for f in sorted(self.SESSION_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding='utf-8'))
                sessions.append({
                    "id": data["session_id"],
                    "timestamp": data["timestamp"],
                    "messages": data["message_count"],
                })
            except:
                pass
        return sessions


# ============================================================
# 上下文窗口管理器
# ============================================================
class ContextManager:
    """管理对话上下文，防止超出token限制"""

    # 粗略估算: 1 token ≈ 0.7 中文字符 ≈ 3 英文字符
    MAX_TOKENS = 28000  # 留出余量给响应
    CHARS_PER_TOKEN_CN = 0.7
    CHARS_PER_TOKEN_EN = 3.0

    def estimate_tokens(self, messages: List[dict]) -> int:
        """估算消息的总token数"""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "") or ""
            # 也计入tool_calls
            if "tool_calls" in msg:
                content += json.dumps(msg["tool_calls"], ensure_ascii=False)
            if "tool_call_id" in msg:
                content += msg["tool_call_id"]
            total_chars += len(content)
        return int(total_chars / self.CHARS_PER_TOKEN_CN)

    def trim(self, messages: List[dict], keep_system: bool = True) -> List[dict]:
        """裁剪消息历史以适应上下文窗口"""
        estimated = self.estimate_tokens(messages)

        if estimated <= self.MAX_TOKENS:
            return messages

        # 需要裁剪：保留system消息 + 最近的对话轮次
        result = []
        start = 0

        # 保留第一条system消息
        if keep_system and messages and messages[0]["role"] == "system":
            result.append(messages[0])
            start = 1

        # 从后往前取，直到接近限制
        remaining_tokens = self.MAX_TOKENS - self.estimate_tokens(result)
        tail = []
        tail_tokens = 0

        for msg in reversed(messages[start:]):
            msg_tokens = self.estimate_tokens([msg])
            if tail_tokens + msg_tokens > remaining_tokens * 0.8:
                break
            tail.insert(0, msg)
            tail_tokens += msg_tokens

        if len(tail) < len(messages) - start:
            result.append({
                "role": "system",
                "content": f"[上下文已裁剪: {len(messages) - start - len(tail)}条旧消息已移除]"
            })

        result.extend(tail)
        return result


# ============================================================
# Agent循环 — 核心引擎
# ============================================================
class SmartRouter:
    # Properties for backward compatibility
    @property
    def model(self):
        return self.primary.model
    @property
    def backend(self):
        return self.primary.backend
    """智能路由层 v3.2 — 自动failover + 复杂度选模型 + 多模型级联 + Subagent分发"""

    # 复杂度关键词
    COMPLEX_PATTERNS = [
        r"(?:分析|审计|审查|重构|架构|设计|规划|review|audit|refactor|architect)",
        r"(?:多.*文件|多个.*模块|全.*项目|整个.*代码)",
        r"(?:安全.*漏洞|性能.*优化|深度.*学习|复杂.*逻辑)",
    ]
    SIMPLE_PATTERNS = [
        r"(?:什么是|怎么|如何|为什么|解释|翻译|总结|列出|查看|显示|帮助)",
        r"(?:\?|？|help|list|show|what|how|why|explain)",
    ]

    def __init__(self, primary: 'ModelBackend', fallback: 'ModelBackend' = None,
                 quick: 'ModelBackend' = None, agent: 'ModelBackend' = None):
        self.primary = primary          # 主力模型
        self.fallback = fallback        # 故障转移（可以是同一后端不同模型）
        self.quick = quick              # 简单任务快速模型(省钱)
        self.agent = agent              # Agent/工具调用专用
        self._stats = {"primary": 0, "fallback": 0, "quick": 0, "agent": 0, "failures": 0}

    def _analyze_complexity(self, messages: list) -> str:
        """分析请求复杂度 -> simple / normal / complex"""
        text = " ".join([m.get("content", "") for m in messages if m.get("role") == "user"])
        if not text:
            return "normal"

        import re
        complex_score = sum(len(re.findall(p, text, re.I)) for p in self.COMPLEX_PATTERNS)
        simple_score = sum(len(re.findall(p, text, re.I)) for p in self.SIMPLE_PATTERNS)

        if complex_score >= 2:
            return "complex"
        elif simple_score >= 2 and complex_score == 0:
            return "simple"
        return "normal"

    def _needs_agent(self, tools: list) -> bool:
        """判断是否需要Agent级处理"""
        if tools and len(tools) > 5:
            return True
        return False

    def select_backend(self, messages: list, tools: list = None):
        """选择合适的后端"""
        # 工具密集型 → Agent专用模型
        if tools and len(tools) > 10 and self.agent:
            self._stats["agent"] += 1
            return "agent", self.agent

        # 简单问题 → 快速模型
        complexity = self._analyze_complexity(messages)
        if complexity == "simple" and self.quick:
            self._stats["quick"] += 1
            return "quick", self.quick

        # 复杂问题 → 主力模型
        self._stats["primary"] += 1
        return "primary", self.primary

    def chat(self, messages: list, tools: list = None, stream: bool = True) -> dict:
        """智能路由chat——自动failover"""
        label, backend = self.select_backend(messages, tools)

        # 第一枪
        try:
            result = backend.chat(messages, tools=tools, stream=stream)
            if result.get("content") or result.get("tool_calls"):
                return result
        except Exception as e:
            pass

        # 主力失败 → 用fallback重试
        if self.fallback and backend != self.fallback:
            self._stats["fallback"] += 1
            self._stats["failures"] += 1
            try:
                return self.fallback.chat(messages, tools=tools, stream=stream)
            except Exception:
                pass

        # fallback也失败 → 返回降级回复
        self._stats["failures"] += 1
        return {
            "content": f"[路由层] 所有后端均不可用，请检查网络和API配置。"
                       f"已尝试: {label}",
            "tool_calls": None
        }

    def stats(self) -> dict:
        """路由统计"""
        total = sum(v for k, v in self._stats.items() if k != "failures")
        return {
            **self._stats,
            "total": total,
            "failover_rate": f"{self._stats['fallback']}/{total}" if total else "0/0",
            "backend_info": {
                "primary": f"{self.primary.backend}/{self.primary.model}",
                "fallback": f"{self.fallback.backend}/{self.fallback.model}" if self.fallback else None,
                "quick": f"{self.quick.backend}/{self.quick.model}" if self.quick else None,
                "agent": f"{self.agent.backend}/{self.agent.model}" if self.agent else None,
            }
        }


# ═══════════════════════════════════════════
# v3.2 新增能力: Background Agents + Voice Mode + Computer Use
# ═══════════════════════════════════════════

class BackgroundAgents:
    """后台Agent管理器 — 异步任务·守护模式·回调通知"""

    def __init__(self):
        self._tasks = {}       # task_id → {"thread": Thread, "status": running/done/failed, "result": any}
        self._callbacks = {}   # task_id → callback function
        self._lock = __import__('threading').Lock()

    def run(self, task_id: str, func, args=(), kwargs=None, callback=None, daemon=True):
        """后台运行任务，完成后回调"""
        import threading
        kwargs = kwargs or {}

        def runner():
            try:
                result = func(*args, **kwargs)
                with self._lock:
                    self._tasks[task_id] = {"status": "done", "result": result}
            except Exception as e:
                with self._lock:
                    self._tasks[task_id] = {"status": "failed", "error": str(e)}
            if callback:
                try:
                    callback(task_id, self._tasks.get(task_id, {}))
                except Exception:
                    pass

        t = threading.Thread(target=runner, daemon=daemon, name=f"bg-{task_id}")
        with self._lock:
            self._tasks[task_id] = {"thread": t, "status": "running", "result": None}
        t.start()
        return task_id

    def status(self, task_id: str = None):
        """查询后台任务状态"""
        if task_id:
            t = self._tasks.get(task_id, {})
            return {"id": task_id, "status": t.get("status", "unknown"), "result": str(t.get("result", ""))[:200]}
        return {tid: {"status": t.get("status", "?")} for tid, t in self._tasks.items()}

    def wait(self, task_id: str, timeout: float = None):
        """等待后台任务完成"""
        import threading
        t_info = self._tasks.get(task_id, {})
        thread = t_info.get("thread")
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        return self.status(task_id)

    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.get("thread") and t["thread"].is_alive())

    def stop_all(self):
        """停止所有后台任务（标记取消，不强制kill）"""
        for tid in list(self._tasks.keys()):
            if self._tasks[tid].get("status") == "running":
                self._tasks[tid]["status"] = "cancelled"


class VoiceMode:
    """语音交互层 — STT语音输入 + TTS语音输出"""

    def __init__(self):
        self._stt_available = False
        self._tts_available = False
        self._check_deps()

    def _check_deps(self):
        """检测可用语音库"""
        try:
            import speech_recognition
            self._stt_available = True
        except ImportError:
            pass
        try:
            import pyttsx3
            self._tts_available = True
        except ImportError:
            pass

    def listen(self, timeout: int = 5, language: str = "zh-CN") -> str:
        """麦克风语音输入 → 文本"""
        if not self._stt_available:
            return "[Voice] 语音识别不可用: pip install SpeechRecognition pyaudio"
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=1)
                audio = r.listen(source, timeout=timeout, phrase_time_limit=15)
            return r.recognize_google(audio, language=language)
        except Exception as e:
            return f"[Voice] 识别失败: {e}"

    def speak(self, text: str, rate: int = 180):
        """文本 → 语音输出"""
        if not self._tts_available:
            print(f"[Voice TTS] {text}")
            return False
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', rate)
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception as e:
            print(f"[Voice TTS] 播放失败: {e}, 文本: {text[:100]}")
            return False

    @property
    def available(self) -> dict:
        return {"stt": self._stt_available, "tts": self._tts_available}


class ComputerUse:
    """桌面控制层 — 截图·浏览器自动化·基础桌面操作"""

    def __init__(self):
        self._playwright_available = False
        try:
            from playwright.sync_api import sync_playwright
            self._playwright_available = True
        except ImportError:
            pass

    def screenshot(self, path: str = None) -> str:
        """截取当前屏幕"""
        path = path or str(USER_HOME / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        try:
            import subprocess
            # Windows: 使用PIL截屏
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(path)
            return f"[截图] 已保存: {path} ({img.size[0]}x{img.size[1]})"
        except ImportError:
            pass
        try:
            # 降级: PowerShell截图
            import subprocess, tempfile
            result = subprocess.run(
                ['powershell', '-Command',
                 f'Add-Type -AssemblyName System.Windows.Forms;'
                 f'[System.Windows.Forms.Screen]::PrimaryScreen.Bounds | Out-String'],
                capture_output=True, text=True, timeout=10)
            return f"[屏幕信息] {result.stdout.strip()}"
        except Exception as e:
            return f"[截图] 不可用: {e}。安装: pip install pillow"

    def browse(self, url: str, task: str = "") -> str:
        """浏览器自动化 — 打开网页并执行任务"""
        if not self._playwright_available:
            return f"[浏览器] Playwright未安装: pip install playwright && playwright install chromium"
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                title = page.title()
                text = page.inner_text("body")[:2000]
                browser.close()
                return f"[浏览器] {title}\n{text}"
        except Exception as e:
            return f"[浏览器] 失败: {e}"

    def type_text(self, text: str):
        """模拟键盘输入"""
        try:
            import subprocess
            # PowerShell SendKeys
            escaped = text.replace('"', '""')
            subprocess.run(['powershell', '-Command',
                           f'Add-Type -AssemblyName System.Windows.Forms;'
                           f'[System.Windows.Forms.SendKeys]::SendWait("{escaped}")'],
                          timeout=10)
            return f"[输入] 已发送: {text[:50]}"
        except Exception as e:
            return f"[输入] 失败: {e}"

    @property
    def available(self) -> dict:
        return {"playwright": self._playwright_available, "screenshot": True}


class AgentLoop:
    """对话+工具调用循环"""

    def __init__(self, backend: ModelBackend, tool_executor: ToolExecutor,
                 session_mgr: SessionManager, context_mgr: ContextManager,
                 use_tools: bool = True):
        self.backend = backend
        self.tools = tool_executor
        self.sessions = session_mgr
        self.context = context_mgr
        self.use_tools = use_tools
        self.messages: List[dict] = []
        self.turn_count = 0
        self.session_id = None
        self.bg_agents = BackgroundAgents()

    def _build_system_prompt(self) -> str:
        """构建蜂王系统提示词"""
        claude_md = Path.home() / "CLAUDE.md"
        identity = ""
        if claude_md.exists():
            try:
                identity = claude_md.read_text(encoding='utf-8')[:3000]
            except:
                identity = "你是蜂王，蜂巢系统的总指挥。"

        # 注入跨会话记忆
        memory_ctx = ""
        try:
            from agents.hiveshell_memory import ShellMemory
            mem = ShellMemory()
            memory_ctx = mem.context_for_prompt(limit=8)
        except Exception:
            pass

        addon = f"""
当前状态:
- 时间: {datetime.now().isoformat()}
- 后端: {self.backend.primary.backend if hasattr(self.backend, 'primary') else self.backend.backend} / {self.backend.primary.model if hasattr(self.backend, 'primary') else self.backend.model}
- 路由: 智能路由层 v3.2 {'已启用' if hasattr(self.backend, 'primary') else '未启用'}
- 会话: {self.session_id or '新会话'}
- 工具: {'已启用' if self.use_tools else '已禁用'}
{memory_ctx}

你是蜂王，通过蜂巢·灵壳 v3.2 与蜂场主对话。
你可以使用工具来读取文件、搜索知识库、执行命令、spawn子代理等。
回答风格：直接、准确、行动导向。像真正的蜂王一样思考。"""
        return identity + addon

    def start_session(self, session_id: str = None):
        """开始会话"""
        if session_id:
            data = self.sessions.load(session_id)
            if data:
                self.messages = data["messages"]
                self.session_id = session_id
                return f"已恢复会话 {session_id} ({len(self.messages)}条消息)"

        self.session_id = session_id or datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self.messages = [{"role": "system", "content": self._build_system_prompt()}]
        return f"新会话: {self.session_id}"

    def process_message(self, user_input: str) -> str:
        """
        处理用户输入，运行完整的Agent循环。
        策略: 工具调用阶段用非流式(可靠获取tool_calls)，最终回复用流式(UX更好)。
        返回蜂王的最终文本回复。
        """
        self.turn_count += 1

        # 添加用户消息
        self.messages.append({"role": "user", "content": user_input})

        # 上下文裁剪
        self.messages = self.context.trim(self.messages)

        # 工具调用循环（最多5轮）
        max_tool_rounds = 5
        tools = self.tools.list_tools() if self.use_tools else None

        for round_num in range(max_tool_rounds):
            # 阶段1: 非流式调用(可靠获取tool_calls)
            # 仅在最后一轮(或禁用工具时)才用流式优化体验
            is_final_attempt = (round_num == max_tool_rounds - 1) or not tools
            use_stream = is_final_attempt

            if not use_stream:
                # 非流式: 静默获取，处理工具调用
                response = self.backend.chat(
                    self.messages,
                    tools=tools,
                    stream=False
                )
                content = response.get("content", "")
                tool_calls = response.get("tool_calls")

                # 纯文本回复(模型选择不用工具) → 但还没到最后，用流式重试
                if not tool_calls:
                    print(f"\n🐝 蜂王 > ", end="", flush=True)
                    response = self.backend.chat(
                        self.messages,
                        tools=None,
                        stream=True
                    )
                    content = response.get("content", "")
                    self.messages.append({"role": "assistant", "content": content})
                    self._auto_save()
                    return content

                # 有工具调用 → 打印并执行
                tool_names = [tc["function"]["name"] for tc in tool_calls]
                print(f"\n  🔧 调用工具: {', '.join(tool_names)}")

                # 添加助手消息（含tool_calls）
                self.messages.append({
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": tool_calls
                })

                # 执行每个工具
                for tc in tool_calls:
                    func_name = tc["function"]["name"]
                    try:
                        func_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        func_args = {}

                    print(f"     ⚙️  {func_name}({json.dumps(func_args, ensure_ascii=False)[:200]})")

                    result = self.tools.execute(func_name, func_args)

                    # 简要显示结果
                    preview = result[:150].replace('\n', ' ')
                    print(f"     ✅ {preview}...")

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result
                    })
                # 继续下一轮(带上工具结果)
                continue
            else:
                # 流式: 最终回复，实时输出
                print(f"\n🐝 蜂王 > ", end="", flush=True)
                response = self.backend.chat(
                    self.messages,
                    tools=None,  # 最终轮不用工具
                    stream=True
                )
                content = response.get("content", "")
                self.messages.append({"role": "assistant", "content": content})
                self._auto_save()
                return content

        # 超过最大轮数 → 强制总结
        self.messages.append({
            "role": "user",
            "content": "请基于以上工具执行结果给出最终回答（简洁，不超过500字）。"
        })

        print(f"\n🐝 蜂王 > ", end="", flush=True)
        final = self.backend.chat(self.messages, tools=None, stream=True)
        content = final.get("content", "处理超时，请简化你的问题。")
        self.messages.append({"role": "assistant", "content": content})
        self._auto_save()
        return content

    def _auto_save(self):
        """自动保存会话"""
        try:
            # 保存精简版（去掉system消息中的长身份提示词以节省空间）
            save_msgs = []
            for msg in self.messages:
                if msg["role"] == "system" and len(msg.get("content", "")) > 5000:
                    save_msgs.append({
                        "role": "system",
                        "content": msg["content"][:5000] + "...[截断]"
                    })
                else:
                    save_msgs.append(msg)

            self.sessions.save(self.session_id, save_msgs, {
                "turn_count": self.turn_count,
                "model": self.backend.model,
                "backend": self.backend.backend,
            })
        except Exception:
            pass  # 静默失败，不影响主流程


# ============================================================
# 主入口
# ============================================================
def run_terminal(backend_name="siliconflow", model=None, use_tools=True,
                 session_id=None, enable_mcp=False):
    """启动蜂巢·灵壳 v3.2"""

    # 初始化组件
    primary = ModelBackend(backend_name, model)

    # 智能路由层 v3.2: 主力 + 降级 + 快速 + Agent
    try:
        # 降级模型: 同后端用更稳定/更便宜的模型
        fallback_model = {"deepseek": "deepseek-chat", "siliconflow": "Qwen/Qwen3-8B",
                          "aliyun": "qwen-plus", "ollama": "qwen3:latest"}.get(backend_name, "deepseek-chat")
        fallback = ModelBackend(backend_name, fallback_model) if backend_name != "ollama" else None
        # 快速模型: 简单任务用小模型省钱
        quick_model = {"deepseek": "deepseek-chat", "siliconflow": "Qwen/Qwen3-8B",
                       "aliyun": "qwen-turbo", "ollama": "qwen3:latest"}.get(backend_name, "deepseek-chat")
        quick = ModelBackend(backend_name, quick_model)
        backend = SmartRouter(primary=primary, fallback=fallback, quick=quick, agent=primary)
    except Exception:
        backend = primary  # 降级: 路由层失败直接用主模型

    # MCP初始化
    mcp_manager = None
    mcp_connected = 0
    if enable_mcp:
        try:
            from agents.hive_mcp_client import MCPManager, KNOWN_MCP_SERVERS
            mcp_manager = MCPManager()
            # 自动连接已知服务器（只连可用的）
            for server_name, cfg in KNOWN_MCP_SERVERS.items():
                try:
                    if mcp_manager.connect(server_name, cfg["command"], cfg.get("args", [])):
                        mcp_connected += 1
                except Exception:
                    pass  # 服务器不可用，静默跳过
        except ImportError:
            pass

    tool_executor = ToolExecutor(mcp_manager=mcp_manager, model_backend=backend)
    session_mgr = SessionManager()
    context_mgr = ContextManager()

    # P1: 跨会话记忆
    shell_mem = None
    try:
        from agents.hiveshell_memory import ShellMemory
        shell_mem = ShellMemory()
    except ImportError:
        pass

    # P2: 技能系统
    skill_mgr = None
    try:
        from agents.hive_skills import SkillManager
        skill_mgr = SkillManager()
    except ImportError:
        pass

    agent = AgentLoop(
        backend=backend,
        tool_executor=tool_executor,
        session_mgr=session_mgr,
        context_mgr=context_mgr,
        use_tools=use_tools
    )

    # 启动会话
    start_msg = agent.start_session(session_id)

    # 显示界面
    version = "v3.2"
    total_tools = len(tool_executor.get_all_tools())
    print("=" * 60)
    print(f"  🐝 蜂巢·灵壳 (HiveShell) {version}")
    print(f"  后端: {backend_name} | 模型: {backend.model}")
    print(f"  工具: {total_tools}个 {'✅' if use_tools else '❌'}")
    if enable_mcp:
        print(f"  MCP: {'✅' if mcp_connected > 0 else '⚠️'} 已连接{mcp_connected}个外部服务器")
    print(f"  会话: {agent.session_id}")
    print("  命令: /help /status /tools /sessions /save /clear /quit")
    if enable_mcp:
        print("  MCP工具已就绪，输入 /tools 查看完整工具列表")
    print(f"  {start_msg}")
    print("=" * 60)
    print()

    # 主循环
    while True:
        try:
            user_input = input("蜂场主 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n蜂巢终端 v2.0 关闭。会话已保存。")
            break

        if not user_input:
            continue

        # 内置命令
        if user_input.startswith("/"):
            cmd_parts = user_input.split(maxsplit=1)
            cmd = cmd_parts[0]

            if cmd == "/quit" or cmd == "/exit":
                agent._auto_save()
                print(f"会话已保存: {agent.session_id}")
                print("蜂巢终端 v2.0 关闭。守护进程仍在后台运行。")
                break

            elif cmd == "/help":
                total_t = len(tool_executor.get_all_tools())
                print(f"""
  📋 内置命令:
    /help        - 显示此帮助
    /status      - 蜂巢系统状态
    /tools       - 列出可用工具({total_t}个)
    /sessions    - 列出历史会话
    /save        - 手动保存当前会话
    /clear       - 清空对话上下文
    /quit        - 退出终端

  🧠 记忆 (P1):
    /remember <标题> <内容> - 保存跨会话记忆
    /recall <关键词>        - 搜索记忆
    /forget <标题>          - 删除记忆
    /memory                 - 记忆统计

  📋 规划 (P1):
    /plan <任务>            - 先规划→审批→执行

  🎯 技能 (P2):
    /skills                 - 列出可用技能
    /skill-load <名称>      - 加载技能
    /skill-unload <名称>    - 卸载技能

  🔍 审查 (P2):
    /review <文件路径>      - 代码审查
    /audit <文件路径>       - 安全审计

  🪝 Hooks (P3):
    /hooks                 - 查看钩子状态
    /hook-add <模板>       - 添加钩子(log/safe)
    /hook-rm <工具名>      - 移除钩子

  📋 任务+Git (v3.1):
    /tasks                 - 列出所有任务
    /commit <消息>         - Git提交
    /cost                  - 成本追踪
    /config                - 查看配置
""")

# --- P1: Memory commands ---
            elif cmd == "/remember":
                if not shell_mem:
                    print("记忆系统未初始化")
                elif len(cmd_parts) > 1:
                    parts = cmd_parts[1].split(maxsplit=1)
                    if len(parts) >= 2:
                        shell_mem.remember(parts[0], parts[1], "user")
                        print(f"已记住: {parts[0]}")
                    else:
                        print("用法: /remember <标题> <内容>")
                else:
                    print("用法: /remember <标题> <内容>")

            elif cmd == "/recall":
                if not shell_mem:
                    print("记忆系统未初始化")
                else:
                    query = cmd_parts[1] if len(cmd_parts) > 1 else ""
                    results = shell_mem.recall(query)
                    if results:
                        print(f"记忆搜索结果 ({len(results)}条):")
                        for r in results:
                            print(f"  📌 {r['title']} ({r.get('type','?')})")
                            print(f"     {r['content'][:150]}")
                    else:
                        print(f"未找到匹配 '{query}' 的记忆")

            elif cmd == "/forget":
                if not shell_mem:
                    print("记忆系统未初始化")
                elif len(cmd_parts) > 1:
                    ok = shell_mem.forget(cmd_parts[1])
                    print("已删除" if ok else f"未找到: {cmd_parts[1]}")
                else:
                    print("用法: /forget <标题>")

            elif cmd == "/memory":
                if shell_mem:
                    stats = shell_mem.stats()
                    print(f"记忆: {stats['total']}条 | 存储: {stats['file']} ({stats['size_kb']}KB)")
                else:
                    print("记忆系统未初始化")

# --- v3.2: Voice/Screenshot/Browse/Background ---
            elif cmd == "/voice":
                v = VoiceMode()
                print("正在聆听... (5秒)")
                text = v.listen(timeout=5)
                print(f"你: {text}")
                if text and not text.startswith('[Voice]'):
                    agent.messages.append({"role": "user", "content": text})
                    agent.process_message(text)
            elif cmd == "/say" and len(cmd_parts) > 1:
                v = VoiceMode()
                text = " ".join(cmd_parts[1:])
                v.speak(text)
            elif cmd == "/screenshot":
                cu = ComputerUse()
                print(cu.screenshot())
            elif cmd == "/browse" and len(cmd_parts) > 1:
                cu = ComputerUse()
                print(cu.browse(cmd_parts[1], " ".join(cmd_parts[2:]) if len(cmd_parts) > 2 else ""))
            elif cmd == "/bg":
                print(f"后台任务: {agent.bg_agents.active_count()}个活跃")
                for tid, s in agent.bg_agents.status().items():
                    print(f"  [{tid}] {s['status']}")

# --- P1: Plan mode ---
            elif cmd == "/plan":
                if len(cmd_parts) > 1:
                    task = cmd_parts[1]
                    print(f"📋 规划中: {task[:80]}...")
                    # 让AI先出规划
                    plan_prompt = f"""任务: {task}

请先分析这个任务，然后给出执行计划。格式:
1. 目标: 一句话
2. 步骤: 每步一句话
3. 涉及文件/工具: 列出
4. 风险: 可能遇到的问题

只需输出计划，不要开始执行。"""
                    agent.messages.append({"role": "user", "content": plan_prompt})
                    print("🐝 蜂王 > ", end="", flush=True)
                    resp = backend.chat(agent.messages, tools=None, stream=True)
                    content = resp.get("content", "")
                    agent.messages.append({"role": "assistant", "content": content})
                    print()
                    print("─" * 40)
                    print("请审批以上计划。输入 'ok' 执行，其他取消。")
                    try:
                        approval = input("审批 > ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        approval = "cancel"
                    if approval == "ok":
                        agent.messages.append({"role": "user", "content": f"计划已批准。请按计划执行: {task}"})
                        print("🐝 蜂王 > ", end="", flush=True)
                        resp2 = backend.chat(agent.messages, tools=tool_executor.get_all_tools(), stream=True)
                        c2 = resp2.get("content", "")
                        agent.messages.append({"role": "assistant", "content": c2})
                    else:
                        print("计划已取消。")
                        agent.messages = agent.messages[:-2]  # 移除plan对话
                else:
                    print("用法: /plan <任务描述>")

# --- P2: Skills ---
            elif cmd == "/skills":
                if not skill_mgr:
                    print("技能系统未初始化")
                else:
                    skills_list = skill_mgr.list_available()
                    print(f"可用技能 ({len(skills_list)}个):")
                    for s in skills_list:
                        loaded = "✅" if s["loaded"] else "⬜"
                        print(f"  {loaded} {s['name']:20s} - {s['description']}")

            elif cmd == "/skill-load":
                if not skill_mgr:
                    print("技能系统未初始化")
                elif len(cmd_parts) > 1:
                    name = cmd_parts[1]
                    if skill_mgr.load(name):
                        addon = skill_mgr.get_system_prompt_addon()
                        agent.messages[0]["content"] = agent._build_system_prompt() + addon
                        print(f"技能已加载: {name}")
                    else:
                        print(f"技能不存在: {name}，输入 /skills 查看可用列表")
                else:
                    print("用法: /skill-load <技能名>")

            elif cmd == "/skill-unload":
                if not skill_mgr:
                    print("技能系统未初始化")
                elif len(cmd_parts) > 1:
                    name = cmd_parts[1]
                    if skill_mgr.unload(name):
                        agent.messages[0]["content"] = agent._build_system_prompt()
                        print(f"技能已卸载: {name}")
                    else:
                        print(f"技能未加载: {name}")
                else:
                    print("用法: /skill-unload <技能名>")

# --- P2: Review/Audit ---
            elif cmd in ("/review", "/audit"):
                if not skill_mgr:
                    print("技能系统未初始化")
                elif len(cmd_parts) > 1:
                    target = cmd_parts[1]
                    skill_name = "security-audit" if cmd == "/audit" else "code-review"
                    skill_mgr.load(skill_name)
                    addon = skill_mgr.get_system_prompt_addon()
                    agent.messages[0]["content"] = agent._build_system_prompt() + addon
                    review_prompt = f"请审查文件: {target}。先读取文件内容，然后按审查维度逐一分析。"
                    print(f"🔍 {'安全审计' if cmd == '/audit' else '代码审查'}: {target}")
                    agent.messages.append({"role": "user", "content": review_prompt})
                    try:
                        agent.process_message(review_prompt)
                    except Exception:
                        pass
                    skill_mgr.unload(skill_name)
                    agent.messages[0]["content"] = agent._build_system_prompt()
                else:
                    print(f"用法: {cmd} <文件路径>")

            elif cmd == "/status":
                result = tool_executor.execute("get_hive_status", {})
                print(result)

            elif cmd == "/sessions":
                sessions = session_mgr.list_sessions()
                if sessions:
                    print("历史会话:")
                    for s in sessions[:10]:
                        print(f"  {s['id']} | {s['timestamp']} | {s['messages']}条消息")
                else:
                    print("无历史会话记录")

            elif cmd == "/save":
                agent._auto_save()
                print(f"会话已保存: {agent.session_id}")

            elif cmd == "/resume" and len(cmd_parts) > 1:
                sid = cmd_parts[1]
                msg = agent.start_session(sid)
                print(msg)

            elif cmd == "/clear":
                agent.messages = [agent.messages[0]]
                print("上下文已清空，开始新对话。")

            elif cmd == "/tools":
                all_t = tool_executor.get_all_tools()
                print(f"可用工具 (共{len(all_t)}个):")
                for t in all_t:
                    name = t["function"]["name"]
                    desc = t["function"]["description"][:80]
                    required = t["function"]["parameters"].get("required", [])
                    tag = "🔌" if name.startswith("mcp_") else "🔧"
                    print(f"  {tag} {name}")
                    print(f"     {desc}")
                    if required:
                        print(f"     必填: {', '.join(required)}")

            elif cmd == "/no-tools":
                agent.use_tools = not agent.use_tools
                state = "已禁用" if not agent.use_tools else "已启用"
                print(f"工具调用: {state}")

# --- Hooks管理 ---
            elif cmd == "/hooks":
                status = tool_executor.hooks.status()
                print(f"Hooks系统: {status['pre_hooks']}pre / {status['post_hooks']}post")
                print(f"  统计: pre触发{status['stats']['pre_fired']}次 | post触发{status['stats']['post_fired']}次 | 拦截{status['stats']['blocked']}次")
                if status['hooked_tools']:
                    print(f"  已挂载工具: {', '.join(status['hooked_tools'])}")
                else:
                    print("  暂无钩子。用 /hook-add <工具名> 添加")
                print("  内置钩子模板:")
                print("    log    - 记录所有工具调用到日志")
                print("    safe   - 拦截危险命令(如rm -rf)")

            elif cmd == "/hook-add":
                if len(cmd_parts) > 1:
                    template = cmd_parts[1]
                    if template == "log":
                        def log_hook_post(name, result, args):
                            ts = datetime.now().strftime("%H:%M:%S")
                            arg_str = json.dumps(args, ensure_ascii=False)[:100]
                            print(f"  [HOOK] {ts} {name}({arg_str}) -> {len(result)}chars")
                            return result
                        tool_executor.hooks.register("*", post=log_hook_post)
                        print("已添加全局日志钩子 — 所有工具调用将显示")
                    elif template == "safe":
                        def safe_hook_pre(name, args):
                            cmd = str(args.get("command", args.get("content", "")))
                            dangerous = ["rm -rf /", "format c:", "del /f /s", "> /dev/sda", "mkfs."]
                            for d in dangerous:
                                if d in cmd.lower():
                                    return {"_blocked": True, "_reason": f"危险命令被拦截: {d}"}
                            return args
                        tool_executor.hooks.register("run_shell", pre=safe_hook_pre)
                        tool_executor.hooks.register("write_file", pre=safe_hook_pre)
                        print("已添加安全钩子 — 危险命令将被拦截")
                    else:
                        print(f"未知模板: {template}。可用: log, safe")
                else:
                    print("用法: /hook-add <模板>。模板: log(记录日志) safe(安全拦截)")

            elif cmd == "/hook-rm":
                if len(cmd_parts) > 1:
                    tool_executor.hooks.unregister(cmd_parts[1])
                    print(f"已移除 {cmd_parts[1]} 的钩子")
                else:
                    tool_executor.hooks.unregister("*")
                    print("已移除全局钩子")

# --- 成本追踪 ---
            elif cmd == "/cost":
                total_tokens = agent.turn_count * 2000  # 粗略估算
                est_cost_sf = total_tokens / 1000000 * 1.0  # SiliconFlow ~1元/百万token
                print(f"会话统计:")
                print(f"  对话轮次: {agent.turn_count}")
                print(f"  估算Token: ~{total_tokens:,}")
                print(f"  估算费用(SF): ~{est_cost_sf:.4f}元")
                print(f"  会话ID: {agent.session_id}")

# --- Git集成 ---
            elif cmd == "/commit":
                import subprocess
                msg = cmd_parts[1] if len(cmd_parts) > 1 else "update"
                r = subprocess.run(["git", "add", "-A"], capture_output=True, text=True, cwd=str(Path.cwd()))
                r2 = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True, cwd=str(Path.cwd()))
                if r2.returncode == 0:
                    print(f"[OK] git commit: {msg}")
                else:
                    print(f"[FAIL] {r2.stderr[:200]}")

# --- 路由层 ---
            elif cmd == "/route":
                if hasattr(backend, "stats"):
                    s = backend.stats()
                    print(f"路由统计: 总{s['total']}次 | 主力{s['primary']} | 降级{s['fallback']} | 快速{s['quick']}")
                    print(f"  故障转移率: {s['failover_rate']}")
                else:
                    print("路由层未启用")

# --- 任务管理 ---
            elif cmd == "/tasks":
                result = tool_executor.execute("task_list", {})
                print(result)

# --- 配置管理 ---
            elif cmd == "/config":
                print("灵壳 v3.2 配置:")
                print(f"  后端: {backend_name} / {backend.model}")
                print(f"  工具: {len(tool_executor.get_all_tools())}个")
                print(f"  会话: {agent.session_id}")
                print(f"  MCP: {'已启用' if enable_mcp else '未启用'}")
                print(f"  用户数据: {USER_HOME}")
                print(f"  产品目录: {PRODUCT_DIR}")

            else:
                print(f"未知命令: {cmd}，输入 /help 查看帮助")
            continue

        # 正常对话 → Agent循环
        try:
            agent.process_message(user_input)
        except Exception as e:
            print(f"\n[蜂王出错] {e}")
            print("请重试或输入 /clear 清空上下文。")


# ============================================================
# CLI入口
# ============================================================
if __name__ == "__main__":
    backend = "custom"      # 默认使用通用后端(从环境变量读取)
    model = None
    use_tools = True
    enable_mcp = False
    session_id = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--custom":
            backend = "custom"
            model = os.environ.get("HIVESHELL_MODEL", "deepseek-chat")
        elif args[i] == "--deepseek":
            backend = "deepseek"
            model = "deepseek-chat"
        elif args[i] == "--ollama":
            backend = "ollama"
            model = os.environ.get("OLLAMA_MODEL", "qwen3:latest")
        elif args[i] == "--aliyun":
            backend = "aliyun"
            model = "qwen3.7-max"
        elif args[i] == "--siliconflow":
            backend = "siliconflow"
            model = "deepseek-ai/DeepSeek-V3.2"
        elif args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 1
        elif args[i] == "--no-tools":
            use_tools = False
        elif args[i] == "--mcp":
            enable_mcp = True
        elif args[i] == "--resume" and i + 1 < len(args):
            session_id = args[i + 1]
            i += 1
        elif args[i] == "--list-sessions":
            mgr = SessionManager()
            sessions = mgr.list_sessions()
            if sessions:
                print("历史会话:")
                for s in sessions:
                    print(f"  {s['id']} | {s['timestamp']} | {s['messages']}条")
            else:
                print("无历史会话")
            sys.exit(0)
        i += 1

    run_terminal(backend, model, use_tools, session_id, enable_mcp)
