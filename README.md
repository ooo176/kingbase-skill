# kingbase-skill

面向 **人大金仓 KingbaseES** 数据库的 **Cursor / Agent Skill**：在对话中通过校验后的 **只读 SQL** 探查数据与元数据，**不支持**插入、更新、删除或 DDL。

## 功能

- 自定义 **SELECT / WITH / EXPLAIN / SHOW / DESC / DESCRIBE** 类查询（具体支持度与数据库 **兼容模式** 一致）
- 脚本层 **关键字与首词校验**，拦截 `INSERT`、`UPDATE`、`DELETE`、`MERGE`、DDL、`CALL`/`EXEC` 等
- 查询结果以 **JSON** 输出，便于 Agent 解析与汇总
- 默认限制返回行数，降低大结果集风险
- 支持 **psycopg2-binary**（pip）与 **ksycopg2**（金仓官方，随安装包）

## 仓库结构

```
kingbase-skill/
├── SKILL.md              # Agent 主指令（必读）
├── reference.md          # 退出码、JSON 字段、校验说明
├── README.md             # 本文件
├── requirements.txt      # Python 依赖（默认 psycopg2-binary）
└── scripts/
    └── kingbase_query.py # 只读查询 CLI
```

## 环境要求

- Python 3.9+（建议与运行 Agent 终端一致）
- **psycopg2-binary**（`pip install -r requirements.txt`），或从金仓介质安装 **ksycopg2** 并配置 `LD_LIBRARY_PATH`（Linux）

### 驱动选择

- **`KB_DRIVER=auto`（默认）**：优先加载 `ksycopg2`，失败则使用 `psycopg2`。
- 仅 pip、无金仓客户端机器：可设 `export KB_DRIVER=psycopg2`。

## 连接配置

在运行脚本的 shell 中配置（**勿**把密码写入仓库或提交 Git）。

**分项变量：**

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

**或 URI：**

```bash
export KB_URI="postgresql://SYSTEM:pass@127.0.0.1:54321/TEST"
```

生产环境建议使用 **仅 SELECT 权限** 的账号。端口以实际部署为准（常见 **54321**）。

## 命令行用法

将 `{ROOT}` 换为本仓库根目录（含 `SKILL.md` 的目录）。

```bash
# 执行查询（stdout 为 JSON）
python3 {ROOT}/scripts/kingbase_query.py --sql "SELECT 1" --max-rows 100

# 从文件读取 SQL
python3 {ROOT}/scripts/kingbase_query.py --file ./query.sql --max-rows 500

# 仅校验 SQL，不连库
python3 {ROOT}/scripts/kingbase_query.py --validate-only --sql "SELECT 1"
```

## Claude Code Skill

仓库克隆到 **`.claude/skills/`** 下后，目录内应直接可见 **`SKILL.md`**（与 `scripts/` 同级）。

### 个人（全局）安装

```bash
mkdir -p ~/.claude/skills
git clone <本仓库 URL> ~/.claude/skills/kingbase-skill
```

### 项目内安装

```bash
mkdir -p .claude/skills
git clone <本仓库 URL> .claude/skills/kingbase-skill
```

**重启 Claude Code** 后，Skill 会自动加载。

可选：设置 **`CLAUDE_SKILL_DIR`** 指向 Skill 根目录：

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/kingbase_query.py" --sql "SELECT 1"
```

## Cursor Skill

将本仓库放到 **`.cursor/skills/`** 下，保证 **`SKILL.md` 位于该 Skill 目录的根一级**（与 `scripts/` 同级）。

### 个人（全局）安装

```bash
mkdir -p ~/.cursor/skills
git clone <本仓库 URL> ~/.cursor/skills/kingbase-skill
```

### 项目内安装

```bash
mkdir -p .cursor/skills
git clone <本仓库 URL> .cursor/skills/kingbase-skill
```

**重启 Cursor**（或「Developer: Reload Window」）后，Agent 可按 Skills 规则加载。

## SQL 规则摘要

详细列表以 `SKILL.md` 与 `scripts/kingbase_query.py` 为准。

- 允许：以 `SELECT`、`WITH`、`EXPLAIN`、`SHOW`、`DESC`、`DESCRIBE` 开头
- 禁止：写操作相关关键字、`CALL`/`EXEC`、事务控制、多语句等

## 安全提示

- 凭证只放在环境变量或私密配置中
- 对用户提供的 SQL 仍需谨慎（性能与敏感列脱敏）
- 本工具为 **只读辅助**，不能替代数据库审计与权限治理

## 更多信息

- Agent 行为与流程： [SKILL.md](SKILL.md)
- 输出与边界说明： [reference.md](reference.md)
