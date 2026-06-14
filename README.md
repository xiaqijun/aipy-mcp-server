# AiPy MCP Server

直接将 [AiPyPro](https://www.aipy.app/) 的 AI 任务执行内核暴露为 MCP 工具，
让 Claude Code 等 MCP 客户端可以直接调用。

## 核心理念

AiPyPro 遵循 **「No Agents, Code is Agent」**——
AI 直接写 Python 代码在本地执行，完成 Task → Plan → Code → Execute → Feedback 的完整闭环。

**本 MCP Server 直接 import aipyapp 源码执行，零 subprocess 开销。**

## 安装

### 前置条件

1. 安装 [AiPyPro](https://www.aipy.app/) 桌面应用（或拥有 aipyapp 源码）
2. Python >= 3.11

### 方式一：uv tool install（推荐）

```bash
uv tool install git+https://github.com/xiaqijun/aipy-mcp-server.git
```

### 方式二：源码开发

```bash
git clone https://github.com/xiaqijun/aipy-mcp-server.git
cd aipy-mcp-server

# 安装依赖（包括 aipyapp 运行时依赖）
uv sync
```

## Claude Code 配置

在目标项目的 `.mcp.json` 中添加：

```json
{
  "mcpServers": {
    "aipy": {
      "command": "uv",
      "args": ["run", "--directory", "E:/github/aipy-mcp-server", "python", "server.py"],
      "env": {
        "AIPYAPP_PATH": "E:/aipy/AiPyPro/resources/app.asar.unpacked/resources/aipyapp"
      }
    }
  }
}
```

> `AIPYAPP_PATH` 指向 aipyapp 源码目录。服务器启动时会自动检测 Windows 各盘符下
> `aipy/AiPyPro/resources/app.asar.unpacked/resources/aipyapp` 路径。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AIPYAPP_PATH` | aipyapp 源码目录 | 自动检测 |
| `AIPYAPP_CONFIG_DIR` | AiPyPro 配置目录 | `~/.aipyapp` |
| `AIPYAPP_PROVIDER` | LLM provider JSON 配置 | 从 AiPyPro 配置读取 |
| `AIPYAPP_TIMEOUT` | 任务超时秒数 | 600 |
| `AIPYAPP_LANG` | 语言 (zh/en) | zh |
| `AIPYAPP_MAX_ROUNDS` | 最大执行轮数 | 32 |

### 自定义 LLM Provider

```json
{
  "env": {
    "AIPYAPP_PROVIDER": "{\"name\":\"openai\",\"type\":\"openai\",\"api_key\":\"sk-xxx\",\"base_url\":\"https://api.openai.com/v1\",\"model\":\"gpt-4o\"}"
  }
}
```

或使用 Trustoken（默认）:

```json
{
  "env": {
    "AIPYAPP_PROVIDER": "{\"name\":\"trustoken\",\"type\":\"trust\",\"api_key\":\"your-trustoken-api-key\"}"
  }
}
```

## 可用工具

### aipy_run — 执行 AI 任务

自然语言描述任务，AiPyPro 自主规划、编码、执行。

| 参数 | 说明 |
|------|------|
| `instruction` (必填) | 任务描述 |
| `mode` (可选) | `auto`(默认) / `qa`(仅问答) / `task`(强制执行) |
| `cwd` (可选) | 工作目录 |

### aipy_python — 执行 Python 代码

直接执行 Python 代码，不经过 AI 规划。

| 参数 | 说明 |
|------|------|
| `code` (必填) | Python 代码 |
| `cwd` (可选) | 工作目录 |

## 架构

```
┌──────────────────┐     MCP stdio     ┌──────────────────┐
│  Claude Code     │ ◄──────────────► │  aipy-mcp-server │
│  (MCP Client)    │                   │  (MCP Server)    │
└──────────────────┘                   └────────┬─────────┘
                                                │
                                    直接 import aipyapp
                                                │
                                   ┌────────────▼─────────┐
                                   │  aipyapp 内核         │
                                   │  ├─ TaskManager       │
                                   │  ├─ UnifiedAgent      │
                                   │  ├─ ClientManager     │
                                   │  ├─ CliPythonRuntime  │
                                   │  └─ Display Plugins   │
                                   └──────────────────────┘
```

与旧版 (v0.1.x) 的区别：
- **旧版**: 通过 subprocess 调用 `aipypro.exe`，每次任务需启动独立进程
- **新版**: 直接 import aipyapp 模块，在同一进程中执行，零进程启动开销

## Skill

项目自带 [SKILL.md](SKILL.md)，复制到目标项目的 `.claude/skills/aipy/` 下即可。

## 许可

MIT
