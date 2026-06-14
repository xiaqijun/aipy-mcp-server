#!/usr/bin/env python3
"""
AiPy MCP Server — 直接集成 AiPyPro 源码，暴露 AI 任务执行能力为 MCP 工具。

与旧版的区别:
- 旧版: 通过 subprocess 调用 aipypro.exe
- 新版: 直接 import aipyapp，零开销调用 AI-PY 内核

用法:
    uv run python server.py

环境变量:
    AIPYAPP_PATH       — aipyapp 源码目录 (必需)
    AIPYAPP_CONFIG_DIR — AiPyPro 配置目录 (默认 ~/.aipyapp)
    AIPYAPP_PROVIDER   — LLM provider JSON (默认从 AiPyPro 配置读取)
    AIPYAPP_TIMEOUT    — 任务超时秒数 (默认 600)
"""

from __future__ import annotations

import asyncio
import os
import sys
import json
import threading
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ---------------------------------------------------------------------------
# 源码路径解析
# ---------------------------------------------------------------------------

# Electron app 内 aipyapp 源码的相对路径
_AIPYAPP_SUB = Path("resources/app.asar.unpacked/resources/aipyapp")


def _resolve_aipyapp_path() -> Path:
    """解析 aipyapp 源码目录（返回包含 aipyapp/__init__.py 的父目录）。

    检测顺序 (任一命中即返回):
        1. 环境变量 AIPYAPP_PATH
        2. pip 安装的 aipyapp 包 (importlib)
        3. ~/.aipyapp 日志/配置中的路径线索
        4. Windows / WSL 常见安装位置遍历
    """
    # 1. 环境变量
    env = os.environ.get("AIPYAPP_PATH", "")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "aipyapp" / "__init__.py").exists():
            return p
        if (p / "__init__.py").exists() and p.name == "aipyapp":
            return p.parent

    # 2. pip 安装
    found = _find_pip()
    if found:
        return found

    # 3. 配置文件/日志线索
    found = _find_from_aipy_config()
    if found:
        return found

    # 4. 系统搜索
    found = _search_filesystem()
    if found:
        return found

    raise FileNotFoundError(
        "找不到 aipyapp 源码目录。\n"
        "请设置环境变量 AIPYAPP_PATH 指向 aipyapp 源码目录，或安装 AiPyPro。\n"
        "示例: AIPYAPP_PATH=E:/aipy/AiPyPro/resources/app.asar.unpacked/resources/aipyapp\n"
        "下载: https://www.aipy.app/"
    )


def _is_aipyapp_root(p: Path) -> bool:
    """检查路径是否包含 aipyapp/__init__.py。"""
    return (p / "aipyapp" / "__init__.py").exists()


def _find_pip() -> Path | None:
    """通过 importlib 查找 pip 安装的 aipyapp。"""
    try:
        from importlib.util import find_spec
        spec = find_spec("aipyapp")
        if spec and spec.origin:
            origin = Path(spec.origin)  # .../aipyapp/__init__.py
            if origin.name == "__init__.py" and origin.parent.name == "aipyapp":
                return origin.parent.parent
    except (ImportError, ValueError, AttributeError):
        pass
    return None


def _find_from_aipy_config() -> Path | None:
    """从 ~/.aipyapp 配置/日志中提取 aipypro.exe 路径，反推源码目录。"""
    config_dir = Path.home() / ".aipyapp"
    if not config_dir.is_dir():
        return None

    # 从日志中提取 aipypro.exe 路径
    log_file = config_dir / "aipyapp.log"
    if log_file.exists():
        try:
            import re
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            # 匹配 Windows 绝对路径中的 aipypro.exe
            for m in re.finditer(r'([A-Za-z]:[^\s"\']*?aipypro\.exe)', content):
                exe = Path(m.group(1))
                if exe.exists():
                    # exe 在 resources/.../bin/aipypro.exe，回到 aipyapp 父目录
                    src = exe.parent.parent / "aipyapp"  # bin/../aipyapp
                    if _is_aipyapp_root(src):
                        return src
                    # 尝试更上级
                    for ancestor in exe.parents:
                        if _is_aipyapp_root(ancestor):
                            return ancestor
        except Exception:
            pass

    # 从配置文件推断
    toml_file = config_dir / "aipyapp.toml"
    if toml_file.exists():
        try:
            import tomllib
            cfg = tomllib.loads(toml_file.read_text(encoding="utf-8"))
            install_path = cfg.get("install_path") or cfg.get("app_path")
            if install_path:
                p = Path(install_path) / _AIPYAPP_SUB
                if _is_aipyapp_root(p):
                    return p
        except Exception:
            pass

    return None


