---
name: kingbase-database
description: "Queries, modifies, and generates test data for KingbaseES (人大金仓 / Kingbase) databases via validated SQL and psycopg2 or ksycopg2. Supports SELECT (default read-only), INSERT/UPDATE/DELETE with user confirmation and automatic backup, and automated test data generation. DDL blocked. Use when the user mentions 人大金仓、Kingbase、金仓数据库、KingbaseES, SQL queries, database modifications, or test data generation."
argument-hint: "[optional SQL or question about tables or test data generation]"
parameter-schema:
  type: object
  description: 金仓连接用的环境变量。使用分项变量时需 KB_USER、KB_PASSWORD、KB_DATABASE 及 KB_HOST、KB_PORT（默认 54321）；使用 KB_URI（或 KINGBASE_URI）时可代替分项主机/端口/库名。
  required: []
  properties:
    KB_HOST:
      type: string
      description: 数据库主机。
    KB_PORT:
      type: integer
      description: 监听端口（常见 54321，以实际部署为准）。
    KB_DATABASE:
      type: string
      description: 数据库名（连接串中的 dbname）。
  additionalProperties: true
version: "1.0.0"
user-invocable: true
allowed-tools: Read, Bash
---

> **语言**：用户用中文则用中文回复；用户用英文则用英文回复。

# 人大金仓 KingbaseES 查询、写操作与测试数据生成

## 何时使用本 Skill

在以下情况启用：

- 用户要**查询 KingbaseES（人大金仓）** 中的表、视图、统计或任意数据
- 用户给出或需要你编写**自定义 SQL**（SELECT 或 INSERT/UPDATE/DELETE）
- 用户明确说需要**读**、**改**、**删**、**增**数据（除 DDL 外）
- 用户要**生成测试数据**、**填充数据库**、**造测试数据**

**支持的操作**

- **只读（默认）**：`SELECT` / `WITH` / `EXPLAIN` / `SHOW` / `DESC` / `DESCRIBE`
- **写操作（须用户确认 + 自动备份）**：`INSERT` / `UPDATE` / `DELETE`
- **测试数据生成（自动推断 + 规则文件）**：零配置生成、基于 `generate.rules.md` 规则文件生成

**始终禁止**：`DROP` / `CREATE` / `ALTER` / `TRUNCATE` / `RENAME` / `GRANT` / `REVOKE` / `MERGE` / `REPLACE` / `CALL` / `EXECUTE` / `EXEC` 等 DDL 与权限变更；显式事务控制；多条语句同时执行。

## 写操作强制流程（增删改）

写操作会**改变数据**，必须严格按照以下步骤：

1. **展示 SQL** — 把即将执行的 INSERT/UPDATE/DELETE 语句原文完整展示给用户。
2. **说明影响面** — 对 UPDATE/DELETE 先执行同 WHERE 条件的 SELECT，告知用户**将影响多少行**、大致内容。
3. **征得用户明示同意** — 用户明确回复「同意 / 执行 / yes / OK」等含义时才继续；仅收到「看一下」「继续研究」等含糊回复**不算同意**。
4. **执行时自动备份** — 脚本在 UPDATE/DELETE 前将受影响行落地为 JSON 文件（默认 `.kb_backups/`，可用 `KB_BACKUP_DIR` 环境变量指定目录），随执行结果一并返回备份路径。INSERT 因不涉及已有数据，不产生备份文件。
5. **回滚参考** — 若执行后需要撤销，读取备份 JSON，按 `columns` + `rows` 手工构造 INSERT（对 DELETE）或 UPDATE（对 UPDATE，用 PK 或原始 WHERE 定位）。备份中的 `where` 字段可用于对齐原始条件。

---

## 工具与路径

| 任务 | 做法 |
|------|------|
| 执行只读 SQL | `Bash` → `python3` 运行本 Skill 内脚本（见下） |
| 查看 Skill 说明或示例 | `Read` → 打开本仓库 `SKILL.md` 或 `docs/reference.md` |

**脚本路径**（将 `{SKILL_ROOT}` 换成本仓库根目录，即包含 `SKILL.md` 的目录）：

