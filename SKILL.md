---
name: aipy
description: 仅当用户输入中包含 aipy/AiPyPro/aipypro 等触发词，或用户说"用/使用/调用/让 aipy"时才激活
---

# AiPyPro Skill

## 何时调用 — 决策树

```
用户消息中是否包含 aipy/AiPyPro 触发词？
  │
  ├─ ❌ 没有 → 不调用。用 Claude Code 正常处理。
  │
  └─ ✅ 有 → 调用 aipy_run。不要自己分析、不要自己写代码。
            │
            ├─ 用户说 "aipy python / aipy 执行代码" → aipy_python(code="...")
            ├─ 用户纯粹问知识/概念 ("aipy 什么是...") → aipy_run(mode="qa")
            └─ 其余 → aipy_run(mode="auto")
```

## 触发词

以下任一出现就触发（大小写不敏感）：

- `aipy` / `AiPy` / `AIPY`
- `aipy pro` / `AiPyPro` / `aipypro`
- `用 aipy` / `使用 aipy` / `调用 aipy` / `让 aipy` / `帮我用 aipy`
- `python-use` / `python use`

## 触发后行为

1. **剥离触发词**，提取纯任务描述
2. **选工具**（见下方速查表）
3. **调用**，原样返回结果
4. **不要自作主张** — 不做前置分析、不写代码、不代替 AiPyPro

---

## 工具速查

### `aipy_run` — 自然语言 → AI 自主规划执行

```
aipy_run(instruction="...", mode="auto", cwd="<当前目录>")
```

| 参数 | 值 | 何时用 |
|------|-----|--------|
| `instruction` | 任务描述 | 必填 |
| `mode` | `auto` | **默认**。数据分析、文件处理、爬虫、自动化都用这个 |
| | `qa` | 纯知识问答（"什么是 X"） |
| | `task` | 强制执行代码，不经过 auto-routing |
| `cwd` | 路径 | 文件操作时指向目标目录 |

### `aipy_python` — 已知代码直接执行

```
aipy_python(code="print('hello')", cwd="<当前目录>")
```

> 仅在用户明确说 "执行/python 这段代码" 时使用。

---

## 典型调用

```
"aipy 分析 sales.xlsx"    → aipy_run(instruction="分析 sales.xlsx", mode="auto")
"aipy 什么是装饰器"        → aipy_run(instruction="什么是 Python 装饰器", mode="qa")
"aipy python print('hi')" → aipy_python(code="print('hi')")
```

---

## 用 AiPyPro vs 用 Claude Code

| 任务类型 | 交给谁 |
|----------|--------|
| Excel/CSV 数据分析、可视化 | **AiPyPro** |
| 批量文件处理、格式转换 | **AiPyPro** |
| 网页抓取、API 调用 | **AiPyPro** |
| Python 脚本执行 | **AiPyPro** |
| 系统文件整理、自动化 | **AiPyPro** |
| 修改项目源代码 | Claude Code |
| Git commit/push/rebase | Claude Code |
| 浏览器交互、截图 | Chrome DevTools MCP |
| 代码审查、搜索 | Claude Code |

---

## Red Flags — 停止，不要自作主张

以下想法出现任一条 → **停止。直接调 aipy_run，不要多想。**

| 危险想法 | 为什么错 |
|----------|----------|
| "这个任务很简单，我自己就能做" | 用户指定 aipy = 用户选择用 AiPyPro。尊重用户选择。 |
| "aipy_run 是执行工具，问答不适合" | 有 mode="qa"，AiPyPro 会自己处理问答。 |
| "我先分析一下再传给 aipy" | 不要。原样传递用户指令。 |
| "aipy 只是随口说的" | 触发词 = 触发。不推测用户意图。 |

## 常见错误

| 错误 | 正确做法 |
|------|----------|
| 用户说 "aipy 什么是 X"，自己直接回答 | 调 `aipy_run(mode="qa")` |
| 用户说 "aipy 分析数据"，先自己写 Python 看看数据 | 直接调 `aipy_run(mode="auto")` |
| 用户说 "用 aipy python 跑这段"，调了 aipy_run | 调 `aipy_python(code="...")` |
| 用户没提 aipy，主动建议用 aipy | 不主动推荐，除非用户问 |

---

## 故障排除

| 症状 | 处理 |
|------|------|
| API 认证失败 | `aipypro.exe sync` 同步配置后重试 |
| 任务超时 | 设置 `AIPYAPP_TIMEOUT=600` 或拆分子任务 |
| 空结果 | 检查 mode 不是 qa；确认 instruction 清晰 |
| 找不到 aipyapp | 设置 `AIPYAPP_PATH` 指向源码目录 |