def _search_filesystem() -> Path | None:
    """遍历常见安装位置搜索 AiPyPro Electron 目录。"""
    if sys.platform == "win32":
        return _search_windows()
    # WSL / Linux: 通过 /mnt 访问 Windows 盘符
    mnt = Path("/mnt")
    if mnt.exists():
        return _search_wsl(mnt)
    return None


# ---------------------------------------------------------------------------
# Windows 搜索
# ---------------------------------------------------------------------------

def _search_windows() -> Path | None:
    """Windows: 遍历所有盘符的常见安装目录。"""
    import string, os as _os

    for drive in string.ascii_uppercase:
        root = Path(f"{drive}:\\")
        if not root.exists():
            continue

        # --- 常见安装目录(按优先级) ---
        search_roots: list[Path] = [
            # 默认安装路径
            root / "aipy",
            # 标准 Windows 安装
            root / "Program Files",
            root / "Program Files (x86)",
        ]

        # 用户目录下的安装
        for env_var in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
            val = _os.environ.get(env_var, "")
            if val:
                p = Path(val)
                if p.exists() and p.drive.rstrip("\\").upper() == f"{drive}:":
                    search_roots.append(p)

        # 在每个 search_root 下查找 *AiPyPro* 或 *aipy* 目录
        for base in search_roots:
            if not base.exists():
                continue
            result = _scan_dir_for_aipyapp(base, max_depth=3)
            if result:
                return result

        # 盘符根目录兜底：aipy/AiPyPro 或 *aipy*/
        result = _scan_dir_for_aipyapp(root, max_depth=2)
        if result:
            return result

    return None


def _scan_dir_for_aipyapp(base: Path, max_depth: int) -> Path | None:
    """在 base 下扫描 AiPyPro 安装目录，找到则返回 aipyapp 父目录。"""
    if max_depth <= 0:
        return None

    # 直接检查 base 自身
    # base / AiPyPro / resources/app.asar.unpacked/resources/aipyapp
    for top_name in ("AiPyPro", "AiPy", "aipypro", "aipy-app"):
        candidate = base / top_name / _AIPYAPP_SUB
        if _is_aipyapp_root(candidate):
            return candidate

    # 通配：base 下含 "aipy" 的目录
    try:
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            name_lower = entry.name.lower()
            if "aipy" in name_lower or "ai-py" in name_lower:
                # 直接匹配
                candidate = entry / _AIPYAPP_SUB
                if _is_aipyapp_root(candidate):
                    return candidate
                # 再深一层: entry / AiPyPro / sub
                candidate2 = entry / "AiPyPro" / _AIPYAPP_SUB
                if _is_aipyapp_root(candidate2):
                    return candidate2
                # 子目录通配
                if max_depth > 1:
                    try:
                        for sub_entry in entry.iterdir():
                            if sub_entry.is_dir() and "aipy" in sub_entry.name.lower():
                                c = sub_entry / _AIPYAPP_SUB
                                if _is_aipyapp_root(c):
                                    return c
                    except PermissionError:
                        continue
    except PermissionError:
        pass

    # 递归进入子目录 (深度有限)
    if max_depth > 1:
        try:
            for entry in base.iterdir():
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                if entry.name.lower() in ("windows", "windowsapps", "windows nt", "system volume information"):
                    continue
                if "aipy" not in entry.name.lower():
                    continue
                result = _scan_dir_for_aipyapp(entry, max_depth - 1)
                if result:
                    return result
        except PermissionError:
            pass

    return None


# ---------------------------------------------------------------------------
# WSL 搜索
# ---------------------------------------------------------------------------

