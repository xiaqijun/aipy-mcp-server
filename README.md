# AiPy MCP Server

将 [AiPyPro](https://www.aipy.app/) 的 AI 任务执行能力包装为 MCP 工具，
让 Claude Code 等 MCP 客户端可以直接调用。

## 核心理念

AiPyPro 遵循 **「No Agents, Code is Agent」**——
AI 直接写 Python 代码在本地执行，完成 Task → Plan → Code → Execute → Feedback 的完整闭环。

## 安装

### 方式一：uv tool install（推荐）

```bash
uv tool install git+https://github.com/xiaqijun/aipy-mcp-server.git
```

安装后 `aipy-mcp` 命令全局可用。

### 方式二：pip install

```bash
pip install git+https://github.com/xiaqijun/aipy-mcp-server.git
```

### 方式三：uvx 免安装运行

无需安装，直接在 `.mcp.json` 中使用 `uvx` 一行运行（见下方配置）。

### 方式四：源码开发

```bash
git clone https://github.com/xiaqijun/aipy-mcp-server.git
cd aipy-mcp-server
uv sync
```

## Claude Code 配置

在目标项目的 `.mcp.json` 中添加：

```json
{
  "mcpServers": {
    "aipy": {
      "command": "aipy-mcp"
    }
  }
}
```

> `AIPYPRO_PATH` 无需手动配置。服务器会自动在所有盘符和常见路径中搜索 `aipypro.exe`。
> 仅在自动检测失败时才需要设置 `env.AIPYPRO_PATH`。

如果使用 uvx 免安装（替换上面的 command/args）：

```json
{
  "mcpServers": {
    "aipy": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/xiaqijun/aipy-mcp-server.git", "aipy-mcp"]
    }
  }
}
```

如果使用源码开发：

```json
{
  "mcpServers": {
    "aipy": {
      "command": "uv",
      "args": ["run", "--directory", "E:/github/aipy-mcp-server", "python", "server.py"]
    }
  }
}
```

## 可用工具

### aipy_run — 执行 AI 任务

自然语言描述任务，AiPyPro 自主规划、编码、执行。

| 参数 | 说明 |
|---|---|
| `instruction` (必填) | 任务描述 |
| `mode` (可选) | `auto`(默认) / `qa` / `task` |
| `cwd` (可选) | 工作目录 |

### aipy_python — 执行 Python 代码

直接执行 Python 代码，不经过 AI 规划。

| 参数 | 说明 |
|---|---|
| `code` (必填) | Python 代码 |
| `cwd` (可选) | 工作目录 |

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `AIPYPRO_PATH` | aipypro.exe 路径 | 自动检测 |
| `AIPYPRO_TIMEOUT` | 任务超时秒数 | 300 |

## Skill

项目自带 [SKILL.md](SKILL.md)，复制到目标项目的 `.claude/skills/aipy/` 下即可。
Skill 规则：**仅当用户输入中明确提到 aipy/AiPyPro 时才触发调用**，其他情况不自动调用。

## 许可

MIT
