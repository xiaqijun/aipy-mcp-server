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
        2. 文件系统搜索（Windows 各盘符 / macOS / Linux 常见路径）
        3. 从 AiPyPro 配置文件推断
        4. 系统 PATH
    """
    # 1. 环境变量
    env_path = os.environ.get("AIPYPRO_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # 2. 文件系统搜索
    found = _search_filesystem()
    if found:
        return found

    # 3. 从 AiPyPro 配置推断
    found = _find_from_config()
    if found:
        return found

    # 4. 系统 PATH
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


def _search_filesystem() -> str | None:
    """在常见位置搜索 aipypro。"""
    exe_name = "aipypro.exe" if sys.platform == "win32" else "aipypro"

    if sys.platform == "win32":
        return _search_windows(exe_name)
    elif sys.platform == "darwin":
        return _search_macos(exe_name)
    else:
        return _search_linux(exe_name)


def _search_windows(exe_name: str) -> str | None:
    """Windows: 在所有盘符下搜索 AiPyPro 安装目录。"""
    import string

    # 常见子路径模式
    sub_path = r"resources\app.asar.unpacked\resources\bin"

    for drive in string.ascii_uppercase:
        root = f"{drive}:\\"
        if not Path(root).exists():
            continue

        # 精确匹配：<drive>:\aipy\AiPyPro\resources\...\bin\aipypro.exe
        candidate = Path(root) / "aipy" / "AiPyPro" / sub_path / exe_name
        if candidate.exists():
            return str(candidate)

        # 搜索 *AiPyPro* 目录
        try:
            drive_root = Path(root)
            for entry in drive_root.iterdir():
                if not entry.is_dir():
                    continue
                name = entry.name.lower()
                if "aipy" in name:
                    candidate = entry / sub_path / exe_name
                    if candidate.exists():
                        return str(candidate)
        except PermissionError:
            continue

        # 深度搜索（仅在 Program Files 和用户目录下）
        for base in [
            rf"{drive}:\Program Files",
            rf"{drive}:\Program Files (x86)",
            rf"{drive}:\Users",
        ]:
            base_path = Path(base)
            if not base_path.exists():
                continue
            try:
                for p in base_path.rglob(f"**/{exe_name}"):
                    if "AiPyPro" in str(p) or "aipy" in str(p).lower():
                        return str(p)
            except PermissionError:
                continue

    return None


def _search_macos(exe_name: str) -> str | None:
    """macOS: 搜索 Applications 目录。"""
    sub_path = "Contents/Resources/app.asar.unpacked/resources/bin"
    candidates = [
        Path(f"/Applications/AiPyPro.app/{sub_path}/{exe_name}"),
        Path.home() / f"Applications/AiPyPro.app/{sub_path}/{exe_name}",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    # 通配搜索
    for base in [Path("/Applications"), Path.home() / "Applications"]:
        if not base.exists():
            continue
        try:
            for p in base.rglob(f"*AiPyPro*/{sub_path}/{exe_name}"):
                return str(p)
        except PermissionError:
            continue

    return None


def _search_linux(exe_name: str) -> str | None:
    """Linux: 搜索常见安装目录。"""
    candidates = [
        f"/opt/AiPyPro/resources/app.asar.unpacked/resources/bin/{exe_name}",
        f"/usr/local/bin/{exe_name}",
        f"/usr/local/share/AiPyPro/resources/app.asar.unpacked/resources/bin/{exe_name}",
    ]
    for c in candidates:
        if Path(c).exists():
            return c

    # 搜索 home 目录
    home = Path.home()
    for pattern in [".local/bin", "Applications", "apps"]:
        base = home / pattern
        if not base.exists():
            continue
        try:
            for p in base.rglob(f"**/{exe_name}"):
                if "aipy" in str(p).lower():
                    return str(p)
        except PermissionError:
            continue

    return None


def _find_from_config() -> str | None:
    """从 AiPyPro 配置文件中推断安装路径。"""
    config_dir = Path.home() / ".aipyapp"
    if not config_dir.exists():
        return None

    # 从日志中提取路径信息
    log_file = config_dir / "aipyapp.log"
    if log_file.exists():
        try:
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            import re
            match = re.search(r'([A-Za-z]:[^"\'\s]*aipypro\.exe)', content)
            if match and Path(match.group(1)).exists():
                return match.group(1)
        except Exception:
            pass

    return None


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