def _search_wsl(mnt: Path) -> Path | None:
    """WSL: 遍历 /mnt/{c..h} 下的常见安装目录。"""
    import os as _os

    for d in "cdefgh":
        drive_root = mnt / d
        if not drive_root.exists():
            continue

        # 常见安装目录
        search_roots: list[Path] = [
            drive_root / "aipy",
            drive_root / "Program Files",
            drive_root / "Program Files (x86)",
        ]

        # Windows 用户目录映射到 WSL
        for wenv in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
            val = _os.environ.get(wenv, "")
            if val:
                # Windows 路径 → WSL 路径
                wsl_path = _win_to_wsl(val, mnt)
                if wsl_path and wsl_path.exists():
                    search_roots.append(wsl_path)

        for base in search_roots:
            if not base.exists():
                continue
            result = _scan_dir_for_aipyapp(base, max_depth=3)
            if result:
                return result

        # 兜底扫描
        result = _scan_dir_for_aipyapp(drive_root, max_depth=2)
        if result:
            return result

    return None


def _win_to_wsl(win_path: str, mnt: Path) -> Path | None:
    """将 Windows 绝对路径转为 WSL /mnt 路径。"""
    try:
        p = Path(win_path)
        parts = p.parts
        if len(parts) >= 2 and len(parts[0]) == 2 and parts[0][1] == ":":
            drive_letter = parts[0][0].lower()
            return mnt / drive_letter / Path(*parts[1:])
    except Exception:
        pass
    return None

AIPYAPP_PATH = _resolve_aipyapp_path()

# 将 aipyapp 添加到 sys.path
_aipyapp_parent = str(AIPYAPP_PATH)
if _aipyapp_parent not in sys.path:
    sys.path.insert(0, _aipyapp_parent)

# ---------------------------------------------------------------------------
# 延迟导入 aipyapp (在 _init_aipy 中调用，确保路径就绪)
# ---------------------------------------------------------------------------

_aipy_imports: dict[str, Any] = {}
_init_lock = threading.Lock()
_initialized = False

def _init_aipy():
    """初始化 AI-PY 内核 (TaskManager, DisplayManager 等)。

    线程安全，仅初始化一次。
    """
    global _initialized, _aipy_imports

    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        # ---- 临时抑制 loguru，避免污染 stdio ----
        try:
            from loguru import logger
            logger.remove()
        except ImportError:
            pass

        # ---- 导入 aipyapp 核心模块 ----
        from aipyapp.aipy.config import CONFIG_DIR, ConfigManager
        from aipyapp.aipy.taskmgr import TaskManager
        from aipyapp.aipy.unified_agent import UnifiedAgent, TaskSwitchRequest
        from aipyapp.display import DisplayManager
        from aipyapp.interface import Event

        # ---- 配置 ----
        config_dir = os.environ.get("AIPYAPP_CONFIG_DIR", str(CONFIG_DIR))
        config_manager = ConfigManager(config_dir)

        settings = _build_settings(config_manager)

        # ---- Display Manager (MCP 定制插件) ----
        display_config = {"style": "mcp", "quiet": True}
        display_manager = DisplayManager(display_config, record=False, quiet=True)
        display_manager.register_plugin(MCPDisplayPlugin, name="mcp")

        # ---- TaskManager ----
        tm = TaskManager(settings, display_manager=display_manager)

        # 特性开关: 启用 subtask / exec_code，禁用不需要的功能
        role = tm.role_manager.current_role
        role.features["subtask"] = False
        role.features["survey"] = False
        role.features["aipy_call"] = True
        role.features["openai_call"] = False
        role.features["exec_code"] = True

        _aipy_imports = {
            "config_manager": config_manager,
            "settings": settings,
            "display_manager": display_manager,
            "tm": tm,
            "UnifiedAgent": UnifiedAgent,
            "TaskSwitchRequest": TaskSwitchRequest,
            "Event": Event,
        }

        _initialized = True


