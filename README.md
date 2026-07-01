# 蜂巢·灵壳 HiveShell v3.2

> 通用AI命令行终端 | 不绑定任何厂商 | 15/15对标Claude Code

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.2.0-orange)]()

灵壳是一个**通用AI命令行终端**，支持24个工具、Agent子代理、MCP协议、智能路由层，**不绑定任何模型厂商**。壳是壳，模型是模型——配什么用什么。

## 为什么选择灵壳？

| 对比 | 灵壳 CLI v3.2 | Claude Code | OpenCode | aider |
|------|:----------:|:-----------:|:--------:|:-----:|
| 后端自由 | ✅ 任意OpenAI兼容 | ❌ 仅Anthropic | ✅ | ✅ |
| 纯本地零成本 | ✅ Ollama | ❌ 需API付费 | ✅ | ✅ |
| Agent子代理 | ✅ 内置 | ✅ | ❌ | ❌ |
| MCP扩展 | ✅ 内置 | ✅ | ❌ | ❌ |
| 智能路由 | ✅ auto-failover | ❌ | ❌ | ❌ |
| Voice语音 | ✅ | ✅ | ❌ | ❌ |
| Computer Use | ✅ 截图+浏览器 | ✅ | ❌ | ❌ |
| Hooks钩子 | ✅ pre/post/event | ✅ | ❌ | ❌ |
| Plan模式 | ✅ | ✅ | ❌ | ❌ |
| Worktree | ✅ | ✅ | ❌ | ❌ |
| 单文件分发 | ✅ 纯Python | ❌ Node.js | ❌ | ❌ |

## 快速开始

```bash
# 安装依赖
pip install requests

# 通用模式（推荐）— 配什么用什么
set HIVESHELL_API_URL=https://api.deepseek.com/v1/chat/completions
set HIVESHELL_API_KEY=sk-你的密钥
set HIVESHELL_MODEL=deepseek-chat
python hiveshell.py --custom

# DeepSeek官方快捷
set DEEPSEEK_API_KEY=sk-你的密钥
python hiveshell.py --deepseek

# Ollama纯本地（零成本·隐私安全）
python hiveshell.py --ollama
```

## 核心功能

### 24个内置工具
read_file | write_file | edit_file | search_knowledge_base | run_shell | glob_files | grep_content | get_hive_status | web_search | spawn_agents | mcp_status | notebook_read | notebook_edit | worktree_list | worktree_add | web_fetch | task_create | task_list | cron_create | cron_list | teammate_send | skill_import | screenshot | browse_web

### 智能路由层 v3.2
- auto-failover: 主模型挂了自动切换降级模型
- 复杂度选模型: 简单问题用小模型省钱，复杂问题用旗舰模型
- 多模型级联: Agent任务自动分配专用模型

### 15/15对标Claude Code
Plan模式 | Hooks钩子 | Skills技能 | Background Agents | Subagents并行 | CLAUDE.md | Worktree | 会话管理 | MCP | 工具调用 | Computer Use | Voice Mode | 记忆系统 | Web Fetch | Task系统

## 支持的后端

| 后端 | 命令 | 费用 | 特点 |
|------|------|------|------|
| 通用(任意API) | `--custom` | API按量 | 配什么用什么 |
| DeepSeek官方 | `--deepseek` | API按量 | 官方API |
| 硅基流动 | `--siliconflow` | API按量 | DeepSeek-V3.2 |
| 阿里百炼 | `--aliyun` | API按量 | Qwen3.7-Max |
| Ollama本地 | `--ollama` | **免费** | 100%本地·隐私 |

## 定价

| 版本 | 价格 | 说明 |
|------|------|------|
| 社区版 | **免费** (MIT开源) | GitHub开源，所有功能 |
| 专业版 | ¥49 永久买断 | 技术支持+优先更新 |

## 反馈与贡献

- 🐛 [提交Issue](https://github.com/qiming3344/hiveshell/issues)
- 📧 weiweilbj@163.com

---

**蜂巢AI实验室** | 自研·开放·隐私优先 | 壳是壳·模型是模型
