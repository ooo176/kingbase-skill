# kingbase-skill

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.9+"></a>
  <img src="https://img.shields.io/badge/KingbaseES-人大金仓-C41E3A?style=flat-square" alt="KingbaseES">
  <img src="https://img.shields.io/badge/SQL-只读-2ea043?style=flat-square" alt="Read-only SQL">
  <img src="https://img.shields.io/badge/Agent-Qoder%20%7C%20Cursor%20%7C%20Claude-6f42c1?style=flat-square" alt="Qoder Cursor Claude">
</p>

<p align="center"><strong>人大金仓 KingbaseES · 只读 SQL Agent Skill</strong><br>
在 <strong>Qoder</strong>、<strong>Cursor</strong>、<strong>Claude Code</strong> 中通过校验后的只读 SQL 探查数据与元数据（不支持写入与 DDL）</p>

---

### 目录

- [核心能力](#核心能力)
- [仓库结构](#仓库结构)
- [环境与驱动](#环境与驱动)
- [连接配置](#连接配置)
- [命令行](#命令行)
- [安装 Skill](#安装-skill)（Qoder · Cursor · Claude Code）
- [SQL 与安全](#sql-与安全)
- [延伸阅读](#延伸阅读)

---

## 核心能力

- **自定义查询**：`SELECT` / `WITH` / `EXPLAIN` / `SHOW` / `DESC` / `DESCRIBE`（具体以当前库**兼容模式**为准）
- **脚本校验**：拦截 `INSERT`、`UPDATE`、`DELETE`、`MERGE`、DDL、`CALL` / `EXEC` 等
- **JSON 输出**：便于 Agent 解析与汇总
- **行数上限**：默认限制返回行数，降低大结果集风险
- **双驱动**：`psycopg2-binary`（pip）或 **ksycopg2**（金仓安装包）

---

## 仓库结构

本仓库**根目录**即 Skill 根目录：`SKILL.md` 与 `scripts/` **必须同级**，Agent 才能正确调用脚本。

```
kingbase-skill/
├── SKILL.md              # Agent 主指令（必读）
├── reference.md          # 退出码、JSON 字段、校验说明
├── README.md             # 本文件
├── requirements.txt      # Python 依赖（默认 psycopg2-binary）
├── .env/                 # 本地私密配置（已 .gitignore）
│   └── env.sh            # 填写后: source .env/env.sh
└── scripts/
    └── kingbase_query.py # 只读查询 CLI
```

---

## 环境与驱动

**要求**

- Python **3.9+**（建议与运行 Agent 的终端一致）
- `pip install -r requirements.txt` → **psycopg2-binary**；或使用介质中的 **ksycopg2**（Linux 常需配置 `LD_LIBRARY_PATH`）

**`KB_DRIVER`**

| 取值 | 行为 |
|------|------|
| `auto`（默认） | 先试 `ksycopg2`，失败再用 `psycopg2` |
| `psycopg2` | 仅用 pip 驱动 |
| `ksycopg2` | 仅用官方驱动 |

```bash
export KB_DRIVER=psycopg2   # Linux / macOS / Git Bash
```

- **PowerShell**：`$env:KB_DRIVER = "psycopg2"`
- **CMD**：`set KB_DRIVER=psycopg2`

---

## 连接配置

> **请勿**把密码写入仓库或提交 Git。可使用仓库内 **`.env/env.sh`**（已忽略版本控制）：填好后在仓库根目录执行 `source .env/env.sh`。

### Bash / zsh

```bash
export KB_USER="SYSTEM"
export KB_PASSWORD="你的密码"
export KB_HOST="127.0.0.1"
export KB_PORT="54321"
export KB_DATABASE="TEST"
# 可选
export KB_SCHEMA="public"
export KB_MAX_ROWS="500"
export KB_DRIVER="auto"
```

**`KB_SCHEMA` 说明**：连库后会执行 `SET search_path TO <值>`，只影响**未带模式前缀**的对象名。查「某模式下有哪些表」时，仍需在 SQL 里写 `WHERE table_schema = '你的模式名'`（`information_schema` / `pg_catalog` 不受 `search_path` 限制）。

### URI（可选）

```bash
export KB_URI="postgresql://SYSTEM:pass@127.0.0.1:54321/TEST"
```

### Windows · PowerShell

```powershell
$env:KB_USER = "SYSTEM"
$env:KB_PASSWORD = "你的密码"
$env:KB_HOST = "127.0.0.1"
$env:KB_PORT = "54321"
$env:KB_DATABASE = "TEST"
$env:KB_SCHEMA = "public"      # 可选
$env:KB_MAX_ROWS = "500"       # 可选
$env:KB_DRIVER = "auto"        # 可选
$env:KB_URI = "postgresql://..."  # 可选，与分项二选一
```

### Windows · CMD

```cmd
set KB_USER=SYSTEM
set KB_PASSWORD=你的密码
set KB_HOST=127.0.0.1
set KB_PORT=54321
set KB_DATABASE=TEST
set KB_URI=postgresql://SYSTEM:pass@127.0.0.1:54321/TEST
```

环境变量默认仅对**当前终端**生效；长期保存可用系统「环境变量」或 PowerShell 的 `[Environment]::SetEnvironmentVariable(..., "User")`。

生产环境建议使用 **仅 SELECT 权限** 账号；端口以现场为准（常见 **54321**）。

---

## 命令行

将 `{ROOT}` 换为 Skill 根目录（含 `SKILL.md` 的目录）。

```bash
python3 {ROOT}/scripts/kingbase_query.py --sql "SELECT 1" --max-rows 100
python3 {ROOT}/scripts/kingbase_query.py --file ./query.sql --max-rows 500
python3 {ROOT}/scripts/kingbase_query.py --validate-only --sql "SELECT 1"
```

---

## 安装 Skill

**共同要求**：安装后目录中须能直接看到 **`SKILL.md`**，且 **`scripts/` 与其同级**（本仓库 `git clone` 后即为正确结构）。

```mermaid
flowchart TB
  A[获取 kingbase-skill 目录] --> B[Qoder]
  A --> C[Cursor]
  A --> D[Claude Code]
  B --> B1["~/.qoder/skills/ 或 项目 .qoder/skills/"]
  C --> C1["~/.cursor/skills/ 或 项目 .cursor/skills/"]
  D --> D1["~/.claude/skills/ 或 项目 .claude/skills/"]
```

### Qoder

依据 [Qoder Skills 文档](https://docs.qoder.com/zh/extensions/skills)，可将本 Skill 放到**用户级**或**项目级**目录（`SKILL.md` 位于 `{skill-name}/` 下）。

| 作用域 | 路径（将 `kingbase-skill` 换为你希望的目录名） |
|--------|-----------------------------------------------|
| 用户级 | `~/.qoder/skills/kingbase-skill/SKILL.md` |
| 项目级 | `<项目根>/.qoder/skills/kingbase-skill/SKILL.md` |

**手动安装（推荐，保留完整 `scripts/`）**

```bash
# 用户级（macOS / Linux）
mkdir -p ~/.qoder/skills
git clone <本仓库 URL> ~/.qoder/skills/kingbase-skill

# 项目级
mkdir -p .qoder/skills
git clone <本仓库 URL> .qoder/skills/kingbase-skill
```

**Windows** 用户级示例：`%USERPROFILE%\.qoder\skills\kingbase-skill\SKILL.md`。

**使用 [Skills CLI](https://github.com/vercel-labs/skills) 安装**（仓库已推送到 GitHub 后，在 Qoder 内置终端执行）：

```bash
npx skills add <本仓库 GitHub URL> -a qoder
```

更多参数见官方 CLI 说明。若与手动目录**同名**，项目级 Skill 优先级高于用户级。

安装完成后 **重启 Qoder IDE**；在对话中输入 **`/`** 可查看已加载的 Skills。触发方式与官方一致：**描述需求自动匹配**，或 **`/` + 技能名** 手动调用。本 Skill 在 `SKILL.md` 中的 `name` 为 **`kingbase-database-readonly`**，若 Qoder 列表中有对应项，可尝试 `/kingbase-database-readonly`（以 IDE 内实际列表为准）。

---

### Cursor

| 作用域 | 路径 |
|--------|------|
| 用户级 | `~/.cursor/skills/kingbase-skill/SKILL.md` |
| 项目级 | `<项目根>/.cursor/skills/kingbase-skill/SKILL.md` |

```bash
mkdir -p ~/.cursor/skills
git clone <本仓库 URL> ~/.cursor/skills/kingbase-skill
# 或项目内: mkdir -p .cursor/skills && git clone <URL> .cursor/skills/kingbase-skill
```

重启 Cursor 或执行 **Developer: Reload Window**。

---

### Claude Code

| 作用域 | 路径 |
|--------|------|
| 用户级 | `~/.claude/skills/kingbase-skill/SKILL.md` |
| 项目级 | `<项目根>/.claude/skills/kingbase-skill/SKILL.md` |

```bash
mkdir -p ~/.claude/skills
git clone <本仓库 URL> ~/.claude/skills/kingbase-skill
```

重启 Claude Code。可选：设置 **`CLAUDE_SKILL_DIR`** 指向 Skill 根目录：

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/kingbase_query.py" --sql "SELECT 1"
```

PowerShell：`$env:CLAUDE_SKILL_DIR = "D:\path\to\kingbase-skill"`，再执行  
`python "$env:CLAUDE_SKILL_DIR\scripts\kingbase_query.py" --sql "SELECT 1"`。

---

## SQL 与安全

| | |
|--|--|
| **允许** | 以 `SELECT`、`WITH`、`EXPLAIN`、`SHOW`、`DESC`、`DESCRIBE` 开头（细则见 `SKILL.md` 与 `scripts/kingbase_query.py`） |
| **禁止** | 写操作关键字、`CALL` / `EXEC`、显式事务控制、**多条语句**（多个 `;`） |

- 凭证仅放在环境变量或 **`.env/`**，勿贴入对话或版本库。
- 注意 SQL 性能与结果中的敏感列脱敏。
- 本工具为**只读辅助**，不能替代审计与权限治理。

---

## 延伸阅读

| 文档 | 说明 |
|------|------|
| [SKILL.md](SKILL.md) | Agent 流程、连接说明、SQL 规则 |
| [reference.md](reference.md) | 退出码、JSON 字段、驱动说明 |