def _build_settings(config_manager) -> dict:
    """构建 AI-PY settings 字典。"""
    conf = config_manager.config
    from aipyapp.aipy.config import CONFIG_DIR
    from aipyapp.i18n import set_lang

    settings = dict(conf)
    settings["workdir"] = str(CONFIG_DIR / "work")
    settings["gui"] = False
    settings["auto_install"] = True
    settings["auto_getenv"] = True
    settings["lang"] = os.environ.get("AIPYAPP_LANG", "zh")
    set_lang(settings["lang"])
    settings["role"] = "aipy"
    settings["max_rounds"] = int(os.environ.get("AIPYAPP_MAX_ROUNDS", "32"))
    settings["timeout"] = 0
    settings["share_result"] = False
    settings["diagnose"] = {"enabled": False}
    settings["skills"] = {"enabled": True}
    settings["config_manager"] = config_manager

    # LLM Provider: 优先环境变量, 其次 AiPyPro 配置
    provider_env = os.environ.get("AIPYAPP_PROVIDER", "")
    if provider_env:
        try:
            provider = json.loads(provider_env)
        except json.JSONDecodeError:
            provider = {"name": "trustoken", "type": "trust", "api_key": provider_env}
    else:
        provider = settings.get("provider",
            {"name": "trustoken", "type": "trust", "api_key": "xyz"})

    settings["llm"] = {
        provider.get("name", "trustoken"): {
            **provider,
            "enable": True,
            "default": True,
        }
    }

    # MCP (不使用 sys MCP)
    settings["mcp"] = {"sys_mcp_enabled": False}

    # 环境变量注入
    envs = settings.get("environ", {})
    for name, value in envs.items():
        os.environ[name] = str(value)

    return settings


# ---------------------------------------------------------------------------
# MCP 定制 Display Plugin — 收集 AI-PY 输出文本
# ---------------------------------------------------------------------------

class MCPDisplayPlugin:
    """MCP 专用的 Display Plugin。

    不输出到终端，而是将 AI 回复文本收集到缓冲区，供 MCP 工具返回。
    与 StdioDisplayPlugin 的 JSON 事件流不同，这里只提取纯文本内容。
    """
    name = "mcp"
    version = "1.0.0"
    description = "MCP Display Plugin — collects AI output for MCP tools"
    author = "AiPy MCP Team"

    # --- 类级存储 (thread-local 不够，因为跨线程访问) ---
    _storage: dict[str, list[str]] = {}  # task_id -> [text chunks]
    _lock = threading.Lock()

    def __init__(self, console=None, quiet: bool = False):
        self.console = console
        self.quiet = quiet
        self._current_task_id: str | None = None

    @staticmethod
    def new_collector(task_id: str):
        """为指定 task_id 创建新的文本收集器。"""
        with MCPDisplayPlugin._lock:
            MCPDisplayPlugin._storage[task_id] = []

    @staticmethod
    def get_text(task_id: str) -> str:
        """获取并清除指定 task_id 的收集文本。"""
        with MCPDisplayPlugin._lock:
            chunks = MCPDisplayPlugin._storage.pop(task_id, [])
        return "\n".join(chunks)

    # --- DisplayPlugin 接口 ---

    def save(self, path: str, clear: bool = False, code_format: str = ""):
        pass

    def print(self, message: str, style: str = ""):
        pass

    def input(self, prompt: str) -> str:
        return ""

    def confirm(self, prompt, default="n", auto=None):
        return True

    # --- event handlers ---

    def _emit_text(self, text: str):
        if not text or not text.strip():
            return
        # 使用全局 task_id fallback
        tid = self._current_task_id or "__global__"
        with MCPDisplayPlugin._lock:
            if tid not in MCPDisplayPlugin._storage:
                MCPDisplayPlugin._storage[tid] = []
            MCPDisplayPlugin._storage[tid].append(text.strip())

    def on_exception(self, event):
        msg = event.data.get("msg", "")
        exc = event.data.get("exception", "")
        self._emit_text(f"[ERROR] {msg}\n{exc}")

    def on_request_started(self, event):
        pass

    def on_stream_started(self, event):
        pass

    def on_stream(self, event):
        # 流式输出暂不收集 (量大且重复)
        pass

    def on_parse_reply_completed(self, event):
        data = event.data
        response = data.get("response", {}) or {}
        message = response.get("message", {}) or {}
        msg = message.get("message", {}) or {}
        content = msg.get("content", "")
        if content and isinstance(content, str) and content.strip():
            self._emit_text(content.strip())

    def on_function_call_started(self, event):
        pass

    def on_function_call_completed(self, event):
        pass

    def on_tool_call_started(self, event):
        pass

    def on_tool_call_completed(self, event):
        pass

    def on_step_completed(self, event):
        data = event.data
        summary = data.get("summary", {}) or {}
        s = summary.get("summary", "")
        if s:
            self._emit_text(str(s))

    def on_task_start(self, event):
        pass

    def on_task_end(self, event):
        pass

    def on_response_complete(self, event):
        pass

    def on_call_function(self, event):
        pass

    def on_exec_result(self, event):
        pass

    def on_query_start(self, event):
        pass

    def on_round_start(self, event):
        pass

    def on_round_end(self, event):
        pass

    def on_parse_reply(self, event):
        pass

    def on_exec(self, event):
        pass

    def on_mcp_result(self, event):
        pass

    def on_mcp_call(self, event):
        pass

    def on_upload_result(self, event):
        pass

    def on_runtime_message(self, event):
        msg = event.data.get("message", "")
        if msg:
            self._emit_text(str(msg))

    def on_runtime_input(self, event):
        pass

    def on_show_image(self, event):
        pass

    def on_stream_end(self, event):
        pass

    def on_stream_completed(self, event):
        pass

    @classmethod
    def get_type(cls):
        from aipyapp.plugin import PluginType
        return PluginType.DISPLAY

    def init(self):
        pass

    def get_handlers(self):
        return {
            "exception": self.on_exception,
            "request_started": self.on_request_started,
            "stream_started": self.on_stream_started,
            "stream": self.on_stream,
            "stream_completed": self.on_stream_completed,
            "parse_reply_completed": self.on_parse_reply_completed,
            "function_call_started": self.on_function_call_started,
            "function_call_completed": self.on_function_call_completed,
            "tool_call_started": self.on_tool_call_started,
            "tool_call_completed": self.on_tool_call_completed,
            "step_completed": self.on_step_completed,
            "task_start": self.on_task_start,
            "task_end": self.on_task_end,
            "response_complete": self.on_response_complete,
            "call_function": self.on_call_function,
            "exec_result": self.on_exec_result,
            "query_start": self.on_query_start,
            "round_start": self.on_round_start,
            "round_end": self.on_round_end,
            "parse_reply": self.on_parse_reply,
            "exec": self.on_exec,
            "mcp_result": self.on_mcp_result,
            "mcp_call": self.on_mcp_call,
            "upload_result": self.on_upload_result,
            "runtime_message": self.on_runtime_message,
            "runtime_input": self.on_runtime_input,
            "show_image": self.on_show_image,
        }


