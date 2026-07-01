"""
蜂巢·灵壳 Agent子代理框架 v1.0
==============================
蜂王可spawn子代理，分发任务、并行执行、回收结果。

架构:
  蜂王(主Agent) → spawn_agent(子代理1, 子代理2, ...)
                    ↓ 并行执行(独立上下文)
                    ↓ 各自调工具
                    ↓ 各自返回结果
  蜂王 ← 综合所有结果 → 回复蜂场主

用法:
  from agents.hive_agent_framework import SubAgent, spawn_agents

  # 单个子代理
  sub = SubAgent(backend, tools, max_turns=3)
  result = sub.run("分析README.md的技术栈并给出建议")

  # 并行多代理
  results = spawn_agents([
      {"name": "代码审查", "prompt": "审查 hive_terminal_v2.py"},
      {"name": "安全审计", "prompt": "检查 hive_terminal_v2.py 安全漏洞"},
  ], backend, tools)
"""

import json
from typing import List, Dict, Optional, Any
from pathlib import Path


class SubAgent:
    """子代理 — 独立上下文，独立工具调用循环"""

    def __init__(self, backend, tools: list = None, max_turns: int = 5,
                 system_prompt: str = None, name: str = "sub-agent"):
        self.backend = backend
        self.tools = tools or []
        self.max_turns = max_turns
        self.name = name
        self.system_prompt = system_prompt or (
            "你是蜂巢·灵壳的子代理。你收到蜂王分配的任务，用可用工具完成它。"
            "只返回最终结果，不返回中间过程。简洁、准确、直接。"
        )
        self.messages = []

    def run(self, task: str, context: dict = None) -> dict:
        """
        执行子代理任务。

        Args:
            task: 任务描述
            context: 额外上下文（可选），如相关文件路径列表

        Returns:
            {"name": str, "success": bool, "result": str, "turns": int, "tools_used": list}
        """
        # 构建初始消息
        ctx_str = ""
        if context:
            ctx_str = "\n背景信息:\n" + json.dumps(context, ensure_ascii=False, indent=2)

        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"任务: {task}{ctx_str}\n\n请用可用工具完成此任务，返回最终结果。"}
        ]

        tools_used = []
        final_result = ""

        for turn in range(self.max_turns):
            response = self.backend.chat(
                self.messages,
                tools=self.tools if self.tools else None,
                stream=False
            )

            content = response.get("content", "")
            tool_calls = response.get("tool_calls")

            # 无工具调用 → 任务完成
            if not tool_calls:
                final_result = content
                break

            # 有工具调用 → 执行
            self.messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": tool_calls
            })

            for tc in tool_calls:
                func_name = tc["function"]["name"]
                tools_used.append(func_name)

                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    func_args = {}

                # 子代理的工具需要通过回调执行
                # 如果提供了 tool_executor，用它执行
                result = self._execute_tool(func_name, func_args)

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result
                })

        if not final_result:
            # 超过max_turns，强制总结
            self.messages.append({
                "role": "user",
                "content": "请基于以上工具执行结果，用一句话给出最终结论。"
            })
            final_resp = self.backend.chat(self.messages, tools=None, stream=False)
            final_result = final_resp.get("content", f"任务'{task}'分析完成(耗时{turn+1}轮)")

        return {
            "name": self.name,
            "success": True,
            "result": final_result.strip(),
            "turns": min(turn + 1, self.max_turns),
            "tools_used": list(set(tools_used)),
        }

    def _execute_tool(self, name: str, args: dict) -> str:
        """子代理工具执行 — 需要有 tool_executor 注入"""
        # 通过外部注入的 executor 执行
        if hasattr(self, '_executor') and self._executor:
            return self._executor.execute(name, args)

        # Fallback: 返回占位（实际使用时必须注入 executor）
        return json.dumps({
            "error": f"子代理工具执行器未注入。工具'{name}'需要外部executor。",
            "args": args
        }, ensure_ascii=False)


def spawn_agents(tasks: List[dict], backend, tool_executor=None,
                 tools: list = None, parallel: bool = True) -> List[dict]:
    """
    批量spawn子代理。

    Args:
        tasks: [{"name": "agent1", "prompt": "...", "context": {...}}, ...]
        backend: ModelBackend实例
        tool_executor: ToolExecutor实例(用于执行工具)
        tools: 子代理可用的工具列表(默认全部)
        parallel: 是否并行(目前按顺序，未来可用线程池)

    Returns:
        [{name, success, result, turns, tools_used}, ...]
    """
    results = []

    if parallel and len(tasks) > 1:
        # 并行执行（使用线程池）
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run_one(task):
            sub = SubAgent(backend, tools=tools, name=task.get("name", "sub"))
            if tool_executor:
                sub._executor = tool_executor
            return sub.run(task["prompt"], task.get("context"))

        with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as executor:
            futures = {executor.submit(_run_one, t): t for t in tasks}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    t = futures[future]
                    results.append({
                        "name": t.get("name", "?"),
                        "success": False,
                        "result": f"子代理异常: {e}",
                        "turns": 0,
                        "tools_used": [],
                    })
    else:
        # 顺序执行
        for task in tasks:
            sub = SubAgent(backend, tools=tools, name=task.get("name", "sub"))
            if tool_executor:
                sub._executor = tool_executor
            try:
                result = sub.run(task["prompt"], task.get("context"))
                results.append(result)
            except Exception as e:
                results.append({
                    "name": task.get("name", "?"),
                    "success": False,
                    "result": f"子代理异常: {e}",
                    "turns": 0,
                    "tools_used": [],
                })

    return results


# ============================================================
# 集成到蜂王CLI壳子的工具定义
# ============================================================
SPAWN_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "spawn_agents",
        "description": "spawn多个子代理并行处理任务。每个子代理独立运行，可以读文件、搜索、执行命令。用于需要并行分析多个文件或多维度审查时。",
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "子代理名称，如'代码审查员'"},
                            "prompt": {"type": "string", "description": "子代理的任务描述"},
                            "context": {
                                "type": "object",
                                "description": "额外上下文（可选），如{'file': 'path/to/file.py'}"
                            }
                        },
                        "required": ["name", "prompt"]
                    },
                    "description": "要并行执行的任务列表"
                }
            },
            "required": ["tasks"]
        }
    }
}
