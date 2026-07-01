# 蜂巢·灵壳 CLI v3.0 (HiveShell)

> AI命令行终端 | 15+工具 | Agent子代理 | MCP协议 | 三层后端 | 隐私安全

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.0.0-orange.svg)]()

灵壳是一个**通用AI命令行终端**，支持15+种工具调用（含Agent子代理、MCP协议、Notebook、Worktree等），**不绑定任何模型厂商**。
**纯Python实现，不依赖Node.js。壳是壳，模型是模型——配什么用什么。**

## ✨ 为什么选择灵壳？

| 对比 | 灵壳 CLI | Claude Code | OpenCode | aider |
|------|----------|-------------|----------|-------|
| 后端自由 | ✅ 任意OpenAI兼容API | ❌ 仅Anthropic | ✅ | ✅ |
| 本地零成本 | ✅ Ollama | ❌ 需API付费 | ✅ | ✅ |
| Agent子代理 | ✅ 内置 | ✅ | ❌ | ❌ |
| MCP扩展 | ✅ 内置 | ✅ | ❌ | ❌ |
| 单文件分发 | ✅ 纯Python | ❌ Node.js重 | ❌ | ❌ |
| 无Node.js依赖 | ✅ | ❌ | ❌ | ❌ |
| 数据不出本地 | ✅ | ❌ | ✅ | ✅ |

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install requests

# 2. 通用模式（推荐）— 配什么用什么
set HIVESHELL_API_URL=https://api.deepseek.com/v1/chat/completions
set HIVESHELL_API_KEY=sk-你的密钥
set HIVESHELL_MODEL=deepseek-chat
python hiveshell.py --custom

# 3. DeepSeek官方API快捷方式
set DEEPSEEK_API_KEY=sk-你的密钥
python hiveshell.py --deepseek

# 4. Ollama纯本地（零成本！）
python hiveshell.py --ollama
```

## 🛠️ 内置工具

### 15+ 核心工具

| 工具 | 功能 | 示例 |
|------|------|------|
| `read_file` | 读取文件 | "打开app.py看看" |
| `write_file` | 创建/覆盖文件 | "创建一个config.json" |
| `edit_file` | 精确替换编辑 | "把第10行的port改成8080" |
| `search_knowledge` | 搜索蜂巢知识库 | "查一下去重引擎的文档" |
| `run_shell` | 执行系统命令 | "运行pytest" |
| `glob_files` | 文件模式匹配 | "找所有*.py文件" |
| `grep_content` | 内容正则搜索 | "搜所有TODO注释" |
| `web_search` | 网络搜索 | "搜Python 3.12新特性" |
| `spawn_agents` | Agent子代理并行 | "同时审查3个文件" |
| `mcp_status` | MCP外部工具 | "查看MCP服务状态" |
| `notebook_read` | 读取Jupyter | "打开analysis.ipynb" |
| `notebook_edit` | 编辑Jupyter | "在notebook加一个cell" |
| `worktree_list` | Git Worktree列表 | "查看所有worktree" |
| `worktree_add` | 创建Git Worktree | "创建feature-X的worktree" |

### 5大技能系统
- 🔍 `/review` — 代码审查
- 🛡️ `/audit` — 安全审计
- ♻️ `/refactor` — 代码重构
- 📝 `/explain` — 代码解释
- 🧪 `/test` — 测试生成

## 🏗️ 架构

```
用户输入 → 灵壳CLI
              ├── 路由到3层后端 (SiliconFlow/百炼/Ollama)
              ├── 工具调用解析 (15+工具)
              ├── Agent子代理分发 (并行执行)
              ├── MCP外部工具桥接
              ├── 会话记忆管理 (跨会话持久化)
              └── Plan模式 (先规划后执行)
```

## 📦 支持的模型后端

| 后端 | 模型 | 费用 | 特点 |
|------|------|------|------|
| SiliconFlow | DeepSeek-V3.2 | API按量 | 云端，推理能力强 |
| 阿里百炼 | Qwen3.7-Max | API按量 | 云端，中文优化 |
| Ollama本地 | Qwen3 8B | **免费** | 100%本地，隐私安全 |

## 🔧 安装

**系统要求:** Python 3.10+ | Windows / macOS / Linux

```bash
git clone https://github.com/qiming3344/hiveshell.git
cd hiveshell
pip install requests
python hiveshell.py --ollama  # 本地模式开箱即用
```

**可选依赖 (增强功能):**
```bash
pip install playwright    # 浏览器自动化工具
# 安装 ripgrep 用于 grep_content 工具
# 安装 Ollama 用于本地模型
```

## 📖 使用示例

```bash
# 基础对话
$ python hiveshell.py --ollama
你> 帮我分析一下这个项目的代码结构
灵壳> 正在读取项目文件...
      发现12个Python文件，3个模块...

# 代码审查
你> /review app.py
灵壳> 启动代码审查...
      [安全问题] 第45行: SQL注入风险
      [性能问题] 第78行: N+1查询
      ...

# Agent并行任务
你> 同时检查 auth.py, api.py, models.py 的安全性
灵壳> 启动3个Agent子代理并行审计...
```

## 🗺️ 路线图

- [x] 15+核心工具
- [x] Agent子代理系统
- [x] MCP协议支持
- [x] 3层后端切换
- [x] 跨会话记忆
- [x] Plan模式
- [x] 5技能系统
- [ ] GUI桌面版 (计划中)
- [ ] VS Code插件 (计划中)
- [ ] 团队协作版 (计划中)

## 🤝 贡献

欢迎提交Issue和PR！灵壳是蜂巢生态系统的一部分。

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)

---

**蜂巢AI实验室** | 自研 · 开放 · 隐私优先