# ---------------------------------------------------------------------------
# 核心执行函数
# ---------------------------------------------------------------------------

TIMEOUT = int(os.environ.get("AIPYAPP_TIMEOUT", "600"))


def _run_task(instruction: str, mode: str, cwd: str) -> str:
    """在独立线程中执行 AI-PY 任务 (同步阻塞)。

    由 asyncio.to_thread() 调用, 不阻塞 MCP 事件循环。
    """
    _init_aipy()

    tm = _aipy_imports["tm"]
    UnifiedAgent = _aipy_imports["UnifiedAgent"]
    TaskSwitchRequest = _aipy_imports["TaskSwitchRequest"]

    task_id = f"mcp_{id(instruction)}_{hash(instruction) & 0xFFFFFFFF:08x}"
    MCPDisplayPlugin.new_collector(task_id)

    # 调整工作目录
    target_cwd = Path(cwd).expanduser().resolve() if cwd else tm.cwd
    if target_cwd.exists():
        os.chdir(str(target_cwd))

    result_parts: list[str] = []

    try:
        if mode in ("auto", "qa"):
            # ---- UnifiedAgent: 自动路由 QA / Task ----
            agent = UnifiedAgent(
                tm.settings,
                display_manager=_aipy_imports["display_manager"],
                enable_task=(mode != "qa"),
                task_manager=tm,
            )

            # 收集流式输出
            stream_chunks: list[str] = []

            def _on_stream(event):
                lines = getattr(event, "lines", None) or []
                if lines:
                    stream_chunks.append("\n".join(lines))

            def _on_parse_reply(event):
                data = event.data
                response = data.get("response", {}) or {}
                msg = response.get("message", {}) or {}
                content = (msg.get("message", {}) or {}).get("content", "")
                if content and isinstance(content, str):
                    nonlocal stream_chunks
                    stream_chunks = []  # 清空流式缓存，用最终结果
                    result_parts.append(content.strip())

            agent.on_event("stream", _on_stream)
            agent.on_event("parse_reply_completed", _on_parse_reply)

            result = agent.run(instruction)

            if isinstance(result, TaskSwitchRequest):
                # UnifiedAgent 决定启动任务模式
                result_parts.append(_run_full_task(result.task, result.instruction))
            elif not result_parts and stream_chunks:
                result_parts.append("\n".join(stream_chunks))
            elif not result_parts and hasattr(result, "content") and result.content:
                result_parts.append(str(result.content))

        else:
            # ---- task 模式: 直接创建 Task ----
            task = tm.new_task()
            result_parts.append(_run_full_task(task, instruction))

    except Exception as e:
        import traceback
        result_parts.append(f"[ERROR] 任务执行异常:\n{traceback.format_exc()}")

    # 合并结果
    display_text = MCPDisplayPlugin.get_text(task_id)
    if display_text:
        result_parts.append(display_text)

    final = "\n\n".join(filter(None, result_parts)).strip()
    return final or "任务执行完成（无输出）"


