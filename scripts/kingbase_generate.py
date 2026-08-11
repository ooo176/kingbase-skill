#!/usr/bin/env python3
"""
人大金仓 KingbaseES 测试数据生成脚本。

自动发现表结构、外键关系，推断字段生成规则，生成测试数据。
执行前自动备份旧表（RENAME 后缀），失败时回滚。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

try:
    from faker import Faker
except ImportError:
    print(
        json.dumps(
            {"ok": False, "error": "未安装 faker。请执行: pip install faker"},
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    sys.exit(2)


def _load_connect() -> Callable[..., Any]:
    """加载数据库连接函数（复用 kingbase_query.py 的逻辑）"""
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
                        "error": "KB_DRIVER=ksycopg2 但未安装 ksycopg2。",
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
                        "error": "未找到 ksycopg2 或 psycopg2。",
                        "detail": str(e),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            sys.exit(2)


def _connect(connect_fn: Callable[..., Any]):
    """建立数据库连接"""
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
                    "error": "请设置 KB_URI 或 KB_USER + KB_PASSWORD + KB_DATABASE",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(2)
    return connect_fn(host=host, port=port, dbname=dbname, user=user, password=password)


def _discover_tables(conn: Any, schema: str) -> list[str]:
    """发现 schema 下所有用户表"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """,
        (schema,),
    )
    return [row[0] for row in cur.fetchall()]


def _discover_columns(conn: Any, schema: str, table: str) -> list[dict[str, Any]]:
    """发现表的列信息"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default,
               character_maximum_length, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """,
        (schema, table),
    )
    columns = []
    for row in cur.fetchall():
        columns.append(
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2] == "YES",
                "default": row[3],
                "max_length": row[4],
                "precision": row[5],
                "scale": row[6],
            }
        )
    return columns


def _discover_foreign_keys(conn: Any, schema: str) -> dict[str, list[dict[str, str]]]:
    """发现外键关系，返回 {table_name: [{column, ref_table, ref_column}]}"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT tc.table_name, kcu.column_name,
               ccu.table_name AS foreign_table_name,
               ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s
    """,
        (schema,),
    )
    fks: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in cur.fetchall():
        fks[row[0]].append(
            {"column": row[1], "ref_table": row[2], "ref_column": row[3]}
        )
    return dict(fks)


def _topological_sort(tables: list[str], fks: dict[str, list[dict[str, str]]]) -> list[str]:
    """拓扑排序：父表优先于子表"""
    in_degree = {t: 0 for t in tables}
    graph = defaultdict(list)

    for table, foreign_keys in fks.items():
        if table not in in_degree:
            continue
        for fk in foreign_keys:
            ref_table = fk["ref_table"]
            if ref_table in in_degree and ref_table != table:
                graph[ref_table].append(table)
                in_degree[table] += 1

    queue = [t for t in tables if in_degree[t] == 0]
    result = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(tables):
        # 存在循环依赖，返回原始顺序
        return tables

    return result


