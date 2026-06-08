#!/usr/bin/env python3
"""
AiPy MCP Server — 将 AiPyPro 的 AI 任务执行能力暴露为 MCP 工具。

通过 stdio 与 MCP 客户端（如 Claude Code）通信，
内部调用 aipypro.exe 执行任务。

用法:
    uv run python server.py
    # 或安装后:
    aipy-mcp

环境变量:
    AIPYPRO_PATH     — aipypro.exe 的路径（默认自动检测）
    AIPYPRO_TIMEOUT  — 任务超时秒数（默认 300）
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# ---------------------------------------------------------------------------
# 配置 — 自动检测 aipypro.exe
# ---------------------------------------------------------------------------

def _find_aipypro() -> str:
    """自动检测 aipypro.exe 路径。

    检测顺序:
        1. 环境变量 AIPYPRO_PATH
        2. AiPyPro 安装目录下的 bin/aipypro.exe
        3. 系统 PATH 中的 aipypro / aipypro.exe
    """
    env_path = os.environ.get("AIPYPRO_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # AiPyPro 默认安装位置
    candidates = [
        r"E:\aipy\AiPyPro\resources\app.asar.unpacked\resources\bin\aipypro.exe",
        r"C:\Program Files\AiPyPro\resources\app.asar.unpacked\resources\bin\aipypro.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c

    # 尝试系统 PATH
    for cmd in ["aipypro.exe", "aipypro"]:
        try:
            result = subprocess.run(
                [cmd, "--help"],
                capture_output=True, text=True, timeout=5,
            )
            if "Python use" in (result.stdout + result.stderr):
                return cmd
        except Exception:
            pass

    raise FileNotFoundError(
        "找不到 aipypro.exe。\n"
        "请设置环境变量 AIPYPRO_PATH 指向 aipypro.exe，\n"
        "或安装 AiPyPro: https://www.aipy.app/"
    )


AIPYPRO = _find_aipypro()
TIMEOUT = int(os.environ.get("AIPYPRO_TIMEOUT", "300"))


# ---------------------------------------------------------------------------
# MCP Server 定义
# ---------------------------------------------------------------------------

server = Server("aipy-mcp")

TOOLS = [
    Tool(
        name="aipy_run",
        description=(
            "通过 AiPyPro 执行 AI 驱动的任务。\n"
            "\n"
            "AiPyPro 是一个遵循「No Agents, Code is Agent」理念的 AI Agent。"
            "它会将自然语言指令自主转化为 Python 代码并在本地执行，"
            "完成 Task → Plan → Code → Execute → Feedback 的完整闭环。\n"
            "\n"
            "适合用于:\n"
            "- 数据分析: Excel/CSV 统计、透视表、趋势分析\n"
            "- 文件处理: 批量重命名、格式转换、编码转换\n"
            "- 网页抓取: API 调用、HTML 解析、数据采集\n"
            "- 数据可视化: 生成 matplotlib/seaborn 图表\n"
            "- 自动化: 文件整理、系统操作、批量处理\n"
            "\n"
            "不适合: 修改项目代码（用 Claude Code 直接编辑）、"
            "浏览器交互（用 Chrome DevTools MCP）"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "自然语言任务描述。例如: '分析 sales.xlsx 销售额趋势'",
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "qa", "task"],
                    "default": "auto",
                    "description": "auto=自动判断, qa=仅问答不执行代码, task=强制任务模式",
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录路径（默认当前目录）",
                },
            },
            "required": ["instruction"],
        },
    ),
    Tool(
        name="aipy_python",
        description=(
            "通过 AiPyPro 的 Python 环境直接执行代码。\n"
            "与 aipy_run 不同，这不是通过 AI 生成代码，而是直接执行你提供的 Python 代码。\n"
            "适合已知确切代码逻辑、不需要 AI 规划的场景。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码",
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录路径（默认当前目录）",
                },
            },
            "required": ["code"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    cwd = arguments.get("cwd") or os.getcwd()

    if name == "aipy_run":
        instruction = arguments["instruction"]
        mode = arguments.get("mode", "auto")
        cmd = [AIPYPRO, "run", "-m", mode, instruction]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=TIMEOUT
            )

            out_text = stdout.decode("utf-8", errors="replace").strip()
            err_text = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                result = out_text or "任务执行完成（无输出）"
            else:
                result = (
                    f"⚠️ 任务执行失败 (exit code: {proc.returncode})\n\n"
                    f"--- STDOUT ---\n{out_text or '(无)'}\n\n"
                    f"--- STDERR ---\n{err_text or '(无)'}"
                )

        except asyncio.TimeoutError:
            result = f"⏱️ 任务超时（>{TIMEOUT}秒）: {instruction[:100]}..."

        return [TextContent(type="text", text=result)]

    elif name == "aipy_python":
        code = arguments["code"]
        cmd = [AIPYPRO, "python"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=code.encode("utf-8")),
                timeout=TIMEOUT,
            )

            out_text = stdout.decode("utf-8", errors="replace").strip()
            err_text = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                result = out_text or "代码执行完成（无输出）"
            else:
                result = (
                    f"⚠️ 执行失败 (exit code: {proc.returncode})\n\n"
                    f"--- STDOUT ---\n{out_text or '(无)'}\n\n"
                    f"--- STDERR ---\n{err_text or '(无)'}"
                )

        except asyncio.TimeoutError:
            result = f"⏱️ 执行超时（>{TIMEOUT}秒）"

        return [TextContent(type="text", text=result)]

    else:
        return [TextContent(type="text", text=f"未知工具: {name}")]


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    """MCP Server 入口 — stdio 传输模式。"""
    print(f"[aipy-mcp] 启动成功，aipypro: {AIPYPRO}", file=sys.stderr)
    print(f"[aipy-mcp] 超时设置: {TIMEOUT}s", file=sys.stderr)

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