def _run_full_task(task, instruction: str) -> str:
    """执行完整 Task 循环并收集结果。"""
    from aipyapp.aipy.chat import ChatMessage

    task_id = task.task_id
    collected: list[str] = []

    # 注册事件监听，从 task 的 event_bus 获取最终回复
    def _on_parse_reply(event):
        data = event.data
        response = data.get("response", {}) or {}
        msg = response.get("message", {}) or {}
        inner = msg.get("message", {}) or {}
        content = inner.get("content", "")
        if content and isinstance(content, str) and content.strip():
            collected.append(content.strip())

    def _on_step_completed(event):
        data = event.data
        summary = data.get("summary", {}) or {}
        s = summary.get("summary", "")
        if s:
            collected.append(str(s))

    task.event_bus.on_event("parse_reply_completed", _on_parse_reply)
    task.event_bus.on_event("step_completed", _on_step_completed)

    try:
        task.run(instruction)
        task.done()
    except (EOFError, KeyboardInterrupt):
        pass
    except Exception:
        import traceback
        collected.append(f"[ERROR] {traceback.format_exc()}")

    return "\n".join(collected)


def _run_python(code: str, cwd: str) -> str:
    """通过 AI-PY Python Runtime 直接执行代码。"""
    _init_aipy()

    import io
    from contextlib import redirect_stdout, redirect_stderr

    target_cwd = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
    if target_cwd.exists():
        os.chdir(str(target_cwd))

    buf_out = io.StringIO()
    buf_err = io.StringIO()

    try:
        # 编译代码
        compiled = compile(code, "<aipy_python>", "exec")

        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            namespace: dict[str, Any] = {}
            exec(compiled, namespace)

        out = buf_out.getvalue().strip()
        err = buf_err.getvalue().strip()

        if err:
            return f"[stderr]\n{err}\n\n[stdout]\n{out}" if out else f"[stderr]\n{err}"
        return out or "代码执行完成（无输出）"

    except Exception:
        import traceback
        tb = traceback.format_exc()
        out = buf_out.getvalue().strip()
        err = buf_err.getvalue().strip()
        parts = [tb]
        if out:
            parts.append(f"[stdout]\n{out}")
        if err:
            parts.append(f"[stderr]\n{err}")
        return "\n\n".join(parts)


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
            "AiPyPro 遵循「No Agents, Code is Agent」理念。"
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

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_run_task, instruction, mode, cwd),
                timeout=TIMEOUT,
            )
        except asyncio.TimeoutError:
            result = f"⏱️ 任务超时 (>{TIMEOUT}秒): {instruction[:100]}..."

        return [TextContent(type="text", text=result)]

    elif name == "aipy_python":
        code = arguments["code"]

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_run_python, code, cwd),
                timeout=TIMEOUT,
            )
        except asyncio.TimeoutError:
            result = f"⏱️ 执行超时 (>{TIMEOUT}秒)"

        return [TextContent(type="text", text=result)]

    else:
        return [TextContent(type="text", text=f"未知工具: {name}")]


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    """MCP Server 入口 — stdio 传输模式。"""
    print(f"[aipy-mcp] aipyapp 源码: {AIPYAPP_PATH}", file=sys.stderr)
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