```bash
# 只读查询（默认）
python3 {SKILL_ROOT}/scripts/kingbase_query.py --sql "SELECT ..."
python3 {SKILL_ROOT}/scripts/kingbase_query.py --file /path/to/query.sql --max-rows 500

# 写操作：必须 --allow-write + --confirm，且事前已获得用户同意
python3 {SKILL_ROOT}/scripts/kingbase_query.py --allow-write --confirm --sql "UPDATE t SET x=1 WHERE id=2"
python3 {SKILL_ROOT}/scripts/kingbase_query.py --allow-write --confirm --sql "DELETE FROM t WHERE id=2"
python3 {SKILL_ROOT}/scripts/kingbase_query.py --allow-write --confirm --sql "INSERT INTO t (a,b) VALUES (1,2)"

# 生成测试数据：--dry-run 预览，--confirm 执行
python3 {SKILL_ROOT}/scripts/kingbase_generate.py --count 100 --dry-run
python3 {SKILL_ROOT}/scripts/kingbase_generate.py --count 100 --confirm
python3 {SKILL_ROOT}/scripts/kingbase_generate.py --tables "dept:10,emp:100" --confirm
```

> `--confirm` 表示「Agent 已当面获取用户授权」。**不得**在未取得用户同意的情况下自行加上此参数。

在 Claude Code 且已设置 `CLAUDE_SKILL_DIR` 时，可写为：

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/kingbase_query.py" --sql "SELECT 1"
```

执行前需在 shell 中导出连接信息。地址、库名等字段的**规范定义**见上文 frontmatter 中的 `parameter-schema`（`KB_HOST`、`KB_PORT`、`KB_DATABASE`）。

### 连接参数与 JDBC URL

与 **KB_HOST / KB_PORT / KB_DATABASE** 等价的 **JDBC 连接串**（Java 等客户端；驱动与版本以金仓文档为准，以下为常见 kingbase8 形式）：

```text
jdbc:kingbase8://${KB_HOST}:${KB_PORT}/${KB_DATABASE}
```

本仓库脚本使用 **psycopg2** 或 **ksycopg2**，不直接消费 JDBC URL；请在 shell 中设置同名环境变量或使用 **KB_URI**（libpq 风格 URI）。

**方式 A — 分项环境变量（推荐）**

```bash
export KB_USER="SYSTEM"
export KB_PASSWORD="******"
export KB_HOST="127.0.0.1"
export KB_PORT="54321"
export KB_DATABASE="TEST"
# 可选：会话 search_path（简单标识符）。仅影响未加模式前缀的表名解析，不过滤 information_schema 等目录查询
export KB_SCHEMA="public"
export KB_MAX_ROWS="500"
# 可选：auto | ksycopg2 | psycopg2（默认 auto：先试官方 ksycopg2，再 psycopg2）
export KB_DRIVER="auto"
# 可选：UPDATE/DELETE 前受影响行备份的输出目录（默认 .kb_backups/）
export KB_BACKUP_DIR=".kb_backups"
```

**方式 B — 连接 URI**

```bash
export KB_URI="postgresql://SYSTEM:your_password@127.0.0.1:54321/TEST"
# 别名：KINGBASE_URI
```

密码与 URI **不要**写进 Skill 文件或提交到 Git；由用户在环境中配置。

---

## 依赖

```bash
pip install -r {SKILL_ROOT}/requirements.txt
```

**国内镜像（阿里云 PyPI）**：

```bash
pip install -r {SKILL_ROOT}/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

**官方 ksycopg2**：通常随 **金仓安装包**分发，需将模块与 **libkci** 等库路径加入 `LD_LIBRARY_PATH`（Linux），详见金仓《应用开发指南》Python 章节；安装后可设 `KB_DRIVER=ksycopg2` 或保持 `auto` 优先使用 ksycopg2。

---

## Agent 执行流程

### 只读查询

1. **确认意图**：只是查询。
2. **编写或确认 SQL**：优先参数化思路；避免拼接不可信输入。
3. **校验（可选）**：
   ```bash
   python3 {SKILL_ROOT}/scripts/kingbase_query.py --validate-only --sql "SELECT 1"
   ```
4. **执行**：
   ```bash
   python3 {SKILL_ROOT}/scripts/kingbase_query.py --sql "..." --max-rows 500
   ```
5. **解读结果**：stdout 为 JSON（`ok` / `columns` / `rows` / `row_count` / `truncated` 等）。

### 写操作（INSERT / UPDATE / DELETE）

