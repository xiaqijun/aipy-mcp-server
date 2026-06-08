# AiPy MCP Server

将 [AiPyPro](https://www.aipy.app/) 的 AI 任务执行能力包装为 MCP 工具，
让 Claude Code 等 MCP 客户端可以直接调用。

## 核心理念

AiPyPro 遵循 **「No Agents, Code is Agent」**  ——
AI 直接写 Python 代码在本地执行，完成 Task → Plan → Code → Execute → Feedback 的完整闭环。

## 快速开始

```bash
# 1. 安装依赖
cd E:\github\aipy-mcp-server
uv sync

# 2. 验证
uv run python -c "from server import AIPYPRO, TOOLS; print('OK:', AIPYPRO)"

# 3. 在 Claude Code 中注册（项目根目录创建 .mcp.json）
```

## Claude Code 配置

在项目根目录的 `.mcp.json` 中添加:

```json
{
  "mcpServers": {
    "aipy": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "E:/github/aipy-mcp-server",
        "python",
        "server.py"
      ],
      "description": "AiPyPro — AI-powered Python task execution"
    }
  }
}
```

然后在 `.claude/settings.local.json` 添加权限:

```json
"mcp__aipy__aipy_run",
"mcp__aipy__aipy_python",
"mcp__aipy__list_tools",
"mcp__aipy__call_tool"
```

## 可用工具

### aipy_run — 执行 AI 任务

自然语言描述任务，AiPyPro 自主规划、编码、执行。

```
参数:
  instruction (必填) - 任务描述
  mode (可选)        - auto | qa | task
  cwd (可选)         - 工作目录
```

示例:
```
> 帮我分析 data/sales.xlsx 中销售额最高的10个产品
> 下载 https://example.com/api/data 的 JSON 并转为 CSV
> 批量重命名当前目录下所有 .jpg 文件按拍摄日期排序
```

### aipy_python — 执行 Python 代码

直接执行 Python 代码，不经过 AI 规划。

```
参数:
  code (必填) - Python 代码
  cwd (可选)  - 工作目录
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `AIPYPRO_PATH` | aipypro.exe 路径 | 自动检测 |
| `AIPYPRO_TIMEOUT` | 任务超时秒数 | 300 |

## 适用场景

| ✅ 适合 | ❌ 不适合 |
|---|---|
| 数据分析 (Excel/CSV) | 浏览器交互 |
| 文件处理/格式转换 | 修改项目源代码 |
| 网页抓取/API 调用 | 纯文本问答 |
| 数据可视化 (图表) | GUI 操作 |
| 自动化脚本 | — |

## 许可

MIT
