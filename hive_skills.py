"""
蜂巢·灵壳 技能系统 v1.0
=======================
可加载/卸载的技能模块。每个技能提供专项系统提示词+可选工具。

用法:
  from agents.hive_skills import SkillManager

  mgr = SkillManager()
  mgr.load("code-review")       # 加载代码审查技能
  mgr.load("security-audit")    # 加载安全审计技能
  tools = mgr.get_all_tools()   # 获取所有技能的工具
  prompt = mgr.get_system_prompt_addon()  # 注入系统提示词
"""

import json
from pathlib import Path
from typing import List, Dict, Optional


# ============================================================
# 内置技能定义
# ============================================================
BUILTIN_SKILLS = {
    "code-review": {
        "name": "代码审查",
        "version": "1.0",
        "description": "审查代码质量：bug检测、安全漏洞、性能问题、代码风格",
        "system_prompt": """
你是一个资深代码审查专家。审查代码时关注以下维度：

1. **正确性**: 逻辑错误、边界条件、空值处理、异常处理
2. **安全性**: SQL注入、XSS、路径遍历、硬编码密钥、不安全反序列化
3. **性能**: 不必要的循环、大对象复制、N+1查询、内存泄漏
4. **可维护性**: 命名规范、函数长度、重复代码、注释质量
5. **最佳实践**: 语言惯用法、设计模式、SOLID原则

给出每条问题的：严重程度(🔴高/🟡中/🟢低)、位置(行号)、问题描述、修复建议。
""",
        "tools": [],
    },

    "security-audit": {
        "name": "安全审计",
        "version": "1.0",
        "description": "深度安全审查：OWASP Top 10、CWE、注入攻击、权限漏洞",
        "system_prompt": """
你是一个应用安全专家。按OWASP Top 10框架审查代码安全：

1. **注入攻击**: SQL/命令/代码注入
2. **认证失效**: 弱密码、会话固定、Token泄露
3. **敏感数据暴露**: 日志泄露、明文存储、传输未加密
4. **XML外部实体**: XXE攻击
5. **访问控制失效**: 越权、IDOR
6. **安全配置错误**: 默认密码、错误信息泄露
7. **跨站脚本**: XSS(存储/反射/DOM)
8. **不安全反序列化**: pickle、yaml.load
9. **使用含已知漏洞的组件**: 过期依赖
10. **日志和监控不足**: 无审计追踪

对每个发现给出：风险等级、攻击场景、修复代码。
""",
        "tools": [],
    },

    "refactor": {
        "name": "代码重构",
        "version": "1.0",
        "description": "代码简化、去重、抽象提取、设计模式应用",
        "system_prompt": """
你是一个代码重构专家。专注代码质量和可维护性：

1. **消除重复**: 提取公共函数/类
2. **简化逻辑**: 减少嵌套、提取复杂表达式
3. **改善命名**: 函数/变量/类名清晰表达意图
4. **拆分大函数**: 单一职责，每个函数<50行
5. **设计模式**: 合适的地方应用工厂/策略/观察者等模式
6. **移除死代码**: 未使用的变量/函数/导入

每次重构保证行为不变。给出：重构前→重构后对比。
""",
        "tools": [],
    },

    "explain": {
        "name": "代码解释",
        "version": "1.0",
        "description": "逐行解释代码逻辑、架构分析、技术栈梳理",
        "system_prompt": """
你是一个技术文档专家。解释代码时：

1. **整体架构**: 先讲宏观设计思路
2. **逐模块**: 按文件/类/函数分解讲解
3. **关键逻辑**: 标注核心算法和关键决策点
4. **数据流**: 数据如何在模块间流转
5. **依赖关系**: 外部依赖、模块间调用关系
6. **使用示例**: 给出典型调用示例

用通俗语言，让中级开发者能完全理解。
""",
        "tools": [],
    },

    "write-tests": {
        "name": "测试编写",
        "version": "1.0",
        "description": "自动生成单元测试、集成测试、边界测试用例",
        "system_prompt": """
你是一个测试工程师。为代码生成测试：

1. **单元测试**: 每个函数的正常路径+边界+异常
2. **集成测试**: 模块间交互
3. **边界测试**: 空值、最大值、特殊字符
4. **Mock策略**: 外部依赖的模拟方案
5. **覆盖率目标**: 语句>80%，分支>70%

使用pytest框架。每个测试函数名清晰描述测试场景。
""",
        "tools": [],
    },
}


class SkillManager:
    """技能管理器"""

    def __init__(self, skills_dir: Path = None):
        if skills_dir:
            self.skills_dir = Path(skills_dir)
        else:
            self.skills_dir = Path(__file__).parent.parent / "data" / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.loaded: Dict[str, dict] = {}
        self._load_custom_skills()

    def _load_custom_skills(self):
        """加载自定义技能文件"""
        for sf in self.skills_dir.glob("*.json"):
            try:
                skill = json.loads(sf.read_text(encoding="utf-8"))
                name = skill.get("name", sf.stem)
                BUILTIN_SKILLS[name] = skill
            except Exception:
                pass

    def list_available(self) -> List[dict]:
        """列出所有可用技能"""
        skills = []
        for name, skill in BUILTIN_SKILLS.items():
            skills.append({
                "name": name,
                "title": skill.get("name", name),
                "description": skill.get("description", ""),
                "loaded": name in self.loaded,
            })
        return skills

    def load(self, skill_name: str) -> bool:
        """加载技能"""
        if skill_name in BUILTIN_SKILLS:
            self.loaded[skill_name] = BUILTIN_SKILLS[skill_name]
            return True
        return False

    def unload(self, skill_name: str) -> bool:
        """卸载技能"""
        if skill_name in self.loaded:
            del self.loaded[skill_name]
            return True
        return False

    def get_system_prompt_addon(self) -> str:
        """获取所有已加载技能的系统提示词组合"""
        if not self.loaded:
            return ""

        parts = ["\n[已加载技能]"]
        for name, skill in self.loaded.items():
            parts.append(f"\n### {skill.get('name', name)}")
            parts.append(skill.get("system_prompt", ""))
        return "\n".join(parts)

    def get_all_tools(self) -> List[dict]:
        """获取所有已加载技能提供的工具"""
        tools = []
        for skill in self.loaded.values():
            tools.extend(skill.get("tools", []))
        return tools

    def get_status(self) -> dict:
        """获取技能系统状态"""
        return {
            "loaded_count": len(self.loaded),
            "loaded_names": list(self.loaded.keys()),
            "available_count": len(BUILTIN_SKILLS),
            "available_names": list(BUILTIN_SKILLS.keys()),
        }