def _infer_column_rule(col: dict[str, Any], faker: Faker) -> Callable[[], Any]:
    """根据列名和类型推断生成策略"""
    name = col["name"].lower()
    dtype = col["type"].lower()
    nullable = col["nullable"]

    # 有默认值且是序列，跳过
    if col["default"] and "nextval" in str(col["default"]).lower():
        return lambda: None  # 数据库自动生成

    # NULL 策略：10% 概率返回 NULL
    def maybe_null(fn: Callable[[], Any]) -> Callable[[], Any]:
        if nullable and "id" not in name:
            import random
            return lambda: None if random.random() < 0.1 else fn()
        return fn

    # 根据列名推断
    if "name" in name or "姓名" in name or "mc" in name:
        return maybe_null(lambda: faker.name())
    if "email" in name or "邮箱" in name:
        return maybe_null(lambda: faker.email())
    if "phone" in name or "电话" in name or "mobile" in name or "lxfs" in name:
        return maybe_null(lambda: faker.phone_number())
    if "address" in name or "地址" in name or "dz" in name:
        return maybe_null(lambda: faker.address().replace("\n", " "))
    if "company" in name or "公司" in name or "dw" in name:
        return maybe_null(lambda: faker.company())
    if "url" in name or "网址" in name:
        return maybe_null(lambda: faker.url())
    if "date" in name or "时间" in name or "time" in name or "created" in name or "updated" in name:
        if "timestamp" in dtype or "date" in dtype:
            return maybe_null(lambda: faker.date_time_between(start_date="-2y", end_date="now"))
    if "uuid" in dtype:
        return lambda: str(uuid.uuid4())
    if "code" in name or "编码" in name or "dm" in name:
        return maybe_null(lambda: faker.bothify(text="????####"))

    # 根据类型推断
    if "int" in dtype or "serial" in dtype:
        return maybe_null(lambda: faker.random_int(min=1, max=999999))
    if "bool" in dtype:
        return maybe_null(lambda: faker.boolean())
    if "numeric" in dtype or "decimal" in dtype or "float" in dtype or "double" in dtype:
        return maybe_null(lambda: round(faker.random.uniform(0, 100000), 2))
    if "char" in dtype or "text" in dtype:
        max_len = col["max_length"] or 50
        return maybe_null(lambda: faker.text(max_nb_chars=min(max_len, 200))[:max_len])

    # 兜底：随机文本
    return maybe_null(lambda: faker.word())


def _parse_tables_spec(tables_spec: str | None, default_count: int) -> dict[str, int]:
    """解析 --tables 参数，返回 {table_name: row_count}"""
    if not tables_spec:
        return {}

    result = {}
    for part in tables_spec.split(","):
        part = part.strip()
        if ":" in part:
            table, count_str = part.split(":", 1)
            result[table.strip()] = int(count_str.strip())
        else:
            result[part] = default_count
    return result


def _parse_rules_json(rules_json: str | None) -> dict[str, dict[str, dict[str, Any]]]:
    """解析 --rules-json 参数"""
    if not rules_json:
        return {}
    return json.loads(rules_json)


