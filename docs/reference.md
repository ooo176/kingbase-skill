# 人大金仓 Skill — 参考

## 脚本退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 参数错误（如未提供 `--sql`/`--file`）或校验失败 |
| 2 | 缺少依赖、未配置连接 |
| 3 | 执行期数据库/驱动错误 |

## JSON 输出字段

### 只读查询成功时

```json
{
  "ok": true,
  "sql": "规范化后的 SQL",
  "columns": ["COL1", "COL2"],
  "rows": [{"COL1": 1, "COL2": "a"}],
  "row_count": 1,
  "returned": 1,
  "truncated": false
}
```

### 写操作成功时

```json
{
  "ok": true,
  "operation": "UPDATE",
  "sql": "UPDATE t SET x=1 WHERE id=2",
  "rows_affected": 1,
  "backup": {
    "skipped": false,
    "file": "/path/to/.kb_backups/update_t_20260811_123456_789012.json",
    "row_count": 1
  }
}
```

**`backup` 字段说明**

- `skipped: true` — INSERT 操作或无法解析表名时跳过备份。
- `skipped: false` — 已备份受影响行。`file` 为 JSON 绝对路径，`row_count` 为备份行数。

### 失败时

```json
{ "ok": false, "error": "原因说明" }
```

## 备份 JSON 文件结构

`.kb_backups/{op}_{table}_{timestamp}.json`：

```json
{
  "operation": "DELETE",
  "table": "users",
  "where": "WHERE status = 'inactive'",
  "backed_up_at": "2026-08-11T12:34:56.789012",
  "row_count": 3,
  "columns": ["id", "name", "status"],
  "rows": [
    {"id": 1, "name": "Alice", "status": "inactive"}
  ]
}
```

可据此手工构造回滚 SQL：DELETE → 反向 INSERT；UPDATE → 用备份行按 PK 或原始 WHERE 定位后 UPDATE。

## 校验与解析局限

- 注释移除采用简单正则，**字符串字面量内**若含与注释冲突的子串，可能导致误判。
- 写模式下的 WHERE 提取基于单表 UPDATE / DELETE 的简单正则：不支持 `USING` 联表、CTE 与子查询式 UPDATE / DELETE；若解析失败会 `skipped: true` 并给出原因，此时脚本**不会自动阻止**写操作，仍会执行 — 因此复杂写操作需人工确认影响范围。
- 无 WHERE 的 UPDATE / DELETE 会备份**整表**，规模大时耗时且占空间。
- 仅关键字与首词过滤，**无法**防御所有风险（如极重查询、锁竞争）；应用侧务必配合最小权限账号与资源限制。

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `KB_BACKUP_DIR` | `.kb_backups` | 写操作前备份 JSON 的输出目录。相对路径基于脚本执行时的 CWD。 |
| `KB_MAX_ROWS` | `500` | 只读查询默认返回上限。 |
| `KB_DRIVER` | `auto` | 驱动选择（`auto` / `ksycopg2` / `psycopg2`）。 |
| `KB_SCHEMA` | 无 | 连接后 `SET search_path TO <值>`。 |

## 与 dm-skill 的对齐方式

本 Skill 同样采用：

- YAML frontmatter（`name` / `description` / `version` / `user-invocable` / `allowed-tools`）
- 明确的「触发条件 + 工具表 + Bash 调用脚本」结构
- 环境变量配置密钥，不写入仓库

便于放入 `.cursor/skills/`、`~/.cursor/skills/` 或 Claude Code 的 skills 目录使用。

## 驱动说明摘要

| KB_DRIVER | 行为 |
|-----------|------|
| `auto`（默认） | 优先 `ksycopg2`，导入失败则用 `psycopg2` |
| `ksycopg2` | 仅官方驱动（随金仓介质安装） |
| `psycopg2` | 仅 pip 的 `psycopg2` / `psycopg2-binary` |

Apple Silicon 等 **ARM** 环境通常可使用 **psycopg2-binary**；**ksycopg2** 是否提供对应平台 wheel 以金仓发布包为准。
