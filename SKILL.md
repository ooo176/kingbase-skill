---
name: kingbase-database-readonly
description: "Queries KingbaseES (人大金仓 / Kingbase) databases in read-only mode via validated SQL and psycopg2 or ksycopg2. Supports SELECT-style exploration, SHOW metadata, and custom SQL; blocks INSERT/UPDATE/DELETE/DDL and other writes. Use when the user mentions 人大金仓、Kingbase、金仓数据库、KingbaseES, read-only SQL, or querying Kingbase."
argument-hint: "[optional SQL or question about tables]"
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

# 人大金仓 KingbaseES 只读查询（Read-Only）

## 何时使用本 Skill

在以下情况启用：

- 用户要**查询 KingbaseES（人大金仓）**中的表、视图、统计或任意**只读**数据
- 用户给出或需要你编写**自定义 SQL**（仅限只读）
- 用户明确说**不能改库**、只要 SELECT / 分析 / 探查 schema

**禁止**：任何 **INSERT、UPDATE、DELETE、MERGE、DDL、GRANT、存储过程执行（CALL/EXEC）** 等写入或权限变更。若用户要求改数据，说明本 Skill 与脚本均不支持，请改用 DBA 工具或专用迁移流程。

---

## 工具与路径

| 任务 | 做法 |
|------|------|
| 执行只读 SQL | `Bash` → `python3` 运行本 Skill 内脚本（见下） |
| 查看 Skill 说明或示例 | `Read` → 打开本仓库 `SKILL.md` 或 `reference.md` |

**脚本路径**（将 `{SKILL_ROOT}` 换成本仓库根目录，即包含 `SKILL.md` 的目录）：

```bash
python3 {SKILL_ROOT}/scripts/kingbase_query.py --sql "你的SQL"
# 或
python3 {SKILL_ROOT}/scripts/kingbase_query.py --file /path/to/query.sql --max-rows 500
```

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

1. **确认意图**：只读查询；若用户要求写入，拒绝并说明边界。
2. **编写或确认 SQL**：优先参数化思路；避免拼接不可信输入。若 SQL 来自用户粘贴，仍须经脚本校验。
3. **先校验（可选）**：
   ```bash
   python3 {SKILL_ROOT}/scripts/kingbase_query.py --validate-only --sql "SELECT 1"
   ```
4. **执行查询**：
   ```bash
   python3 {SKILL_ROOT}/scripts/kingbase_query.py --sql "..." --max-rows 500
   ```
5. **解读结果**：脚本 stdout 为 **JSON**（`ok`、`columns`、`rows`、`row_count`、`truncated` 等）。向用户总结关键结论；大行集说明已截断并可缩小条件或提高 `KB_MAX_ROWS`（注意内存与性能）。

---

## SQL 规则（与脚本一致）

- 允许以 **`SELECT`、`WITH`、`EXPLAIN`、`SHOW`、`DESC`、`DESCRIBE`** 开头（大小写不敏感，可带末尾分号）。具体语句是否受当前 **兼容模式**（Oracle/MySQL/PostgreSQL 等）支持，以库端为准。
- **禁止**语句中出现以下关键字（整词匹配，含注释 stripped 后的主体）：  
  `INSERT`、`UPDATE`、`DELETE`、`MERGE`、`REPLACE`、`DROP`、`CREATE`、`ALTER`、`TRUNCATE`、`RENAME`、`GRANT`、`REVOKE`、`COMMIT`、`ROLLBACK`、`SAVEPOINT`、`CALL`、`EXECUTE`、`EXEC`。
- **禁止**多条语句（多个 `;` 分隔的独立语句）。
- 默认最多返回 **500** 行（`--max-rows` 或 `KB_MAX_ROWS`）；超大结果集建议在 SQL 中加 `WHERE`/分页。

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
- 生产库查询使用**只读账号**；限制 `KB_MAX_ROWS` 与查询时间窗口。
- 用户 SQL 可能包含敏感列；输出时注意脱敏与最小必要原则。

---

## 更多说明

- 实现细节与边界案例见 [reference.md](reference.md)。
