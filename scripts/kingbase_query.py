#!/usr/bin/env python3
"""
人大金仓 KingbaseES SQL 查询与写操作。

默认只读（SELECT/WITH/EXPLAIN/SHOW/DESC/DESCRIBE）。
传入 --allow-write 可执行 INSERT/UPDATE/DELETE；写操作必须同时传 --confirm。
UPDATE/DELETE 执行前自动备份受影响行至 JSON 文件。
DDL（DROP/CREATE/ALTER/TRUNCATE/RENAME 等）始终禁止。

驱动优先级（环境变量 KB_DRIVER）：
  auto（默认）— 先试 ksycopg2（官方），失败再用 psycopg2
  ksycopg2   — 仅官方驱动
  psycopg2   — 仅 psycopg2 / psycopg2-binary
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def _strip_sql_comments(sql: str) -> str:
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    s = re.sub(r"--[^\n]*", " ", s)
    return s


_READONLY_FORBIDDEN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|MERGE|REPLACE|"
    r"DROP|CREATE|ALTER|TRUNCATE|RENAME|"
    r"GRANT|REVOKE|COMMIT|ROLLBACK|SAVEPOINT|"
    r"CALL|EXECUTE|EXEC"
    r")\b",
    re.IGNORECASE,
)

_DDL_FORBIDDEN = re.compile(
    r"\b("
    r"DROP|CREATE|ALTER|TRUNCATE|RENAME|"
    r"GRANT|REVOKE|COMMIT|ROLLBACK|SAVEPOINT|"
    r"CALL|EXECUTE|EXEC|MERGE|REPLACE"
    r")\b",
    re.IGNORECASE,
)

_READONLY_ALLOWED_START = frozenset(
    {"SELECT", "WITH", "EXPLAIN", "SHOW", "DESC", "DESCRIBE"}
)
_WRITE_ALLOWED_START = frozenset({"INSERT", "UPDATE", "DELETE"})


def validate_readonly_sql(sql: str) -> str:
    raw = sql.strip()
    if not raw:
        raise ValueError("SQL 为空")
    cleaned = _strip_sql_comments(raw).strip()
    if not cleaned:
        raise ValueError("去掉注释后 SQL 为空")
    parts = [p.strip() for p in cleaned.split(";") if p.strip()]
    if len(parts) > 1:
        raise ValueError("不允许一次执行多条语句（多个分号分隔）")
    stmt = parts[0] if parts else cleaned.rstrip(";").strip()
    if _READONLY_FORBIDDEN.search(stmt):
        m = _READONLY_FORBIDDEN.search(stmt)
        raise ValueError(f"只读模式禁止关键字: {m.group(1) if m else '?'}")
    first = re.match(r"^\s*(\w+)", stmt)
    if not first:
        raise ValueError("无法解析 SQL 首关键字")
    kw = first.group(1).upper()
    if kw not in _READONLY_ALLOWED_START:
        raise ValueError(
            f"只读模式仅允许以以下关键字开头: {', '.join(sorted(_READONLY_ALLOWED_START))}"
        )
    return raw.rstrip().rstrip(";")


def validate_write_sql(sql: str) -> str:
    """校验写操作 SQL（INSERT/UPDATE/DELETE）；DDL 始终禁止。"""
    raw = sql.strip()
    if not raw:
        raise ValueError("SQL 为空")
    cleaned = _strip_sql_comments(raw).strip()
    if not cleaned:
        raise ValueError("去掉注释后 SQL 为空")
    parts = [p.strip() for p in cleaned.split(";") if p.strip()]
    if len(parts) > 1:
        raise ValueError("不允许一次执行多条语句（多个分号分隔）")
    stmt = parts[0] if parts else cleaned.rstrip(";").strip()
    if _DDL_FORBIDDEN.search(stmt):
        m = _DDL_FORBIDDEN.search(stmt)
        raise ValueError(f"DDL 操作始终禁止: {m.group(1) if m else '?'}")
    first = re.match(r"^\s*(\w+)", stmt)
    if not first:
        raise ValueError("无法解析 SQL 首关键字")
    kw = first.group(1).upper()
    all_allowed = _READONLY_ALLOWED_START | _WRITE_ALLOWED_START
    if kw not in all_allowed:
        raise ValueError(
            f"不支持的语句类型: {kw}。允许: {', '.join(sorted(all_allowed))}"
        )
    return raw.rstrip().rstrip(";")


_TABLE_NAME_PAT = r'"?[A-Za-z_][A-Za-z0-9_]*"?(?:\."?[A-Za-z_][A-Za-z0-9_]*"?)?'


def _extract_table_and_where(sql: str) -> tuple[str, str | None]:
    """返回 (table_name, where_clause_or_None)，仅处理简单单表语句。"""
    cleaned = _strip_sql_comments(sql).strip()
    kw_m = re.match(r"^\s*(\w+)", cleaned)
    if not kw_m:
        return ("", None)
    op = kw_m.group(1).upper()
    if op == "DELETE":
        m = re.match(
            rf"DELETE\s+FROM\s+({_TABLE_NAME_PAT})\s*(WHERE\s+.+)?$",
            cleaned,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return ("", None)
        table = m.group(1).strip('"').split(".")[-1]
        where = m.group(2).strip() if m.group(2) else None
        return (table, where)
    if op == "UPDATE":
        m = re.match(
            rf"UPDATE\s+({_TABLE_NAME_PAT})\s+SET\s+.+?(WHERE\s+.+)?$",
            cleaned,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return ("", None)
        table = m.group(1).strip('"').split(".")[-1]
        where = m.group(2).strip() if m.group(2) else None
        return (table, where)
    return ("", None)


def _load_connect() -> Callable[..., Any]:
    mode = (os.environ.get("KB_DRIVER") or "auto").strip().lower()

    def from_ksycopg2() -> Any:
        import ksycopg2  # type: ignore
        return ksycopg2.connect

    def from_psycopg2() -> Any:
        import psycopg2  # type: ignore
        return psycopg2.connect

    if mode == "ksycopg2":
        try:
            return from_ksycopg2()
        except ImportError as e:
            print(json.dumps({"ok": False, "error": "KB_DRIVER=ksycopg2 但未安装 ksycopg2。", "detail": str(e)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(2)

    if mode == "psycopg2":
        try:
            return from_psycopg2()
        except ImportError as e:
            print(json.dumps({"ok": False, "error": "未安装 psycopg2。请: pip install -r requirements.txt", "detail": str(e)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(2)

    try:
        return from_ksycopg2()
    except ImportError:
        try:
            return from_psycopg2()
        except ImportError as e:
            print(json.dumps({"ok": False, "error": "未找到 ksycopg2 或 psycopg2。", "detail": str(e)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(2)


def _connect(connect_fn: Callable[..., Any]):
    uri = os.environ.get("KB_URI") or os.environ.get("KINGBASE_URI")
    if uri:
        return connect_fn(uri)
    user = os.environ.get("KB_USER")
    password = os.environ.get("KB_PASSWORD")
    host = os.environ.get("KB_HOST", "localhost")
    port = int(os.environ.get("KB_PORT", "54321"))
    dbname = os.environ.get("KB_DATABASE") or os.environ.get("KB_DB")
    if not user or password is None or not dbname:
        print(json.dumps({"ok": False, "error": "请设置 KB_URI 或 KB_USER + KB_PASSWORD + KB_DATABASE"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
    return connect_fn(host=host, port=port, dbname=dbname, user=user, password=password)


def _rows_to_json(columns: list[str] | None, rows: list[tuple[Any, ...]], max_rows: int) -> dict[str, Any]:
    cols = columns or []
    limited = rows[:max_rows]
    dict_rows = [dict(zip(cols, row)) for row in limited]
    return {
        "columns": cols,
        "row_count": len(rows),
        "returned": len(dict_rows),
        "truncated": len(rows) > max_rows,
        "rows": dict_rows,
    }


def _set_search_path(cur: Any, schema: str) -> None:
    s = schema.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s):
        raise ValueError("KB_SCHEMA 仅支持未加引号的简单标识符")
    cur.execute("SET search_path TO " + s)


def _backup_dir() -> Path:
    d = os.environ.get("KB_BACKUP_DIR") or ".kb_backups"
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _backup_affected_rows(conn: Any, sql: str) -> dict[str, Any]:
    """在写操作前备份受影响的行；INSERT 不需备份。"""
    cleaned = _strip_sql_comments(sql).strip()
    kw_m = re.match(r"^\s*(\w+)", cleaned)
    op = kw_m.group(1).upper() if kw_m else ""
    if op == "INSERT":
        return {"skipped": True, "reason": "INSERT 操作无需备份已有数据"}

    table, where = _extract_table_and_where(sql)
    if not table:
        return {"skipped": True, "reason": "无法解析表名，跳过备份"}

    select_sql = f"SELECT * FROM {table}"
    if where:
        select_sql += f" {where}"

    cur = conn.cursor()
    cur.execute(select_sql)
    columns = [d[0] for d in cur.description] if cur.description else []
    rows = list(cur.fetchall())
    dict_rows = [dict(zip(columns, row)) for row in rows]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    slug = re.sub(r"[^A-Za-z0-9_]", "_", table)
    filename = f"{op.lower()}_{slug}_{ts}.json"
    backup_path = _backup_dir() / filename
    payload = {
        "operation": op,
        "table": table,
        "where": where,
        "backed_up_at": datetime.now().isoformat(),
        "row_count": len(dict_rows),
        "columns": columns,
        "rows": dict_rows,
    }
    backup_path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return {"skipped": False, "file": str(backup_path), "row_count": len(dict_rows)}


def run_query(sql: str, max_rows: int) -> dict[str, Any]:
    """只读查询执行。"""
    validated = validate_readonly_sql(sql)
    connect_fn = _load_connect()
    conn = _connect(connect_fn)
    try:
        schema = os.environ.get("KB_SCHEMA")
        cur = conn.cursor()
        if schema:
            _set_search_path(cur, schema)
        cur.execute(validated)
        if cur.description:
            columns = [d[0] for d in cur.description]
            rows = list(cur.fetchall())
            payload = _rows_to_json(columns, rows, max_rows)
        else:
            payload = {"columns": [], "row_count": cur.rowcount if cur.rowcount is not None else 0, "returned": 0, "truncated": False, "rows": [], "note": "无结果集"}
        out: dict[str, Any] = {"ok": True, "sql": validated, **payload}
        if schema:
            out["search_path"] = schema.strip()
        return out
    finally:
        conn.close()


def run_write(sql: str) -> dict[str, Any]:
    """写操作执行（INSERT/UPDATE/DELETE），UPDATE/DELETE 前自动备份。"""
    validated = validate_write_sql(sql)
    kw_m = re.match(r"^\s*(\w+)", _strip_sql_comments(validated))
    op = kw_m.group(1).upper() if kw_m else ""

    if op in _READONLY_ALLOWED_START:
        return run_query(sql, int(os.environ.get("KB_MAX_ROWS", "500")))

    connect_fn = _load_connect()
    conn = _connect(connect_fn)
    try:
        schema = os.environ.get("KB_SCHEMA")
        cur = conn.cursor()
        if schema:
            _set_search_path(cur, schema)

        backup_info = _backup_affected_rows(conn, validated)

        cur.execute(validated)
        conn.commit()

        out: dict[str, Any] = {
            "ok": True,
            "operation": op,
            "sql": validated,
            "rows_affected": cur.rowcount if cur.rowcount is not None else -1,
            "backup": backup_info,
        }
        return out
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="人大金仓 KingbaseES SQL — 支持只读与写操作")
    p.add_argument("--sql", help="SQL 字符串")
    p.add_argument("--file", "-f", help="从文件读取 SQL")
    p.add_argument("--max-rows", type=int, default=int(os.environ.get("KB_MAX_ROWS", "500")), help="最多返回行数（默认 500）")
    p.add_argument("--validate-only", action="store_true", help="仅校验，不执行")
    p.add_argument("--allow-write", action="store_true", help="允许 INSERT/UPDATE/DELETE（需配合 --confirm）")
    p.add_argument("--confirm", action="store_true", help="确认已获用户授权执行写操作")
    args = p.parse_args()

    if bool(args.sql) == bool(args.file):
        print(json.dumps({"ok": False, "error": "请指定其一: --sql 或 --file"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    sql = args.sql if args.sql else open(args.file, encoding="utf-8").read()

    if args.validate_only:
        try:
            if args.allow_write:
                v = validate_write_sql(sql)
            else:
                v = validate_readonly_sql(sql)
            print(json.dumps({"ok": True, "validated": v}, ensure_ascii=False))
        except ValueError as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)
        return

    if args.allow_write:
        if not args.confirm:
            print(json.dumps({
                "ok": False,
                "error": "写操作需要用户确认。请先向用户展示 SQL，获得同意后加 --confirm 重新执行。",
                "hint": "--allow-write 必须配合 --confirm 使用",
            }, ensure_ascii=False))
            sys.exit(1)
        try:
            out = run_write(sql)
            print(json.dumps(out, ensure_ascii=False, default=str))
        except ValueError as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)
        except Exception as e:
            print(json.dumps({"ok": False, "error": "执行失败", "detail": str(e)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(3)
        return

    try:
        out = run_query(sql, max(1, args.max_rows))
        print(json.dumps(out, ensure_ascii=False, default=str))
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "执行失败", "detail": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()