1. **展示 SQL**：把 SQL 原文展示给用户。
2. **预估影响面**（UPDATE / DELETE）：以同 WHERE 条件跑一次 SELECT，告知用户「本次将影响 N 行」并列举样本。
3. **征得用户同意**：等待用户明确回复同意后，再进入下一步。
4. **校验（可选）**：
   ```bash
   python3 {SKILL_ROOT}/scripts/kingbase_query.py --validate-only --allow-write --sql "UPDATE t SET x=1 WHERE id=2"
   ```
5. **执行**（脚本会先做一次备份 SELECT，再执行写操作，最后 commit）：
   ```bash
   python3 {SKILL_ROOT}/scripts/kingbase_query.py --allow-write --confirm --sql "UPDATE t SET x=1 WHERE id=2"
   ```
6. **回报**：输出 JSON 中的 `rows_affected` 与 `backup.file`（备份文件绝对路径），一并汇报给用户，便于日后回滚。

**注意**

- **`--confirm` 是硬门槛**。脚本在缺少 `--confirm` 时拒绝执行任何写操作。
- **不允许一次写多张表**。脚本仅支持单条语句、单表 UPDATE / DELETE 的 WHERE 提取；对复杂写操作先与用户拆分。
- **无 WHERE 的 UPDATE / DELETE** 会备份**整表**当前快照，请提前警告用户。

---

## 生成测试数据（Generate）

本 Skill 提供**零配置自动推断**的测试数据生成能力，非技术人员只需说「每个表生成 100 条」即可。

### 三种使用方式（由简到繁）

| 层级 | 谁用 | 规则维护位置 | 怎么做 |
|------|------|-------------|--------|
| **L1 规则文件** | 非技术人员（推荐） | 项目内 `generate.rules.md` | 用中文写每张表规则，对 Agent 说「按规则生成」 |
| **L2 对话** | 临时一次性需求 | 对话中口头说明 | 「这次只给 employee 生成 50 条」 |
| **L3 CLI / JSON** | 开发/自动化 | 命令行或 CI | `--count 100` / `--rules-json '{...}'` |

**规则优先级**（冲突时）：对话临时指令 > `generate.rules.md` > 自动推断。

### L1：规则文件 `generate.rules.md`（推荐）

非技术人员在**项目根目录**维护 `generate.rules.md`，用**中文**描述每张表的生成要求。Agent 会读取此文件并翻译为技术参数执行。

**文件示例**：

```markdown
# 数据生成规则

schema: public
默认每个表: 100 条

## department
- 生成 10 条
- dept_name 从以下随机：研发部、市场部、财务部

## employee
- 生成 100 条
- status 随机：在职、离职
- email 格式：user_{序号}@example.com

## 不生成
- sys_log
- audit_history
```

**支持的写法**（自然语言）：

| 你想表达 | 示例 |
|----------|------|
| 全局默认条数 | `默认每个表: 100 条` |
| 某表条数 | `## employee` 下写 `- 生成 100 条` |
| 枚举字段 | `- status 随机：在职、离职` |
| 固定格式 | `- email 格式：user_{序号}@example.com` |
| 跳过某表 | `## 不生成` 下列出表名 |

**使用方法**：编辑好 `generate.rules.md` 后，对 Agent 说：

- 「按 generate.rules.md 生成数据」
- 「帮我生成测试数据」

### Agent 生成流程

1. **读取**项目内 `generate.rules.md`（若存在）；用户对话中的临时要求可覆盖文件内容。
2. 将 rules 文件**翻译**为 `--schema` / `--tables` / `--exclude-tables` / `--rules-json`。
3. 设置或确认连接环境变量。
4. 执行 `--dry-run`，将 JSON **翻译为中文摘要**展示：

   ```text
   即将在 schema「public」生成测试数据：

     备份并重命名（后缀 20260811）：
       · department（当前 5 行）→ department_20260811
       · employee（当前 120 行）→ employee_20260811

     生成计划：
       · department：10 行
       · employee：100 行

     外键关系（自动发现）：
       · employee.dept_id → department.id

   确认执行吗？
   ```

5. 用户确认。
6. 执行 `--confirm`，用中文汇报备份表名与各表插入行数。

### 自动推断（未写规则的字段）

脚本连接数据库后**自动完成**以下工作：

- **发现表**：从 `information_schema.tables` 读取 schema 下所有用户表
- **发现外键关系**：构建依赖图，**拓扑排序**决定 INSERT 顺序（父表先于子表）
- **自动推断字段生成规则**：

