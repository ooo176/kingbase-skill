#!/usr/bin/env python3
"""
只读执行人大金仓 KingbaseES SQL：校验通过后连接并输出 JSON。
禁止 INSERT/UPDATE/DELETE/DDL 等写操作。

驱动优先级（环境变量 KB_DRIVER）：
  auto（默认）— 先试 ksycopg2（官方，随安装包），失败再用 psycopg2
  ksycopg2 — 仅官方驱动
  psycopg2 — 仅 psycopg2 / psycopg2-binary
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Callable


def _strip_sql_comments(sql: str) -> str:
    """移除块注释与行注释（字符串字面量内含 -- 或 /* 时可能误判）。"""
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    s = re.sub(r"--[^\n]*", " ", s)
    return s


_FORBIDDEN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|MERGE|REPLACE|"
    r"DROP|CREATE|ALTER|TRUNCATE|RENAME|"
    r"GRANT|REVOKE|COMMIT|ROLLBACK|SAVEPOINT|"
    r"CALL|EXECUTE|EXEC"
    r")\b",
    re.IGNORECASE,
)

_ALLOWED_START = frozenset(
    {"SELECT", "WITH", "EXPLAIN", "SHOW", "DESC", "DESCRIBE"}
)


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
    if _FORBIDDEN.search(stmt):
        m = _FORBIDDEN.search(stmt)
        raise ValueError(f"只读模式禁止关键字: {m.group(1) if m else '?'}")
    first = re.match(r"^\s*(\w+)", stmt)
    if not first:
        raise ValueError("无法解析 SQL 首关键字")
    kw = first.group(1).upper()
    if kw not in _ALLOWED_START:
        raise ValueError(
            f"只读模式仅允许以以下关键字开头: {', '.join(sorted(_ALLOWED_START))}"
        )
    return raw.rstrip().rstrip(";")


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
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "KB_DRIVER=ksycopg2 但未安装 ksycopg2。请从金仓安装包安装并配置 LD_LIBRARY_PATH。",
                        "detail": str(e),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            sys.exit(2)

    if mode == "psycopg2":
        try:
            return from_psycopg2()
        except ImportError as e:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "未安装 psycopg2。请: pip install -r requirements.txt",
                        "detail": str(e),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            sys.exit(2)

    # auto
    try:
        return from_ksycopg2()
    except ImportError:
        try:
            return from_psycopg2()
        except ImportError as e:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "未找到 ksycopg2 或 psycopg2。请 pip install psycopg2-binary，或从金仓介质安装 ksycopg2。",
                        "detail": str(e),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
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
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "请设置 KB_URI（或 KINGBASE_URI），或 KB_USER + KB_PASSWORD + KB_DATABASE（可选 KB_HOST、KB_PORT，默认端口 54321）",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(2)

    return connect_fn(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )


def _rows_to_json(
    columns: list[str] | None, rows: list[tuple[Any, ...]], max_rows: int
) -> dict[str, Any]:
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
    """使用简单标识符规则，避免仅安装 ksycopg2 时依赖 psycopg2.sql。"""
    s = schema.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s):
        raise ValueError("KB_SCHEMA 仅支持未加引号的简单标识符（字母/数字/下划线）")
    cur.execute("SET search_path TO " + s)


def run_query(sql: str, max_rows: int) -> dict[str, Any]:
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
            payload = {
                "columns": [],
                "row_count": cur.rowcount if cur.rowcount is not None else 0,
                "returned": 0,
                "truncated": False,
                "rows": [],
                "note": "无结果集（可能为仅 EXPLAIN/SHOW 等，依驱动行为而定）",
            }
        out: dict[str, Any] = {"ok": True, "sql": validated, **payload}
        if schema:
            out["search_path"] = schema.strip()
        return out
    finally:
        conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="人大金仓 KingbaseES 只读 SQL 查询，输出 JSON")
    p.add_argument("--sql", help="SQL 字符串")
    p.add_argument("--file", "-f", help="从文件读取 SQL")
    p.add_argument(
        "--max-rows",
        type=int,
        default=int(os.environ.get("KB_MAX_ROWS", "500")),
        help="最多返回行数（默认 500，可用环境变量 KB_MAX_ROWS）",
    )
    p.add_argument(
        "--validate-only",
        action="store_true",
        help="仅校验 SQL，不连接数据库",
    )
    args = p.parse_args()

    if bool(args.sql) == bool(args.file):
        print(
            json.dumps(
                {"ok": False, "error": "请指定其一: --sql 或 --file"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    sql = args.sql if args.sql else open(args.file, encoding="utf-8").read()

    if args.validate_only:
        try:
            v = validate_readonly_sql(sql)
            print(json.dumps({"ok": True, "validated": v}, ensure_ascii=False))
        except ValueError as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)
        return

    try:
        out = run_query(sql, max(1, args.max_rows))
        print(json.dumps(out, ensure_ascii=False, default=str))
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        print(
            json.dumps({"ok": False, "error": "执行失败", "detail": str(e)}, ensure_ascii=False),
            file=sys.stderr,
        )
        sys.exit(3)


if __name__ == "__main__":
    main()
