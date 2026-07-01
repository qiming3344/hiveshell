"""
蜂巢·灵壳 跨会话记忆 v1.0
=========================
轻量级跨会话记忆 — 不依赖ChromaDB，纯JSON文件存储。

用法:
  from agents.hiveshell_memory import ShellMemory

  mem = ShellMemory()
  mem.remember("项目进展", "灵壳v3.0已完成Agent+MCP")
  facts = mem.recall("灵壳")
  ctx = mem.context_for_prompt()  # 注入系统提示词
"""

import json, re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


class ShellMemory:
    """灵壳轻量记忆引擎"""

    def __init__(self, memory_dir: Path = None):
        self.memory_dir = memory_dir or (Path.home() / ".hiveshell" / "memory")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.store_file = self.memory_dir / "memory_store.json"
        self._ensure_store()

    def _ensure_store(self):
        if not self.store_file.exists():
            self.store_file.write_text(json.dumps({"memories": [], "updated": ""}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_store(self) -> dict:
        return json.loads(self.store_file.read_text(encoding="utf-8"))

    def _write_store(self, data: dict):
        data["updated"] = datetime.now().isoformat()
        self.store_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def remember(self, title: str, content: str, mem_type: str = "reference") -> dict:
        """保存一条记忆"""
        store = self._read_store()
        mem = {
            "title": title,
            "content": content[:500],
            "type": mem_type,
            "timestamp": datetime.now().isoformat(),
        }
        # 去重(同标题覆盖)
        store["memories"] = [m for m in store["memories"] if m["title"] != title]
        store["memories"].append(mem)
        # 限制总数
        if len(store["memories"]) > 100:
            store["memories"] = store["memories"][-50:]
        self._write_store(store)
        return mem

    def recall(self, query: str = None, mem_type: str = None, limit: int = 10) -> List[dict]:
        """搜索记忆"""
        store = self._read_store()
        results = store["memories"]
        if mem_type:
            results = [m for m in results if m.get("type") == mem_type]
        if query:
            q = query.lower()
            results = [m for m in results if q in m.get("title", "").lower() or q in m.get("content", "").lower()]
        return sorted(results, key=lambda m: m.get("timestamp", ""), reverse=True)[:limit]

    def forget(self, title: str) -> bool:
        """删除记忆"""
        store = self._read_store()
        before = len(store["memories"])
        store["memories"] = [m for m in store["memories"] if m["title"] != title]
        self._write_store(store)
        return len(store["memories"]) < before

    def context_for_prompt(self, limit: int = 10) -> str:
        """获取记忆上下文(注入系统提示词)"""
        recent = sorted(self._read_store()["memories"], key=lambda m: m.get("timestamp", ""), reverse=True)[:limit]
        if not recent:
            return ""

        lines = ["\n[跨会话记忆]"]
        for r in recent:
            tag = {"project": "📋", "feedback": "💬", "user": "👤", "reference": "📌"}.get(r.get("type", ""), "📌")
            lines.append(f"{tag} {r['title']}: {r['content'][:200]}")
        return "\n".join(lines)

    def stats(self) -> dict:
        store = self._read_store()
        return {"total": len(store["memories"]), "file": str(self.store_file),
                "size_kb": round(self.store_file.stat().st_size / 1024, 1) if self.store_file.exists() else 0}