| 列特征 | 自动生成策略 |
|--------|-------------|
| serial / identity / 自增 PK | 数据库自动 |
| integer/bigint PK（非 FK） | 递增整数 |
| FK 列 | 引用父表已插入行的 PK 值（random） |
| 列名含 name/姓名/mc | 中文姓名（Faker） |
| 列名含 email/phone/mobile/lxfs/address/dz | 对应 Faker provider |
| 列名含 time/date/created/updated | 近期随机日期或 now() |
| varchar/text NOT NULL | 随机文本 |
| boolean | 随机 true/false |
| numeric/decimal | 范围内随机数 |
| uuid 类型 | uuid4 |
| nullable 非 PK | 约 10% NULL |
| 其余 | 按 data_type 通用兜底 |

### L2：临时对话指令

对话中可临时覆盖规则文件：

- 「这次 department 改成 20 条」
- 「只生成 employee 表，50 条」

Agent 会合并规则文件和对话指令，优先采用对话中的要求。

### L3：直接 CLI

开发者或自动化场景可直接命令行：

```bash
# 零配置：schema 下全部表，每张 100 条
python3 scripts/kingbase_generate.py --count 100 --confirm

# 指定表和不同条数
python3 scripts/kingbase_generate.py --tables "department:10,employee:100" --confirm

# 排除某些表
python3 scripts/kingbase_generate.py --count 100 --exclude-tables "sys_log,audit_history" --confirm

# 字段级规则 JSON
python3 scripts/kingbase_generate.py --count 100 --rules-json '{"employee":{"status":{"type":"enum","values":["在职","离职"]}}}' --confirm

# 预览再执行
python3 scripts/kingbase_generate.py --count 100 --dry-run
python3 scripts/kingbase_generate.py --count 100 --confirm
```

### 安全约束

| 项 | 规则 |
|----|------|
| 授权 | 必须 `--confirm` |
| 预览 | Agent **必须先 dry-run**，用中文展示计划 |
| 环境 | 仅测试库使用；可选 `KB_ALLOW_GENERATE=1` |
| 备份 | 执行前将旧表 `RENAME` 为 `{表名}_{YYYYMMDD}` |
| 事务 | 全流程单事务，失败回滚 |

---

## SQL 规则（与脚本一致）

**只读模式（默认）**

- 允许以 `SELECT` / `WITH` / `EXPLAIN` / `SHOW` / `DESC` / `DESCRIBE` 开头。
- 语句主体中出现 `INSERT` / `UPDATE` / `DELETE` / `MERGE` / `REPLACE` / `DROP` / `CREATE` / `ALTER` / `TRUNCATE` / `RENAME` / `GRANT` / `REVOKE` / `COMMIT` / `ROLLBACK` / `SAVEPOINT` / `CALL` / `EXECUTE` / `EXEC` 之一即被拒绝。

**写模式（`--allow-write --confirm`）**

- 允许以 `INSERT` / `UPDATE` / `DELETE` 开头；`SELECT` 等只读语句会自动走只读路径。
- 始终禁止 `DROP` / `CREATE` / `ALTER` / `TRUNCATE` / `RENAME` / `GRANT` / `REVOKE` / `MERGE` / `REPLACE` / `CALL` / `EXECUTE` / `EXEC` 及显式事务控制。

**通用**

- 禁止多条语句（多个 `;` 分隔）。
- 只读默认最多返回 **500** 行（`--max-rows` 或 `KB_MAX_ROWS`）。
- 写模式下，脚本以单一事务提交；执行失败则整体回滚。

---

## 常用探查示例（PostgreSQL 兼容 / information_schema）

实际系统表与兼容模式有关；若报错，按现场版本改用 `pg_catalog` 或金仓字典视图。

```sql
-- 当前库、public 下用户表
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE' AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;

-- 列信息
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'your_table';

-- 采样
SELECT * FROM your_table LIMIT 20;
```

---

## 安全与合规

- 不在对话中重复打印完整密码。
- 生产库查询使用**只读账号**；仅在必要且授权的库上使用写权限账号。
- 用户 SQL 可能包含敏感列；输出时注意脱敏与最小必要原则。
- 写模式下，`.kb_backups/` 目录内 JSON 可能包含**受影响行的原始数据**（含潜在敏感列）；请纳入 `.gitignore` 并按需清理。

---

## 更多说明

- 实现细节与边界案例见 [docs/reference.md](docs/reference.md)。
- 规则文件模板见 [examples/generate.rules.example.md](examples/generate.rules.example.md)。
- 完整能力规范见 [docs/SPEC.md](docs/SPEC.md)。