def _generate_data(
    conn: Any,
    schema: str,
    tables: list[str],
    table_counts: dict[str, int],
    rules: dict[str, dict[str, dict[str, Any]]],
    locale: str,
    dry_run: bool,
    suffix: str,
) -> dict[str, Any]:
    """生成测试数据"""
    faker = Faker(locale)

    # 发现外键关系
    fks = _discover_foreign_keys(conn, schema)

    # 拓扑排序
    sorted_tables = _topological_sort(tables, fks)

    # 准备执行计划
    plan = []
    generated_pks: dict[str, list[Any]] = {}  # {table: [pk_values]}

    for table in sorted_tables:
        row_count = table_counts.get(table, 0)
        if row_count <= 0:
            continue

        # 获取表结构
        columns = _discover_columns(conn, schema, table)
        if not columns:
            continue

        # 获取当前行数（用于备份信息）
        cur = conn.cursor()
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        current_rows = cur.fetchone()[0]

        plan.append({
            "table": table,
            "rows_to_generate": row_count,
            "current_rows": current_rows,
            "columns": [c["name"] for c in columns],
        })

        if dry_run:
            continue

        # 备份：重命名旧表
        backup_name = f"{table}_{suffix}"
        cur.execute(f'ALTER TABLE "{schema}"."{table}" RENAME TO "{backup_name}"')

        # 创建新表
        cur.execute(f'CREATE TABLE "{schema}"."{table}" (LIKE "{schema}"."{backup_name}" INCLUDING ALL)')

        # 生成数据
        table_rules = rules.get(table, {})
        pk_column = None
        pk_values = []

        for i in range(row_count):
            row_data = {}
            for col in columns:
                col_name = col["name"]

                # 检查是否是外键
                is_fk = False
                if table in fks:
                    for fk in fks[table]:
                        if fk["column"] == col_name:
                            # 从引用表中随机选择
                            ref_table = fk["ref_table"]
                            if ref_table in generated_pks and generated_pks[ref_table]:
                                import random
                                row_data[col_name] = random.choice(generated_pks[ref_table])
                                is_fk = True
                            break

                if is_fk:
                    continue

                # 检查是否有自定义规则
                if col_name in table_rules:
                    rule = table_rules[col_name]
                    if rule.get("type") == "enum":
                        import random
                        row_data[col_name] = random.choice(rule["values"])
                    elif rule.get("type") == "sequence":
                        pattern = rule.get("pattern", "{seq}")
                        row_data[col_name] = pattern.replace("{seq}", str(i + 1))
                    continue

                # 跳过自增列
                if col["default"] and "nextval" in str(col["default"]).lower():
                    continue

                # 自动推断
                generator = _infer_column_rule(col, faker)
                value = generator()
                if value is not None:
                    row_data[col_name] = value

                # 记录主键
                if "id" == col_name.lower() and not pk_column:
                    pk_column = col_name
                    if value is not None:
                        pk_values.append(value)

            # 插入数据
            if row_data:
                cols = list(row_data.keys())
                vals = [row_data[c] for c in cols]
                placeholders = ", ".join(["%s"] * len(cols))
                col_names = ", ".join([f'"{c}"' for c in cols])
                cur.execute(
                    f'INSERT INTO "{schema}"."{table}" ({col_names}) VALUES ({placeholders})',
                    vals,
                )

        # 记录生成的主键值（用于外键引用）
        if pk_column:
            cur.execute(f'SELECT "{pk_column}" FROM "{schema}"."{table}"')
            generated_pks[table] = [row[0] for row in cur.fetchall()]

        conn.commit()

    return {
        "ok": True,
        "mode": "generate",
        "schema": schema,
        "suffix": suffix,
        "dry_run": dry_run,
        "plan": plan,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="人大金仓 KingbaseES 测试数据生成")
    p.add_argument("--count", "-n", type=int, help="每张表的默认行数")
    p.add_argument("--schema", default=os.environ.get("KB_SCHEMA", "public"), help="目标 schema（默认 KB_SCHEMA 或 public）")
    p.add_argument("--tables", help="逗号分隔的表名或 表名:行数（如 dept:10,emp:100）")
    p.add_argument("--exclude-tables", help="逗号分隔的排除表名")
    p.add_argument("--rules-json", help="字段规则 JSON")
    p.add_argument("--dry-run", action="store_true", help="只输出计划，不执行")
    p.add_argument("--confirm", action="store_true", help="确认执行（必须）")
    p.add_argument("--suffix", default=datetime.now().strftime("%Y%m%d"), help="备份后缀（默认 YYYYMMDD）")
    p.add_argument("--locale", default="zh_CN", help="Faker 语言（默认 zh_CN）")
    args = p.parse_args()

    if not args.dry_run and not args.confirm:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "生成数据需要用户确认。请先 --dry-run 查看计划，确认后加 --confirm 执行。",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    # 连接数据库
    connect_fn = _load_connect()
    conn = _connect(connect_fn)

    try:
        # 发现表
        all_tables = _discover_tables(conn, args.schema)

        # 解析表和行数
        table_counts = _parse_tables_spec(args.tables, args.count or 100)

        # 如果未指定表，使用所有表
        if not table_counts:
            table_counts = {t: args.count or 100 for t in all_tables}

        # 排除表
        if args.exclude_tables:
            exclude = set(t.strip() for t in args.exclude_tables.split(","))
            table_counts = {t: c for t, c in table_counts.items() if t not in exclude}

        # 验证表存在
        tables = [t for t in table_counts.keys() if t in all_tables]
        missing = set(table_counts.keys()) - set(tables)
        if missing:
            print(
                json.dumps(
                    {"ok": False, "error": f"表不存在: {', '.join(missing)}"},
                    ensure_ascii=False,
                )
            )
            sys.exit(1)

        # 解析规则
        rules = _parse_rules_json(args.rules_json)

        # 生成数据
        result = _generate_data(
            conn,
            args.schema,
            tables,
            table_counts,
            rules,
            args.locale,
            args.dry_run,
            args.suffix,
        )

        print(json.dumps(result, ensure_ascii=False, default=str))

    except Exception as e:
        conn.rollback()
        print(
            json.dumps(
                {"ok": False, "error": "执行失败", "detail": str(e)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(3)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
