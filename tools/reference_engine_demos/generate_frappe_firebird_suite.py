#!/usr/bin/env python3
# SPDX-License-Identifier: PostgreSQL
"""Clean-room Firebird 5.0 enterprise schema & sample-data generator.

Analyzes the donor project collection in
``/home/dcalford/Sandbox/donor_release_acquisition/frappe`` (Frappe DocType
definitions, Custom Field extensions, Frappe Books schemas, Datum ClickHouse
migrations, Cargo telemetry queries, Stalwart SQL directory/store schemas, Boat
VM persistence models, Mobile Accounting SQL tables, and PyWall SQL tables),
adapts all metadata to idiomatic Firebird 5.0 SQL (32 KB pages, UTF8, <=63-char
unquoted SNAKE_CASE identifiers, Firebird Domains, Sequences, Exceptions, Roles,
row-buffer size guards, enforced FOREIGN KEY constraints, Triggers, Views,
Stored Procedures, Functions, and Packages), populates rich multi-module
enterprise sample data plus FK-valid rows across every generated table, and
optionally registers ``frappe_suite.fdb`` in ScratchRobin.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DONOR_ROOT = Path("/home/dcalford/Sandbox/donor_release_acquisition/frappe")
DEFAULT_DIALECT_JSON = (
    REPO_ROOT
    / "web/pgadmin/cdeadmin/providers/firebird/firebird_dialect_5_0_4.json"
)
DEFAULT_DB_PATH = "/var/lib/firebird/data/frappe_suite.fdb"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 53050
DEFAULT_USER = "SYSDBA"
DEFAULT_PASSWORD = os.environ.get(
    "CDEADMIN_FIREBIRD_DEMO_PASSWORD", "CDEadminDemo-2026!"
)
DEFAULT_CONTAINER = "cdeadmin-demo-firebird"

# Priority order when multiple donor repos define the same Frappe DocType.
APP_PRIORITY = {
    "frappe": 1,
    "erpnext": 2,
    "hrms": 3,
    "crm": 4,
    "helpdesk": 5,
    "lending": 6,
    "payments": 7,
    "education": 8,
    "lms": 9,
    "insights": 10,
    "drive": 11,
    "raven": 12,
    "gameplan": 13,
    "mail": 14,
    "wiki": 15,
    "builder": 16,
    "press": 17,
    "central": 18,
    "suite": 19,
    "suite_cloud": 20,
    "webshop": 21,
    "ecommerce_integrations": 22,
    "hospitality": 23,
    "agriculture": 24,
    "non_profit": 25,
    "healthcare": 26,
    "cargo": 27,
    "atlas": 28,
    "guard": 29,
    "panoptic": 30,
    "grove": 31,
    "changemakers": 32,
    "whatsapp": 33,
    "telephony": 34,
    "print_designer": 35,
    # Archived / duplicate snapshots get lowest priority (still merged for any extra fields)
    "erpnext_local": 900,
    "erpnext-14": 910,
    "gameplan-old": 920,
    "hub-old": 930,
    "frappe_io_2014": 940,
    "accounting-archive": 950,
    "archives": 960,
}

LAYOUT_ONLY_FIELDTYPES = frozenset({
    "Section Break",
    "Column Break",
    "Tab Break",
    "Page Break",
    "Fold",
    "Heading",
    "Button",
    "HTML",
    "Table",
    "Table MultiSelect",
    "Image",
    "",
})

# Baseline SQL/Firebird 5.0 reserved & context-sensitive keywords (augmented from firebird_dialect_5_0_4.json).
BASE_RESERVED_WORDS = {
    "ADD", "ADMIN", "ALL", "ALTER", "AND", "ANY", "AS", "AT", "AVG", "BEGIN",
    "BETWEEN", "BIGINT", "BINARY", "BIT_LENGTH", "BLOB", "BOOLEAN", "BOTH",
    "BY", "CASE", "CAST", "CHAR", "CHAR_LENGTH", "CHARACTER",
    "CHARACTER_LENGTH", "CHECK", "CLOSE", "COALESCE", "COLLATE", "COLUMN",
    "COMMENT", "COMMIT", "CONNECT", "CONSTRAINT", "CORR", "COUNT",
    "COVAR_POP", "COVAR_SAMP", "CREATE", "CROSS", "CURRENT",
    "CURRENT_CONNECTION", "CURRENT_DATE", "CURRENT_ROLE", "CURRENT_TIME",
    "CURRENT_TIMESTAMP", "CURRENT_TRANSACTION", "CURRENT_USER", "CURSOR",
    "DATE", "DAY", "DEC", "DECFLOAT", "DECIMAL", "DECLARE", "DEFAULT",
    "DELETE", "DELETING", "DETERMINISTIC", "DISCONNECT", "DISTINCT", "DOUBLE",
    "DROP", "ELSE", "END", "ESCAPE", "EXCEPT", "EXCEPTION", "EXECUTE",
    "EXISTS", "EXTERNAL", "EXTRACT", "FALSE", "FETCH", "FILTER", "FLOAT",
    "FOR", "FOREIGN", "FROM", "FULL", "FUNCTION", "GDSCODE", "GLOBAL",
    "GRANT", "GROUP", "HAVING", "HOUR", "IN", "INDEX", "INNER", "INSENSITIVE",
    "INSERT", "INSERTING", "INT", "INT128", "INTEGER", "INTERSECT", "INTO",
    "IS", "JOIN", "LATERAL", "LEADING", "LEFT", "LIKE", "LIMIT", "LOCAL",
    "LOCALTIME", "LOCALTIMESTAMP", "LOWER", "MAX", "MERGE", "MESSAGE", "MIN",
    "MINUTE", "MONTH", "NATIONAL", "NATURAL", "NCHAR", "NO", "NOT", "NULL",
    "NUMERIC", "OCTET_LENGTH", "OF", "OFFSET", "ON", "ONLY", "OPEN", "OR",
    "ORDER", "OUTER", "OVER", "PACKAGE", "PARAMETER", "PASSWORD", "PLAN",
    "POSITION", "POST_EVENT", "PRECISION", "PRIMARY", "PROCEDURE",
    "PUBLICATION", "RDB$DB_KEY", "RDB$RECORD_VERSION", "REAL",
    "RECORD_VERSION", "RECREATE", "RECURSIVE", "REFERENCES", "REGR_AVGX",
    "REGR_AVGY", "REGR_COUNT", "REGR_INTERCEPT", "REGR_R2", "REGR_SLOPE",
    "REGR_SXX", "REGR_SXY", "REGR_SYY", "RELEASE", "RESETTING", "RETURN",
    "RETURNING_VALUES", "RETURNS", "REVOKE", "RIGHT", "ROLE", "ROLLBACK",
    "ROW_COUNT", "ROW_NUMBER", "ROWS", "SAVEPOINT", "SCHEMA", "SCROLL",
    "SECOND", "SELECT", "SENSITIVE", "SEQUENCE", "SESSION", "SET", "SIMILAR",
    "SMALLINT", "SOME", "SQLCODE", "SQLSTATE", "START", "STATEMENT",
    "STDDEV_POP", "STDDEV_SAMP", "SUB_TYPE", "SUM", "SYSTEM", "TABLE",
    "TABLESPACE", "TEMPORARY", "THEN", "TIME", "TIMESTAMP", "TIMEZONE_HOUR",
    "TIMEZONE_MINUTE", "TO", "TRAILING", "TRIGGER", "TRIM", "TRUE", "TYPE",
    "UNBOUNDED", "UNION", "UNIQUE", "UNKNOWN", "UPDATE", "UPDATING", "UPPER",
    "USER", "USING", "VALUE", "VALUES", "VAR_POP", "VAR_SAMP", "VARBINARY",
    "VARCHAR", "VARIABLE", "VARYING", "VIEW", "WHEN", "WHERE", "WHILE",
    "WINDOW", "WITH", "WITHOUT", "YEAR",
}

# Domain specifications: (sql_definition, uncompressed_utf8_bytes)
DOMAINS = [
    ("D_DOC_ID", "VARCHAR(80)", 322),
    ("D_CODE", "VARCHAR(40)", 162),
    ("D_TITLE", "VARCHAR(120)", 482),
    ("D_SHORT_TEXT", "VARCHAR(120)", 482),
    ("D_STATUS", "VARCHAR(64)", 258),
    ("D_EMAIL", "VARCHAR(120)", 482),
    ("D_PHONE", "VARCHAR(40)", 162),
    ("D_URL", "VARCHAR(200)", 802),
    ("D_MONEY", "NUMERIC(18, 4) DEFAULT 0", 8),
    ("D_RATE", "NUMERIC(18, 6) DEFAULT 0", 8),
    ("D_PERCENT", "NUMERIC(9, 4) DEFAULT 0", 8),
    ("D_QTY", "DOUBLE PRECISION DEFAULT 0", 8),
    ("D_BOOL", "BOOLEAN DEFAULT FALSE NOT NULL", 2),
    ("D_DOCSTATUS", "SMALLINT DEFAULT 0 NOT NULL CHECK (VALUE IN (0, 1, 2))", 2),
    ("D_TEXT", "BLOB SUB_TYPE TEXT", 8),
    ("D_JSON", "BLOB SUB_TYPE TEXT", 8),
]
DOMAIN_BYTES = {name: size for name, _defn, size in DOMAINS}
TYPE_BYTES_FALLBACK = {
    "INTEGER DEFAULT 0": 4,
    "INTEGER": 4,
    "BIGINT DEFAULT 0": 8,
    "BIGINT": 8,
    "SMALLINT DEFAULT 0": 2,
    "SMALLINT": 2,
    "DATE": 4,
    "TIMESTAMP": 8,
    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP": 8,
    "TIMESTAMP WITH TIME ZONE": 12,
    "TIME": 4,
    "DOUBLE PRECISION DEFAULT 0": 8,
    "DOUBLE PRECISION": 8,
    "VARCHAR(255)": 1022,
    "VARBINARY(255)": 257,
    "BLOB SUB_TYPE BINARY": 8,
}

# Keep uncompressed UTF8 row width safely under Firebird's 65,535-byte ceiling.
MAX_INLINE_ROW_BYTES = 34000
MAX_FKS_PER_TABLE = 16


@dataclass
class ColumnSpec:
    col_name: str
    fb_type: str
    orig_fieldname: str
    label: str = ""
    fieldtype: str = "Data"
    options: str = ""
    link_target_doctype: str | None = None
    not_null: bool = False
    is_pk: bool = False

    def byte_size(self) -> int:
        if self.fb_type in DOMAIN_BYTES:
            return DOMAIN_BYTES[self.fb_type]
        return TYPE_BYTES_FALLBACK.get(self.fb_type, 256)


@dataclass
class TableSpec:
    table_name: str
    source_app: str
    orig_name: str
    module: str
    kind: str  # 'doctype', 'child', 'single', 'virtual', 'books', 'companion', 'system'
    is_tree: bool = False
    is_submittable: bool = False
    columns: list[ColumnSpec] = field(default_factory=list)
    pk_columns: list[str] = field(default_factory=lambda: ["DOC_NAME"])
    parent_doctypes: set[str] = field(default_factory=set)
    comment: str = ""


@dataclass
class ForeignKeySpec:
    constraint_name: str
    source_table: str
    source_col: str
    target_table: str
    target_col: str = "DOC_NAME"
    on_delete: str = ""
    on_update: str = "ON UPDATE CASCADE"


def load_reserved_words(dialect_json: Path) -> set[str]:
    words = set(BASE_RESERVED_WORDS)
    if dialect_json.is_file():
        data = json.loads(dialect_json.read_text(encoding="utf-8"))
        for rule in data.get("inventories", {}).get("lexical_rules", []):
            token = str(rule.get("native_name") or "").strip().upper()
            if token and re.match(r"^[A-Z_][A-Z0-9_$]*$", token):
                if not rule.get("non_reserved", False):
                    words.add(token)
    return words


def to_snake_upper(raw: str) -> str:
    s = re.sub(r"['\"`]", "", str(raw or "").strip())
    # CamelCase -> SNAKE_CASE
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    if not s:
        s = "ITEM"
    if not re.match(r"^[A-Z]", s):
        s = "N_" + s
    return s


def make_unique_identifier(
    raw: str,
    used: set[str],
    reserved: set[str],
    *,
    prefix: str = "",
    fallback_suffix: str = "_FLD",
    max_len: int = 63,
) -> str:
    base = to_snake_upper(raw)
    if prefix:
        base = f"{prefix}_{base}"
    if base in reserved or base.startswith("RDB$") or base.startswith("MON$") or base.startswith("SEC$"):
        base = f"{base}{fallback_suffix}"
    if len(base) > max_len:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6].upper()
        base = f"{base[: max_len - 7].rstrip('_')}_{digest}"
    candidate = base
    counter = 2
    while candidate in used or candidate in reserved:
        suffix = f"_{counter}"
        candidate = f"{base[: max_len - len(suffix)].rstrip('_')}{suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def map_field_to_firebird(
    fieldname: str, fieldtype: str, options: str
) -> tuple[str, str | None]:
    ft = (fieldtype or "Data").strip()
    fn_low = (fieldname or "").lower()
    opt_clean = str(options or "").strip().splitlines()[0].strip() if options else ""

    if ft == "Link":
        return "D_DOC_ID", (opt_clean or None)
    if ft in ("Dynamic Link", "DynamicLink"):
        return "D_DOC_ID", None
    if ft == "Check":
        return "D_BOOL", None
    if ft == "Int":
        return "INTEGER DEFAULT 0", None
    if ft in ("Long Int", "Duration"):
        return "BIGINT DEFAULT 0", None
    if ft == "Currency":
        return "D_MONEY", None
    if ft == "Float":
        if "rate" in fn_low or "exchange" in fn_low:
            return "D_RATE", None
        return "D_QTY", None
    if ft in ("Percent", "Rating"):
        return "D_PERCENT", None
    if ft == "Date":
        return "DATE", None
    if ft == "Datetime":
        return "TIMESTAMP", None
    if ft == "Time":
        return "TIME", None
    if ft == "Select":
        return "D_STATUS", None
    if ft in ("Phone",):
        return "D_PHONE", None
    if ft in ("Color", "Icon"):
        return "D_CODE", None
    if ft in ("Attach", "Attach Image", "Attachment", "AttachImage"):
        return "D_URL", None
    if ft in ("Password", "Secret"):
        return "VARCHAR(255)", None
    if ft == "JSON":
        return "D_JSON", None
    if ft in (
        "Small Text",
        "Text",
        "Long Text",
        "Text Editor",
        "Markdown Editor",
        "HTML Editor",
        "Code",
        "Geolocation",
        "Signature",
    ):
        return "D_TEXT", None
    # Data / Read Only / Autocomplete / Barcode
    if "email" in fn_low:
        return "D_EMAIL", None
    if "phone" in fn_low or "mobile" in fn_low:
        return "D_PHONE", None
    if fn_low.endswith("_url") or fn_low in ("url", "website", "route"):
        return "D_URL", None
    if fn_low.endswith("_code") or fn_low in ("currency", "uom", "abbr", "language", "country_code"):
        return "D_CODE", None
    return "D_SHORT_TEXT", None


def enforce_row_byte_budget(table: TableSpec) -> int:
    """Demote wide non-key VARCHAR columns to D_TEXT if table exceeds inline budget."""
    total = sum(c.byte_size() for c in table.columns)
    if total <= MAX_INLINE_ROW_BYTES:
        return 0
    demoted = 0
    # Demote from tail first, skipping PK and FK Link columns.
    for col in reversed(table.columns):
        if total <= MAX_INLINE_ROW_BYTES:
            break
        if col.is_pk or col.link_target_doctype or col.col_name in (
            "DOC_NAME",
            "PARENT_ID",
            "PARENT_TYPE",
            "PARENT_FIELD",
            "OWNER_USER",
            "MODIFIED_BY",
        ):
            continue
        old_bytes = col.byte_size()
        if old_bytes > 16 and col.fb_type in (
            "D_URL",
            "D_SHORT_TEXT",
            "D_TITLE",
            "D_EMAIL",
            "D_STATUS",
            "VARCHAR(255)",
        ):
            col.fb_type = "D_TEXT"
            total = total - old_bytes + col.byte_size()
            demoted += 1
    # If a massive table still exceeds budget because it has >110 Link columns,
    # demote trailing unindexed Link columns beyond the FK cap to D_TEXT.
    if total > MAX_INLINE_ROW_BYTES:
        fk_seen = 0
        for col in table.columns:
            if col.link_target_doctype:
                fk_seen += 1
                if fk_seen > MAX_FKS_PER_TABLE and total > MAX_INLINE_ROW_BYTES:
                    old_bytes = col.byte_size()
                    col.fb_type = "D_TEXT"
                    col.link_target_doctype = None
                    total = total - old_bytes + col.byte_size()
                    demoted += 1
    return demoted


def build_standard_frappe_system_columns(
    *, is_child: bool, is_tree: bool
) -> list[ColumnSpec]:
    cols = [
        ColumnSpec(
            "DOC_NAME", "D_DOC_ID", "name", "Document ID", "Data",
            not_null=True, is_pk=True,
        ),
        ColumnSpec(
            "CREATION_TS", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "creation",
            "Created On", "Datetime",
        ),
        ColumnSpec(
            "MODIFIED_TS", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "modified",
            "Modified On", "Datetime",
        ),
        ColumnSpec("MODIFIED_BY", "D_DOC_ID", "modified_by", "Modified By", "Data"),
        ColumnSpec("OWNER_USER", "D_DOC_ID", "owner", "Owner", "Data"),
        ColumnSpec("DOCSTATUS", "D_DOCSTATUS", "docstatus", "Document Status", "Int"),
        ColumnSpec("IDX_NO", "INTEGER DEFAULT 0", "idx", "Row Index", "Int"),
    ]
    if is_child:
        cols.extend([
            ColumnSpec("PARENT_ID", "D_DOC_ID", "parent", "Parent Document", "Data"),
            ColumnSpec("PARENT_FIELD", "D_CODE", "parentfield", "Parent Field", "Data"),
            ColumnSpec("PARENT_TYPE", "D_SHORT_TEXT", "parenttype", "Parent DocType", "Data"),
        ])
    if is_tree:
        cols.extend([
            ColumnSpec("LFT_NODE", "INTEGER DEFAULT 0", "lft", "Tree Left", "Int"),
            ColumnSpec("RGT_NODE", "INTEGER DEFAULT 0", "rgt", "Tree Right", "Int"),
            ColumnSpec("OLD_PARENT", "D_DOC_ID", "old_parent", "Old Parent", "Data"),
        ])
    return cols


def discover_and_compile_schemas(
    donor_root: Path, reserved: set[str]
) -> tuple[list[dict], dict[str, TableSpec], dict[str, str], list[ForeignKeySpec]]:
    """Scan all 235 donor repositories and compile deduplicated Firebird TableSpecs."""
    project_catalog: list[dict] = []
    raw_doctypes: dict[str, list[tuple[int, str, dict]]] = defaultdict(list)
    custom_fields_by_dt: dict[str, list[dict]] = defaultdict(list)
    child_parent_map: dict[str, set[str]] = defaultdict(set)

    repo_dirs = sorted(
        [p for p in donor_root.iterdir() if p.is_dir() and not p.name.startswith(".")]
    )

    for repo_dir in repo_dirs:
        repo_name = repo_dir.name
        prio = APP_PRIORITY.get(repo_name, 100)
        dt_count = 0

        for jpath in repo_dir.rglob("doctype/*/*.json"):
            if jpath.parent.name != jpath.stem:
                continue
            try:
                doc = json.loads(jpath.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            if not isinstance(doc, dict) or (
                doc.get("doctype") != "DocType" and "fields" not in doc
            ):
                continue
            dt_name = str(doc.get("name") or jpath.stem).strip()
            raw_doctypes[dt_name].append((prio, repo_name, doc))
            dt_count += 1
            for f in doc.get("fields", []):
                if isinstance(f, dict) and f.get("fieldtype") in (
                    "Table",
                    "Table MultiSelect",
                ):
                    opt = str(f.get("options") or "").strip().splitlines()[0].strip()
                    if opt:
                        child_parent_map[opt].add(dt_name)

        # Custom field JSON fixtures
        for cf_path in repo_dir.rglob("*custom_field*.json"):
            try:
                cf_data = json.loads(
                    cf_path.read_text(encoding="utf-8", errors="ignore")
                )
            except Exception:
                continue
            items = cf_data if isinstance(cf_data, list) else [cf_data]
            for item in items:
                if isinstance(item, dict) and item.get("dt") and item.get("fieldname"):
                    custom_fields_by_dt[str(item["dt"]).strip()].append(item)

        if repo_name == "books":
            category = "Standalone Desktop Accounting (TypeScript/JSON Schemas)"
        elif repo_name in ("datum", "stalwart", "mobile-accounting", "pywall", "boat"):
            category = "Companion SQL / Systems Service"
        elif repo_name == "cargo":
            category = "Frappe App + Telemetry SQL Suite"
        elif dt_count > 0 or list(repo_dir.glob("*/hooks.py")):
            category = "Frappe Application"
        else:
            category = "UI Library / CLI / Documentation / Infrastructure"

        project_catalog.append({
            "repo_name": repo_name,
            "category": category,
            "doctype_count": dt_count,
        })

    used_table_names: set[str] = set()
    tables_by_name: dict[str, TableSpec] = {}
    doctype_to_table: dict[str, str] = {}

    # Reserve explicit system & companion table names first so no DocType collides with them.
    explicit_system_names = {
        "SUITE_PROJECT_CATALOG",
        "FRAPPE_AUTH",
        "FRAPPE_USER_SETTINGS",
        "FRAPPE_GLOBAL_SEARCH",
        "FRAPPE_SINGLES_KV",
        "FRAPPE_SERIES",
        "DATUM_SAMPLES",
        "DATUM_DAILY_INGESTION_STATS",
        "DATUM_LOGS",
        "DATUM_DAILY_LOG_STATS",
        "DATUM_TRACES",
        "STALWART_ACCOUNTS",
        "STALWART_GROUP_MEMBERS",
        "STALWART_EMAILS",
        "STALWART_STORE_DATA",
        "STALWART_STORE_INDEX",
        "STALWART_STORE_COUNTER",
        "STALWART_STORE_BLOB",
        "BOAT_VIRTUAL_MACHINE",
        "BOAT_DECISION_JOURNAL",
        "BOAT_VOLUME",
        "MOBACC_ACCOUNT",
        "MOBACC_PARTY",
        "MOBACC_TAX",
        "MOBACC_ITEM",
        "PYWALL_WALL",
    }
    used_table_names.update(explicit_system_names)

    # 1. Compile all 2,853 unique Frappe DocTypes
    for dt_name in sorted(raw_doctypes.keys()):
        candidates = sorted(raw_doctypes[dt_name], key=lambda item: (item[0], item[1]))
        _best_prio, best_app, primary_doc = candidates[0]
        is_child = bool(primary_doc.get("istable"))
        is_single = bool(primary_doc.get("issingle"))
        is_virtual = bool(primary_doc.get("is_virtual"))
        is_tree = bool(primary_doc.get("is_tree"))
        is_submittable = bool(primary_doc.get("is_submittable"))
        module_name = str(primary_doc.get("module") or best_app).strip()

        kind = (
            "child"
            if is_child
            else "single"
            if is_single
            else "virtual"
            if is_virtual
            else "doctype"
        )
        tname = make_unique_identifier(
            dt_name, used_table_names, reserved, fallback_suffix="_TBL"
        )
        doctype_to_table[dt_name] = tname

        cols = build_standard_frappe_system_columns(
            is_child=is_child, is_tree=is_tree
        )
        used_cols = {c.col_name for c in cols}
        seen_orig_fields = {c.orig_fieldname.lower() for c in cols}

        merged_field_dicts: list[dict] = []
        for _prio, _app, doc in candidates:
            for f in doc.get("fields", []):
                if isinstance(f, dict):
                    merged_field_dicts.append(f)
        merged_field_dicts.extend(custom_fields_by_dt.get(dt_name, []))

        for f in merged_field_dicts:
            ft = str(f.get("fieldtype") or "Data").strip()
            if ft in LAYOUT_ONLY_FIELDTYPES:
                continue
            fn = str(f.get("fieldname") or "").strip()
            if not fn or fn.lower() in seen_orig_fields:
                continue
            seen_orig_fields.add(fn.lower())
            opts = str(f.get("options") or "")
            fb_type, link_target = map_field_to_firebird(fn, ft, opts)
            cname = make_unique_identifier(
                fn, used_cols, reserved, fallback_suffix="_VAL"
            )
            cols.append(
                ColumnSpec(
                    col_name=cname,
                    fb_type=fb_type,
                    orig_fieldname=fn,
                    label=str(f.get("label") or fn)[:120],
                    fieldtype=ft,
                    options=opts,
                    link_target_doctype=link_target,
                )
            )

        spec = TableSpec(
            table_name=tname,
            source_app=best_app,
            orig_name=dt_name,
            module=module_name,
            kind=kind,
            is_tree=is_tree,
            is_submittable=is_submittable,
            columns=cols,
            parent_doctypes=set(child_parent_map.get(dt_name, set())),
            comment=(
                f"Frappe {kind} DocType '{dt_name}' (app: {best_app}, module: {module_name})"
            ),
        )
        enforce_row_byte_budget(spec)
        tables_by_name[tname] = spec

    # 2. Compile Frappe Books standalone JSON schemas (FBK_*)
    books_raw: dict[str, dict] = {}
    for sub in ("core", "meta", "app"):
        sub_dir = donor_root / "books" / "schemas" / sub
        if sub_dir.is_dir():
            for jpath in sorted(sub_dir.glob("*.json")):
                try:
                    bdoc = json.loads(jpath.read_text(encoding="utf-8"))
                    if isinstance(bdoc, dict) and bdoc.get("name"):
                        books_raw[str(bdoc["name"])] = bdoc
                except Exception:
                    pass

    def resolved_books_fields(schema_name: str, visited: set[str] | None = None) -> list[dict]:
        visited = visited or set()
        if schema_name in visited or schema_name not in books_raw:
            return []
        visited.add(schema_name)
        bdoc = books_raw[schema_name]
        parent_name = bdoc.get("extends")
        base_fields = resolved_books_fields(str(parent_name), visited) if parent_name else []
        own_fields = [f for f in bdoc.get("fields", []) if isinstance(f, dict) and not f.get("abstract")]
        by_fn: dict[str, dict] = {}
        for item in base_fields + own_fields:
            fn = str(item.get("fieldname") or "").strip()
            if fn:
                by_fn[fn] = item
        return list(by_fn.values())

    books_to_table: dict[str, str] = {}
    books_child_parents: dict[str, set[str]] = defaultdict(set)
    for bname, bdoc in sorted(books_raw.items()):
        if bdoc.get("isAbstract"):
            continue
        for f in resolved_books_fields(bname):
            if f.get("fieldtype") == "Table" and f.get("target"):
                books_child_parents[str(f["target"])].add(bname)

    def resolved_books_flag(schema_name: str, flag: str, visited: set[str] | None = None) -> bool:
        visited = visited or set()
        if schema_name in visited or schema_name not in books_raw:
            return False
        visited.add(schema_name)
        bdoc = books_raw[schema_name]
        if flag in bdoc:
            return bool(bdoc[flag])
        parent_name = bdoc.get("extends")
        return resolved_books_flag(str(parent_name), flag, visited) if parent_name else False

    for bname, bdoc in sorted(books_raw.items()):
        if bdoc.get("isAbstract"):
            continue
        tname = make_unique_identifier(
            bname, used_table_names, reserved, prefix="FBK", fallback_suffix="_TBL"
        )
        books_to_table[bname] = tname
        is_child = resolved_books_flag(bname, "isChild")
        is_tree = resolved_books_flag(bname, "isTree")
        cols = build_standard_frappe_system_columns(
            is_child=is_child, is_tree=is_tree
        )
        used_cols = {c.col_name for c in cols}
        seen_fn = {c.orig_fieldname.lower() for c in cols}

        for f in resolved_books_fields(bname):
            ft = str(f.get("fieldtype") or "Data").strip()
            if ft in LAYOUT_ONLY_FIELDTYPES:
                continue
            fn = str(f.get("fieldname") or "").strip()
            if not fn or fn.lower() in seen_fn:
                continue
            seen_fn.add(fn.lower())
            opts_raw = f.get("target") or ""
            if not opts_raw and isinstance(f.get("options"), list):
                opts_raw = "\n".join(
                    str(o.get("value") or "") for o in f["options"] if isinstance(o, dict)
                )
            elif not opts_raw and isinstance(f.get("options"), str):
                opts_raw = f["options"]
            fb_type, link_target = map_field_to_firebird(fn, ft, str(opts_raw))
            if link_target:
                link_target = f"__BOOKS__:{link_target}"
            cname = make_unique_identifier(
                fn, used_cols, reserved, fallback_suffix="_VAL"
            )
            cols.append(
                ColumnSpec(
                    col_name=cname,
                    fb_type=fb_type,
                    orig_fieldname=fn,
                    label=str(f.get("label") or fn)[:120],
                    fieldtype=ft,
                    options=str(opts_raw),
                    link_target_doctype=link_target,
                )
            )

        bspec = TableSpec(
            table_name=tname,
            source_app="books",
            orig_name=f"Books:{bname}",
            module="Frappe Books",
            kind="books",
            is_tree=is_tree,
            is_submittable=bool(bdoc.get("isSubmittable")),
            columns=cols,
            parent_doctypes={f"__BOOKS__:{p}" for p in books_child_parents.get(bname, set())},
            comment=f"Frappe Books standalone schema '{bname}'",
        )
        enforce_row_byte_budget(bspec)
        tables_by_name[tname] = bspec

    # 3. Add explicit companion & runtime system tables
    companion_specs = _build_companion_table_specs()
    for cspec in companion_specs:
        tables_by_name[cspec.table_name] = cspec

    # Update project_catalog table_count
    app_table_counts: dict[str, int] = defaultdict(int)
    for spec in tables_by_name.values():
        app_table_counts[spec.source_app] += 1
    for entry in project_catalog:
        entry["table_count"] = app_table_counts.get(entry["repo_name"], 0)

    # 4. Compile FOREIGN KEY constraints across all tables
    fks: list[ForeignKeySpec] = []
    used_fk_names: set[str] = set()

    def resolve_target(ref: str) -> str | None:
        if ref.startswith("__BOOKS__:"):
            return books_to_table.get(ref.split(":", 1)[1])
        if ref in tables_by_name:
            return ref
        return doctype_to_table.get(ref)

    # Priority business targets get FK precedence when a table has >MAX_FKS_PER_TABLE Link fields.
    priority_targets = {
        "Company", "Customer", "Supplier", "Item", "Account", "Warehouse",
        "Cost Center", "Currency", "UOM", "Item Group", "Customer Group",
        "Supplier Group", "Territory", "Employee", "Department", "Designation",
        "Project", "Sales Order", "Sales Invoice", "Delivery Note", "Quotation",
        "Purchase Order", "Purchase Invoice", "Purchase Receipt", "Payment Entry",
        "Journal Entry", "BOM", "Work Order", "User", "Role", "DocType", "Module Def",
        "CRM Lead", "CRM Deal", "HD Ticket", "Loan", "Loan Product", "Course",
        "LMS Course", "Student", "Site", "Bench", "Release Group",
    }

    for tname, spec in sorted(tables_by_name.items()):
        spec_col_names = {c.col_name for c in spec.columns}
        # Single-parent child table FK on PARENT_ID
        if len(spec.parent_doctypes) == 1 and "PARENT_ID" in spec_col_names:
            only_parent_ref = next(iter(spec.parent_doctypes))
            parent_table = resolve_target(only_parent_ref)
            if parent_table and parent_table != tname:
                cname = make_unique_identifier(
                    f"FK_{tname}_PARENT", used_fk_names, reserved, fallback_suffix="_FK"
                )
                fks.append(
                    ForeignKeySpec(
                        constraint_name=cname,
                        source_table=tname,
                        source_col="PARENT_ID",
                        target_table=parent_table,
                        target_col="DOC_NAME",
                        on_delete="ON DELETE CASCADE",
                        on_update="ON UPDATE CASCADE",
                    )
                )

        # Link column FKs
        link_cols = [c for c in spec.columns if c.link_target_doctype]
        link_cols.sort(
            key=lambda c: (
                0 if c.link_target_doctype in priority_targets else 1,
                c.col_name,
            )
        )
        added_for_table = 0
        for col in link_cols:
            if added_for_table >= MAX_FKS_PER_TABLE:
                break
            target_table = resolve_target(col.link_target_doctype or "")
            if not target_table or target_table not in tables_by_name:
                continue
            target_spec = tables_by_name[target_table]
            if target_spec.pk_columns != ["DOC_NAME"]:
                continue
            cname = make_unique_identifier(
                f"FK_{tname}_{col.col_name}",
                used_fk_names,
                reserved,
                fallback_suffix="_FK",
            )
            fks.append(
                ForeignKeySpec(
                    constraint_name=cname,
                    source_table=tname,
                    source_col=col.col_name,
                    target_table=target_table,
                    target_col="DOC_NAME",
                    on_delete="",
                    on_update="ON UPDATE CASCADE",
                )
            )
            added_for_table += 1

    # Explicit companion FKs (Mobile Accounting, Stalwart, Boat)
    for cname, src_t, src_c, dst_t, dst_c, on_del in (
        ("FK_MOBACC_ACC_PARENT", "MOBACC_ACCOUNT", "PARENT_ACCOUNT", "MOBACC_ACCOUNT", "DOC_NAME", ""),
        ("FK_MOBACC_ITEM_INC", "MOBACC_ITEM", "INCOME_ACCOUNT", "MOBACC_ACCOUNT", "DOC_NAME", ""),
        ("FK_MOBACC_ITEM_EXP", "MOBACC_ITEM", "EXPENSE_ACCOUNT", "MOBACC_ACCOUNT", "DOC_NAME", ""),
        ("FK_MOBACC_ITEM_TAX", "MOBACC_ITEM", "TAX_REF", "MOBACC_TAX", "DOC_NAME", ""),
        ("FK_STALWART_GRP_ACC", "STALWART_GROUP_MEMBERS", "ACCOUNT_NAME", "STALWART_ACCOUNTS", "ACCOUNT_NAME", "ON DELETE CASCADE"),
        ("FK_STALWART_EML_ACC", "STALWART_EMAILS", "ACCOUNT_NAME", "STALWART_ACCOUNTS", "ACCOUNT_NAME", "ON DELETE CASCADE"),
        ("FK_BOAT_VOL_VM", "BOAT_VOLUME", "VM_ID", "BOAT_VIRTUAL_MACHINE", "VM_ID", "ON DELETE CASCADE"),
    ):
        used_fk_names.add(cname)
        fks.append(
            ForeignKeySpec(
                constraint_name=cname,
                source_table=src_t,
                source_col=src_c,
                target_table=dst_t,
                target_col=dst_c,
                on_delete=on_del,
                on_update="ON UPDATE CASCADE",
            )
        )

    return project_catalog, tables_by_name, doctype_to_table, fks


def _build_companion_table_specs() -> list[TableSpec]:
    """Explicit Firebird 5.0 adapted schemas for runtime & non-DocType donor projects."""
    return [
        TableSpec(
            table_name="SUITE_PROJECT_CATALOG",
            source_app="frappe",
            orig_name="Suite Project Catalog",
            module="Suite Metadata",
            kind="system",
            pk_columns=["REPO_NAME"],
            columns=[
                ColumnSpec("REPO_NAME", "D_DOC_ID", "repo_name", is_pk=True, not_null=True),
                ColumnSpec("CATEGORY", "D_SHORT_TEXT", "category", not_null=True),
                ColumnSpec("DOCTYPE_COUNT", "INTEGER DEFAULT 0", "doctype_count"),
                ColumnSpec("TABLE_COUNT", "INTEGER DEFAULT 0", "table_count"),
                ColumnSpec("STATUS", "D_STATUS", "status"),
            ],
            comment="Master inventory of all 235 repositories in donor_release_acquisition/frappe",
        ),
        TableSpec(
            table_name="FRAPPE_AUTH",
            source_app="frappe",
            orig_name="__Auth",
            module="Core",
            kind="system",
            pk_columns=["DOCTYPE_NAME", "DOC_NAME", "FIELD_NAME"],
            columns=[
                ColumnSpec("DOCTYPE_NAME", "D_DOC_ID", "doctype", is_pk=True, not_null=True),
                ColumnSpec("DOC_NAME", "D_DOC_ID", "name", is_pk=True, not_null=True),
                ColumnSpec("FIELD_NAME", "D_CODE", "fieldname", is_pk=True, not_null=True),
                ColumnSpec("PASSWD_HASH", "VARCHAR(255)", "password", not_null=True),
                ColumnSpec("ENCRYPTED_FLAG", "D_BOOL", "encrypted"),
            ],
            comment="Frappe __Auth encrypted credential store adapted to Firebird 5.0",
        ),
        TableSpec(
            table_name="FRAPPE_USER_SETTINGS",
            source_app="frappe",
            orig_name="__UserSettings",
            module="Core",
            kind="system",
            pk_columns=["USER_ID", "DOCTYPE_NAME"],
            columns=[
                ColumnSpec("USER_ID", "D_DOC_ID", "user", is_pk=True, not_null=True),
                ColumnSpec("DOCTYPE_NAME", "D_DOC_ID", "doctype", is_pk=True, not_null=True),
                ColumnSpec("SETTINGS_JSON", "D_JSON", "data"),
            ],
            comment="Frappe __UserSettings per-user view/filter preferences",
        ),
        TableSpec(
            table_name="FRAPPE_GLOBAL_SEARCH",
            source_app="frappe",
            orig_name="__global_search",
            module="Core",
            kind="system",
            pk_columns=["DOCTYPE_NAME", "DOC_NAME"],
            columns=[
                ColumnSpec("DOCTYPE_NAME", "D_DOC_ID", "doctype", is_pk=True, not_null=True),
                ColumnSpec("DOC_NAME", "D_DOC_ID", "name", is_pk=True, not_null=True),
                ColumnSpec("TITLE", "D_TITLE", "title"),
                ColumnSpec("CONTENT_TEXT", "D_TEXT", "content"),
                ColumnSpec("ROUTE_PATH", "D_URL", "route"),
                ColumnSpec("PUBLISHED_FLAG", "D_BOOL", "published"),
            ],
            comment="Frappe __global_search full-text search index table",
        ),
        TableSpec(
            table_name="FRAPPE_SINGLES_KV",
            source_app="frappe",
            orig_name="tabSingles",
            module="Core",
            kind="system",
            pk_columns=["DOCTYPE_NAME", "FIELD_NAME"],
            columns=[
                ColumnSpec("DOCTYPE_NAME", "D_DOC_ID", "doctype", is_pk=True, not_null=True),
                ColumnSpec("FIELD_NAME", "D_DOC_ID", "field", is_pk=True, not_null=True),
                ColumnSpec("FIELD_VALUE", "D_TEXT", "value"),
            ],
            comment="Frappe tabSingles key-value settings table",
        ),
        TableSpec(
            table_name="FRAPPE_SERIES",
            source_app="frappe",
            orig_name="tabSeries",
            module="Core",
            kind="system",
            pk_columns=["SERIES_NAME"],
            columns=[
                ColumnSpec("SERIES_NAME", "D_DOC_ID", "name", is_pk=True, not_null=True),
                ColumnSpec("CURRENT_VAL", "BIGINT DEFAULT 0", "current", not_null=True),
            ],
            comment="Frappe tabSeries naming counter table",
        ),
        # Datum + Cargo observability tables (ClickHouse MergeTree/SummingMergeTree -> Firebird 5.0)
        TableSpec(
            table_name="DATUM_SAMPLES",
            source_app="datum",
            orig_name="datum.samples",
            module="Observability",
            kind="companion",
            pk_columns=["SAMPLE_ID"],
            columns=[
                ColumnSpec("SAMPLE_ID", "BIGINT NOT NULL", "sample_id", is_pk=True, not_null=True),
                ColumnSpec("TS", "TIMESTAMP WITH TIME ZONE", "ts", not_null=True),
                ColumnSpec("METRIC", "D_SHORT_TEXT", "metric", not_null=True),
                ColumnSpec("RESOURCE_ID", "D_SHORT_TEXT", "resource_id", not_null=True),
                ColumnSpec("SERVICE_NAME", "D_CODE", "service"),
                ColumnSpec("SERIES_KIND", "D_CODE", "kind"),
                ColumnSpec("LABELS_JSON", "D_JSON", "labels"),
                ColumnSpec("SAMPLE_VALUE", "DOUBLE PRECISION DEFAULT 0", "value", not_null=True),
            ],
            comment="Datum metric samples adapted from ClickHouse MergeTree (supports Cargo SQL views)",
        ),
        TableSpec(
            table_name="DATUM_DAILY_INGESTION_STATS",
            source_app="datum",
            orig_name="datum.daily_ingestion_stats",
            module="Observability",
            kind="companion",
            pk_columns=["STAT_DATE", "RESOURCE_ID"],
            columns=[
                ColumnSpec("STAT_DATE", "DATE", "date", is_pk=True, not_null=True),
                ColumnSpec("RESOURCE_ID", "D_SHORT_TEXT", "resource_id", is_pk=True, not_null=True),
                ColumnSpec("METRIC_COUNT", "BIGINT DEFAULT 0", "metric_count", not_null=True),
            ],
            comment="Datum SummingMergeTree rollup maintained live via Firebird trigger TRG_AI_DATUM_SAMPLES",
        ),
        TableSpec(
            table_name="DATUM_LOGS",
            source_app="datum",
            orig_name="datum.logs",
            module="Observability",
            kind="companion",
            pk_columns=["LOG_ID"],
            columns=[
                ColumnSpec("LOG_ID", "BIGINT NOT NULL", "log_id", is_pk=True, not_null=True),
                ColumnSpec("TS", "TIMESTAMP WITH TIME ZONE", "ts", not_null=True),
                ColumnSpec("RESOURCE_ID", "D_SHORT_TEXT", "resource_id", not_null=True),
                ColumnSpec("PRODUCT", "D_CODE", "product", not_null=True),
                ColumnSpec("SERVICE_NAME", "D_CODE", "service", not_null=True),
                ColumnSpec("LOG_LEVEL", "D_CODE", "level", not_null=True),
                ColumnSpec("LOG_SOURCE", "D_SHORT_TEXT", "source", not_null=True),
                ColumnSpec("HTTP_STATUS", "INTEGER DEFAULT 200", "http_status"),
                ColumnSpec("MESSAGE_TEXT", "D_TEXT", "message"),
                ColumnSpec("ATTRIBUTES_JSON", "D_JSON", "attributes"),
            ],
            comment="Datum structured log lines adapted from ClickHouse MergeTree",
        ),
        TableSpec(
            table_name="DATUM_DAILY_LOG_STATS",
            source_app="datum",
            orig_name="datum.daily_log_stats",
            module="Observability",
            kind="companion",
            pk_columns=["STAT_DATE", "RESOURCE_ID", "PRODUCT", "SERVICE_NAME", "LOG_LEVEL"],
            columns=[
                ColumnSpec("STAT_DATE", "DATE", "date", is_pk=True, not_null=True),
                ColumnSpec("RESOURCE_ID", "D_SHORT_TEXT", "resource_id", is_pk=True, not_null=True),
                ColumnSpec("PRODUCT", "D_CODE", "product", is_pk=True, not_null=True),
                ColumnSpec("SERVICE_NAME", "D_CODE", "service", is_pk=True, not_null=True),
                ColumnSpec("LOG_LEVEL", "D_CODE", "level", is_pk=True, not_null=True),
                ColumnSpec("LOG_COUNT", "BIGINT DEFAULT 0", "log_count", not_null=True),
            ],
            comment="Datum daily log rollup maintained live via Firebird trigger TRG_AI_DATUM_LOGS",
        ),
        TableSpec(
            table_name="DATUM_TRACES",
            source_app="datum",
            orig_name="datum.traces",
            module="Observability",
            kind="companion",
            pk_columns=["TRACE_ID", "SPAN_ID"],
            columns=[
                ColumnSpec("TRACE_ID", "D_CODE", "trace_id", is_pk=True, not_null=True),
                ColumnSpec("SPAN_ID", "D_CODE", "span_id", is_pk=True, not_null=True),
                ColumnSpec("PARENT_SPAN_ID", "D_CODE", "parent_span_id"),
                ColumnSpec("TS", "TIMESTAMP WITH TIME ZONE", "ts", not_null=True),
                ColumnSpec("RESOURCE_ID", "D_SHORT_TEXT", "resource_id", not_null=True),
                ColumnSpec("SERVICE_NAME", "D_CODE", "service", not_null=True),
                ColumnSpec("SPAN_NAME", "D_SHORT_TEXT", "span_name", not_null=True),
                ColumnSpec("SPAN_KIND", "D_CODE", "span_kind"),
                ColumnSpec("DURATION_NS", "BIGINT DEFAULT 0", "duration_ns"),
                ColumnSpec("STATUS_CODE", "D_CODE", "status_code"),
                ColumnSpec("STATUS_MESSAGE", "D_SHORT_TEXT", "status_message"),
                ColumnSpec("ATTRIBUTES_JSON", "D_JSON", "attributes"),
            ],
            comment="Datum OpenTelemetry trace spans adapted from ClickHouse MergeTree",
        ),
        # Stalwart Mail / Directory / KV Store tables
        TableSpec(
            table_name="STALWART_ACCOUNTS",
            source_app="stalwart",
            orig_name="stalwart.accounts",
            module="Mail Server",
            kind="companion",
            pk_columns=["ACCOUNT_NAME"],
            columns=[
                ColumnSpec("ACCOUNT_NAME", "D_EMAIL", "name", is_pk=True, not_null=True),
                ColumnSpec("SECRET_HASH", "VARCHAR(255)", "secret"),
                ColumnSpec("DESCRIPTION", "D_SHORT_TEXT", "description"),
                ColumnSpec("ACCOUNT_TYPE", "D_CODE", "type", not_null=True),
                ColumnSpec("QUOTA_BYTES", "BIGINT DEFAULT 0", "quota"),
                ColumnSpec("ACTIVE_FLAG", "D_BOOL", "active"),
            ],
            comment="Stalwart SQL directory accounts table",
        ),
        TableSpec(
            table_name="STALWART_GROUP_MEMBERS",
            source_app="stalwart",
            orig_name="stalwart.group_members",
            module="Mail Server",
            kind="companion",
            pk_columns=["ACCOUNT_NAME", "MEMBER_OF"],
            columns=[
                ColumnSpec("ACCOUNT_NAME", "D_EMAIL", "name", is_pk=True, not_null=True),
                ColumnSpec("MEMBER_OF", "D_EMAIL", "member_of", is_pk=True, not_null=True),
            ],
            comment="Stalwart SQL directory group membership table",
        ),
        TableSpec(
            table_name="STALWART_EMAILS",
            source_app="stalwart",
            orig_name="stalwart.emails",
            module="Mail Server",
            kind="companion",
            pk_columns=["ACCOUNT_NAME", "EMAIL_ADDRESS"],
            columns=[
                ColumnSpec("ACCOUNT_NAME", "D_EMAIL", "name", is_pk=True, not_null=True),
                ColumnSpec("EMAIL_ADDRESS", "D_EMAIL", "address", is_pk=True, not_null=True),
                ColumnSpec("EMAIL_ROLE", "D_CODE", "role"),
            ],
            comment="Stalwart SQL directory email aliases table",
        ),
        TableSpec(
            table_name="STALWART_STORE_DATA",
            source_app="stalwart",
            orig_name="stalwart.store_d",
            module="Mail Server",
            kind="companion",
            pk_columns=["STORE_KEY"],
            columns=[
                ColumnSpec("STORE_KEY", "VARBINARY(255)", "k", is_pk=True, not_null=True),
                ColumnSpec("STORE_VAL", "BLOB SUB_TYPE BINARY", "v", not_null=True),
            ],
            comment="Stalwart SQL key-value payload table adapted to Firebird VARBINARY + BLOB",
        ),
        TableSpec(
            table_name="STALWART_STORE_INDEX",
            source_app="stalwart",
            orig_name="stalwart.store_i",
            module="Mail Server",
            kind="companion",
            pk_columns=["INDEX_KEY"],
            columns=[
                ColumnSpec("INDEX_KEY", "VARBINARY(255)", "k", is_pk=True, not_null=True),
            ],
            comment="Stalwart SQL key-index table",
        ),
        TableSpec(
            table_name="STALWART_STORE_COUNTER",
            source_app="stalwart",
            orig_name="stalwart.store_c",
            module="Mail Server",
            kind="companion",
            pk_columns=["COUNTER_KEY"],
            columns=[
                ColumnSpec("COUNTER_KEY", "VARBINARY(255)", "k", is_pk=True, not_null=True),
                ColumnSpec("COUNTER_VAL", "BIGINT DEFAULT 0", "v", not_null=True),
            ],
            comment="Stalwart SQL atomic counter table",
        ),
        TableSpec(
            table_name="STALWART_STORE_BLOB",
            source_app="stalwart",
            orig_name="stalwart.store_b",
            module="Mail Server",
            kind="companion",
            pk_columns=["BLOB_HASH"],
            columns=[
                ColumnSpec("BLOB_HASH", "D_DOC_ID", "hash", is_pk=True, not_null=True),
                ColumnSpec("BYTE_SIZE", "BIGINT DEFAULT 0", "size", not_null=True),
                ColumnSpec("PAYLOAD", "BLOB SUB_TYPE BINARY", "payload", not_null=True),
            ],
            comment="Stalwart content-addressed MIME/JMAP blob table",
        ),
        # Boat Firecracker VM persistence models (boat/internal/model/*.go)
        TableSpec(
            table_name="BOAT_VIRTUAL_MACHINE",
            source_app="boat",
            orig_name="boat.VirtualMachine",
            module="Hypervisor",
            kind="companion",
            pk_columns=["VM_ID"],
            columns=[
                ColumnSpec("VM_ID", "D_DOC_ID", "vm_id", is_pk=True, not_null=True),
                ColumnSpec("HOSTNAME", "D_SHORT_TEXT", "hostname", not_null=True),
                ColumnSpec("DESIRED_POWER", "D_STATUS", "desired_power", not_null=True),
                ColumnSpec("OBSERVED_STATUS", "D_STATUS", "status", not_null=True),
                ColumnSpec("VCPU_COUNT", "INTEGER DEFAULT 2", "vcpu_count"),
                ColumnSpec("MEM_MIB", "INTEGER DEFAULT 2048", "mem_mib"),
                ColumnSpec("IPV4_CIDR", "D_CODE", "ipv4_cidr"),
                ColumnSpec("WAKE_ON_SYN", "D_BOOL", "wake_on_syn"),
                ColumnSpec("UPDATED_AT", "TIMESTAMP WITH TIME ZONE", "updated_at"),
            ],
            comment="Boat Firecracker VM state model adapted from boat/internal/model",
        ),
        TableSpec(
            table_name="BOAT_DECISION_JOURNAL",
            source_app="boat",
            orig_name="boat.Decision",
            module="Hypervisor",
            kind="companion",
            pk_columns=["OPERATION_ID", "STEP_NAME"],
            columns=[
                ColumnSpec("OPERATION_ID", "D_DOC_ID", "operation_id", is_pk=True, not_null=True),
                ColumnSpec("STEP_NAME", "D_CODE", "step", is_pk=True, not_null=True),
                ColumnSpec("VM_ID", "D_DOC_ID", "vm_id"),
                ColumnSpec("VALUES_JSON", "D_JSON", "values"),
                ColumnSpec("DECIDED_AT", "TIMESTAMP WITH TIME ZONE", "at", not_null=True),
            ],
            comment="Boat write-ahead idempotency decision journal (boat/internal/model/decision.go)",
        ),
        TableSpec(
            table_name="BOAT_VOLUME",
            source_app="boat",
            orig_name="boat.Volume",
            module="Hypervisor",
            kind="companion",
            pk_columns=["VOLUME_ID"],
            columns=[
                ColumnSpec("VOLUME_ID", "D_DOC_ID", "volume_id", is_pk=True, not_null=True),
                ColumnSpec("VM_ID", "D_DOC_ID", "vm_id", not_null=True),
                ColumnSpec("DEVICE_PATH", "D_URL", "device_path"),
                ColumnSpec("SIZE_GIB", "INTEGER DEFAULT 20", "size_gib"),
                ColumnSpec("ROOT_FS_FLAG", "D_BOOL", "root_fs"),
            ],
            comment="Boat block volume attachment model",
        ),
        # Mobile Accounting (mobile-accounting/src/assets/tables.sql)
        TableSpec(
            table_name="MOBACC_ACCOUNT",
            source_app="mobile-accounting",
            orig_name="mobile_accounting.Account",
            module="Mobile Accounting",
            kind="companion",
            is_tree=True,
            pk_columns=["DOC_NAME"],
            columns=[
                ColumnSpec("DOC_NAME", "D_DOC_ID", "name", is_pk=True, not_null=True),
                ColumnSpec("OWNER_USER", "D_DOC_ID", "owner", not_null=True),
                ColumnSpec("MODIFIED_BY", "D_DOC_ID", "modifiedBy", not_null=True),
                ColumnSpec("CREATION_TS", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "creation"),
                ColumnSpec("MODIFIED_TS", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "modified"),
                ColumnSpec("KEYWORDS", "D_SHORT_TEXT", "keywords"),
                ColumnSpec("LFT_NODE", "INTEGER DEFAULT 0", "lft"),
                ColumnSpec("RGT_NODE", "INTEGER DEFAULT 0", "rgt"),
                ColumnSpec("PARENT_ACCOUNT", "D_DOC_ID", "parentAccount"),
                ColumnSpec("ROOT_TYPE", "D_CODE", "rootType"),
                ColumnSpec("ACCOUNT_TYPE", "D_STATUS", "accountType"),
                ColumnSpec("IS_GROUP", "D_BOOL", "isGroup"),
            ],
            comment="Mobile Accounting SQLite Account table adapted to Firebird",
        ),
        TableSpec(
            table_name="MOBACC_PARTY",
            source_app="mobile-accounting",
            orig_name="mobile_accounting.Party",
            module="Mobile Accounting",
            kind="companion",
            pk_columns=["DOC_NAME"],
            columns=[
                ColumnSpec("DOC_NAME", "D_DOC_ID", "name", is_pk=True, not_null=True),
                ColumnSpec("OWNER_USER", "D_DOC_ID", "owner", not_null=True),
                ColumnSpec("MODIFIED_BY", "D_DOC_ID", "modifiedBy", not_null=True),
                ColumnSpec("CREATION_TS", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "creation"),
                ColumnSpec("MODIFIED_TS", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "modified"),
                ColumnSpec("KEYWORDS", "D_SHORT_TEXT", "keywords"),
                ColumnSpec("IS_CUSTOMER", "D_BOOL", "customer"),
                ColumnSpec("IS_SUPPLIER", "D_BOOL", "supplier"),
            ],
            comment="Mobile Accounting Party table",
        ),
        TableSpec(
            table_name="MOBACC_TAX",
            source_app="mobile-accounting",
            orig_name="mobile_accounting.Tax",
            module="Mobile Accounting",
            kind="companion",
            pk_columns=["DOC_NAME"],
            columns=[
                ColumnSpec("DOC_NAME", "D_DOC_ID", "name", is_pk=True, not_null=True),
                ColumnSpec("TAX_RATE", "D_PERCENT", "rate"),
                ColumnSpec("ENABLED_FLAG", "D_BOOL", "enabled"),
            ],
            comment="Mobile Accounting Tax table",
        ),
        TableSpec(
            table_name="MOBACC_ITEM",
            source_app="mobile-accounting",
            orig_name="mobile_accounting.Item",
            module="Mobile Accounting",
            kind="companion",
            pk_columns=["DOC_NAME"],
            columns=[
                ColumnSpec("DOC_NAME", "D_DOC_ID", "name", is_pk=True, not_null=True),
                ColumnSpec("OWNER_USER", "D_DOC_ID", "owner", not_null=True),
                ColumnSpec("MODIFIED_BY", "D_DOC_ID", "modifiedBy", not_null=True),
                ColumnSpec("DESCRIPTION", "D_TEXT", "description"),
                ColumnSpec("UNIT_CODE", "D_CODE", "unit"),
                ColumnSpec("INCOME_ACCOUNT", "D_DOC_ID", "incomeAccount"),
                ColumnSpec("EXPENSE_ACCOUNT", "D_DOC_ID", "expenseAccount"),
                ColumnSpec("TAX_REF", "D_DOC_ID", "tax"),
                ColumnSpec("UNIT_RATE", "D_MONEY", "rate"),
            ],
            comment="Mobile Accounting Item table with Account & Tax foreign keys",
        ),
        # PyWall (pywall/pywall_schema.sql)
        TableSpec(
            table_name="PYWALL_WALL",
            source_app="pywall",
            orig_name="pywall.wall",
            module="Community Wall",
            kind="companion",
            pk_columns=["POST_ID"],
            columns=[
                ColumnSpec("POST_ID", "BIGINT NOT NULL", "post_id", is_pk=True, not_null=True),
                ColumnSpec("MESSAGE_TEXT", "VARCHAR(255)", "message", not_null=True),
                ColumnSpec("POSTED_BY", "D_SHORT_TEXT", "posted_by", not_null=True),
                ColumnSpec("POSTED_ON", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "posted_on"),
            ],
            comment="PyWall message board table adapted from pywall_schema.sql",
        ),
    ]


def sql_lit(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, bytes):
        return "X'" + val.hex().upper() + "'"
    s = str(val).replace("'", "''")
    return f"'{s}'"


def build_curated_and_universal_rows(
    project_catalog: list[dict],
    tables_by_name: dict[str, TableSpec],
    doctype_to_table: dict[str, str],
    fks: list[ForeignKeySpec],
) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[str]]]:
    """Generate rich domain workflows + universal FK-consistent seed rows for every table."""
    rows_by_table: dict[str, list[dict[str, object]]] = defaultdict(list)
    pk_pool: dict[str, list[str]] = {}

    # Pre-build FK lookup: (source_table, source_col) -> target_table
    fk_map: dict[tuple[str, str], str] = {
        (fk.source_table, fk.source_col): fk.target_table for fk in fks
    }

    def dt_table(dt_name: str) -> str | None:
        return doctype_to_table.get(dt_name)

    def add_doc_rows(
        dt_or_table: str, records: list[dict[str, object]], *, by_doctype: bool = True
    ) -> None:
        tname = dt_table(dt_or_table) if by_doctype else dt_or_table
        if not tname or tname not in tables_by_name:
            return
        spec = tables_by_name[tname]
        col_by_orig = {c.orig_fieldname.lower(): c.col_name for c in spec.columns}
        col_set = {c.col_name for c in spec.columns}
        out_rows = rows_by_table[tname]
        pks = pk_pool.setdefault(tname, [])

        for idx, rec in enumerate(records, start=1):
            mapped: dict[str, object] = {}
            for k, v in rec.items():
                if k in col_set:
                    mapped[k] = v
                elif k.lower() in col_by_orig:
                    mapped[col_by_orig[k.lower()]] = v
            if "DOC_NAME" in col_set:
                doc_id = str(mapped.get("DOC_NAME") or f"{tname[:24]}-{idx:04d}")
                mapped["DOC_NAME"] = doc_id
                mapped.setdefault("OWNER_USER", "Administrator")
                mapped.setdefault("MODIFIED_BY", "Administrator")
                mapped.setdefault("CREATION_TS", "2026-01-15 09:00:00")
                mapped.setdefault("MODIFIED_TS", "2026-10-15 14:30:00")
                mapped.setdefault("DOCSTATUS", 1 if spec.is_submittable else 0)
                mapped.setdefault("IDX_NO", idx)
                if doc_id not in pks:
                    pks.append(doc_id)
            elif len(spec.pk_columns) == 1:
                pk_col = spec.pk_columns[0]
                pk_val = str(mapped[pk_col])
                if pk_val not in pks:
                    pks.append(pk_val)
            out_rows.append(mapped)

    # 1. Master Suite Project Catalog (all 235 donor directories)
    add_doc_rows(
        "SUITE_PROJECT_CATALOG",
        [
            {
                "REPO_NAME": item["repo_name"],
                "CATEGORY": item["category"],
                "DOCTYPE_COUNT": item["doctype_count"],
                "TABLE_COUNT": item["table_count"],
                "STATUS": "Active" if item["table_count"] > 0 else "Cataloged",
            }
            for item in project_catalog
        ],
        by_doctype=False,
    )

    # 2. Core Frappe Foundation DocTypes
    add_doc_rows("Currency", [
        {"name": "CAD", "currency_name": "Canadian Dollar", "symbol": "$", "fraction": "Cent", "fraction_units": 100, "enabled": True},
        {"name": "USD", "currency_name": "United States Dollar", "symbol": "$", "fraction": "Cent", "fraction_units": 100, "enabled": True},
        {"name": "EUR", "currency_name": "Euro", "symbol": "EUR", "fraction": "Cent", "fraction_units": 100, "enabled": True},
        {"name": "GBP", "currency_name": "Pound Sterling", "symbol": "GBP", "fraction": "Penny", "fraction_units": 100, "enabled": True},
        {"name": "INR", "currency_name": "Indian Rupee", "symbol": "INR", "fraction": "Paisa", "fraction_units": 100, "enabled": True},
    ])
    add_doc_rows("Country", [
        {"name": "Canada", "code": "ca", "date_format": "yyyy-mm-dd", "time_zones": "America/Toronto"},
        {"name": "United States", "code": "us", "date_format": "mm-dd-yyyy", "time_zones": "America/New_York"},
        {"name": "United Kingdom", "code": "gb", "date_format": "dd-mm-yyyy", "time_zones": "Europe/London"},
        {"name": "Germany", "code": "de", "date_format": "dd.mm.yyyy", "time_zones": "Europe/Berlin"},
        {"name": "India", "code": "in", "date_format": "dd-mm-yyyy", "time_zones": "Asia/Kolkata"},
    ])
    add_doc_rows("Language", [
        {"name": "en", "language_code": "en", "language_name": "English", "enabled": True},
        {"name": "fr", "language_code": "fr", "language_name": "French", "enabled": True},
        {"name": "de", "language_code": "de", "language_name": "German", "enabled": True},
        {"name": "es", "language_code": "es", "language_name": "Spanish", "enabled": True},
        {"name": "ja", "language_code": "ja", "language_name": "Japanese", "enabled": True},
    ])
    add_doc_rows("Role", [
        {"name": "System Manager", "desk_access": True, "disabled": False},
        {"name": "Administrator", "desk_access": True, "disabled": False},
        {"name": "Accounts Manager", "desk_access": True, "disabled": False},
        {"name": "Sales Manager", "desk_access": True, "disabled": False},
        {"name": "Purchase Manager", "desk_access": True, "disabled": False},
        {"name": "Stock Manager", "desk_access": True, "disabled": False},
        {"name": "Manufacturing Manager", "desk_access": True, "disabled": False},
        {"name": "HR Manager", "desk_access": True, "disabled": False},
        {"name": "Support Team", "desk_access": True, "disabled": False},
        {"name": "Academics User", "desk_access": True, "disabled": False},
    ])
    add_doc_rows("User", [
        {"name": "Administrator", "email": "admin@scratchbird-demo.example", "first_name": "System", "last_name": "Administrator", "full_name": "System Administrator", "enabled": True, "user_type": "System User", "language": "en"},
        {"name": "ada.lovelace@scratchbird-demo.example", "email": "ada.lovelace@scratchbird-demo.example", "first_name": "Ada", "last_name": "Lovelace", "full_name": "Ada Lovelace", "enabled": True, "user_type": "System User", "language": "en"},
        {"name": "grace.hopper@scratchbird-demo.example", "email": "grace.hopper@scratchbird-demo.example", "first_name": "Grace", "last_name": "Hopper", "full_name": "Grace Hopper", "enabled": True, "user_type": "System User", "language": "en"},
        {"name": "katherine.johnson@scratchbird-demo.example", "email": "katherine.johnson@scratchbird-demo.example", "first_name": "Katherine", "last_name": "Johnson", "full_name": "Katherine Johnson", "enabled": True, "user_type": "System User", "language": "en"},
        {"name": "alan.turing@scratchbird-demo.example", "email": "alan.turing@scratchbird-demo.example", "first_name": "Alan", "last_name": "Turing", "full_name": "Alan Turing", "enabled": True, "user_type": "System User", "language": "en"},
        {"name": "margaret.hamilton@scratchbird-demo.example", "email": "margaret.hamilton@scratchbird-demo.example", "first_name": "Margaret", "last_name": "Hamilton", "full_name": "Margaret Hamilton", "enabled": True, "user_type": "System User", "language": "en"},
        {"name": "donald.knuth@scratchbird-demo.example", "email": "donald.knuth@scratchbird-demo.example", "first_name": "Donald", "last_name": "Knuth", "full_name": "Donald Knuth", "enabled": True, "user_type": "System User", "language": "en"},
        {"name": "barbara.liskov@scratchbird-demo.example", "email": "barbara.liskov@scratchbird-demo.example", "first_name": "Barbara", "last_name": "Liskov", "full_name": "Barbara Liskov", "enabled": True, "user_type": "System User", "language": "en"},
    ])
    add_doc_rows("Module Def", [
        {"name": "Core", "module_name": "Core", "app_name": "frappe"},
        {"name": "Accounts", "module_name": "Accounts", "app_name": "erpnext"},
        {"name": "Selling", "module_name": "Selling", "app_name": "erpnext"},
        {"name": "Buying", "module_name": "Buying", "app_name": "erpnext"},
        {"name": "Stock", "module_name": "Stock", "app_name": "erpnext"},
        {"name": "Manufacturing", "module_name": "Manufacturing", "app_name": "erpnext"},
        {"name": "HR", "module_name": "HR", "app_name": "hrms"},
        {"name": "Payroll", "module_name": "Payroll", "app_name": "hrms"},
        {"name": "FCRM", "module_name": "FCRM", "app_name": "crm"},
        {"name": "Helpdesk", "module_name": "Helpdesk", "app_name": "helpdesk"},
        {"name": "Loan Management", "module_name": "Loan Management", "app_name": "lending"},
        {"name": "Education", "module_name": "Education", "app_name": "education"},
        {"name": "LMS", "module_name": "LMS", "app_name": "lms"},
        {"name": "Insights", "module_name": "Insights", "app_name": "insights"},
        {"name": "Press", "module_name": "Press", "app_name": "press"},
    ])
    add_doc_rows("UOM", [
        {"name": "Nos", "uom_name": "Nos", "enabled": True, "must_be_whole_number": True},
        {"name": "Kg", "uom_name": "Kilogram", "enabled": True, "must_be_whole_number": False},
        {"name": "Hour", "uom_name": "Hour", "enabled": True, "must_be_whole_number": False},
        {"name": "Box", "uom_name": "Box", "enabled": True, "must_be_whole_number": True},
        {"name": "Meter", "uom_name": "Meter", "enabled": True, "must_be_whole_number": False},
        {"name": "License", "uom_name": "License", "enabled": True, "must_be_whole_number": True},
    ])
    add_doc_rows("Fiscal Year", [
        {"name": "FY-2025", "year": "FY-2025", "year_start_date": "2025-01-01", "year_end_date": "2025-12-31", "disabled": False},
        {"name": "FY-2026", "year": "FY-2026", "year_start_date": "2026-01-01", "year_end_date": "2026-12-31", "disabled": False},
    ])

    # 3. Multi-Company Enterprise Setup (ERPNext)
    companies = [
        {"name": "Maple Tech Manufacturing", "company_name": "Maple Tech Manufacturing", "abbr": "MTM", "default_currency": "CAD", "country": "Canada", "domain": "Manufacturing"},
        {"name": "Northstar Cloud Services", "company_name": "Northstar Cloud Services", "abbr": "NCS", "default_currency": "USD", "country": "United States", "domain": "Services"},
        {"name": "Horizon Agritech Cooperative", "company_name": "Horizon Agritech Cooperative", "abbr": "HAC", "default_currency": "CAD", "country": "Canada", "domain": "Agriculture"},
    ]
    add_doc_rows("Company", companies)

    add_doc_rows("Cost Center", [
        {"name": "Main - MTM", "cost_center_name": "Main", "company": "Maple Tech Manufacturing", "is_group": True, "lft": 1, "rgt": 6},
        {"name": "Operations - MTM", "cost_center_name": "Operations", "company": "Maple Tech Manufacturing", "parent_cost_center": "Main - MTM", "is_group": False, "lft": 2, "rgt": 3},
        {"name": "R&D - MTM", "cost_center_name": "R&D", "company": "Maple Tech Manufacturing", "parent_cost_center": "Main - MTM", "is_group": False, "lft": 4, "rgt": 5},
        {"name": "Cloud Ops - NCS", "cost_center_name": "Cloud Ops", "company": "Northstar Cloud Services", "is_group": False, "lft": 7, "rgt": 8},
        {"name": "Field Farms - HAC", "cost_center_name": "Field Farms", "company": "Horizon Agritech Cooperative", "is_group": False, "lft": 9, "rgt": 10},
    ])

    add_doc_rows("Account", [
        {"name": "Assets - MTM", "account_name": "Application of Funds (Assets)", "company": "Maple Tech Manufacturing", "root_type": "Asset", "report_type": "Balance Sheet", "account_currency": "CAD", "is_group": True, "lft": 1, "rgt": 10},
        {"name": "Operating Bank - MTM", "account_name": "Operating Bank", "parent_account": "Assets - MTM", "company": "Maple Tech Manufacturing", "root_type": "Asset", "report_type": "Balance Sheet", "account_type": "Bank", "account_currency": "CAD", "is_group": False, "lft": 2, "rgt": 3},
        {"name": "Debtors - MTM", "account_name": "Accounts Receivable", "parent_account": "Assets - MTM", "company": "Maple Tech Manufacturing", "root_type": "Asset", "report_type": "Balance Sheet", "account_type": "Receivable", "account_currency": "CAD", "is_group": False, "lft": 4, "rgt": 5},
        {"name": "Stock In Hand - MTM", "account_name": "Stock In Hand", "parent_account": "Assets - MTM", "company": "Maple Tech Manufacturing", "root_type": "Asset", "report_type": "Balance Sheet", "account_type": "Stock", "account_currency": "CAD", "is_group": False, "lft": 6, "rgt": 7},
        {"name": "Liabilities - MTM", "account_name": "Source of Funds (Liabilities)", "company": "Maple Tech Manufacturing", "root_type": "Liability", "report_type": "Balance Sheet", "account_currency": "CAD", "is_group": True, "lft": 11, "rgt": 16},
        {"name": "Creditors - MTM", "account_name": "Accounts Payable", "parent_account": "Liabilities - MTM", "company": "Maple Tech Manufacturing", "root_type": "Liability", "report_type": "Balance Sheet", "account_type": "Payable", "account_currency": "CAD", "is_group": False, "lft": 12, "rgt": 13},
        {"name": "HST Payable - MTM", "account_name": "HST Tax Payable", "parent_account": "Liabilities - MTM", "company": "Maple Tech Manufacturing", "root_type": "Liability", "report_type": "Balance Sheet", "account_type": "Tax", "account_currency": "CAD", "is_group": False, "lft": 14, "rgt": 15},
        {"name": "Income - MTM", "account_name": "Income", "company": "Maple Tech Manufacturing", "root_type": "Income", "report_type": "Profit and Loss", "account_currency": "CAD", "is_group": True, "lft": 17, "rgt": 22},
        {"name": "Product Sales - MTM", "account_name": "Product Sales", "parent_account": "Income - MTM", "company": "Maple Tech Manufacturing", "root_type": "Income", "report_type": "Profit and Loss", "account_type": "Income Account", "account_currency": "CAD", "is_group": False, "lft": 18, "rgt": 19},
        {"name": "Service Revenue - NCS", "account_name": "Cloud Subscription Revenue", "company": "Northstar Cloud Services", "root_type": "Income", "report_type": "Profit and Loss", "account_type": "Income Account", "account_currency": "USD", "is_group": False, "lft": 20, "rgt": 21},
        {"name": "Expenses - MTM", "account_name": "Expenses", "company": "Maple Tech Manufacturing", "root_type": "Expense", "report_type": "Profit and Loss", "account_currency": "CAD", "is_group": True, "lft": 23, "rgt": 30},
        {"name": "Cost of Goods Sold - MTM", "account_name": "Cost of Goods Sold", "parent_account": "Expenses - MTM", "company": "Maple Tech Manufacturing", "root_type": "Expense", "report_type": "Profit and Loss", "account_type": "Cost of Goods Sold", "account_currency": "CAD", "is_group": False, "lft": 24, "rgt": 25},
        {"name": "Payroll Expense - MTM", "account_name": "Payroll Expense", "parent_account": "Expenses - MTM", "company": "Maple Tech Manufacturing", "root_type": "Expense", "report_type": "Profit and Loss", "account_type": "Expense Account", "account_currency": "CAD", "is_group": False, "lft": 26, "rgt": 27},
        {"name": "Cloud Hosting Expense - NCS", "account_name": "Cloud Infrastructure Expense", "company": "Northstar Cloud Services", "root_type": "Expense", "report_type": "Profit and Loss", "account_type": "Expense Account", "account_currency": "USD", "is_group": False, "lft": 28, "rgt": 29},
    ])

    add_doc_rows("Customer Group", [
        {"name": "All Customer Groups", "customer_group_name": "All Customer Groups", "is_group": True, "lft": 1, "rgt": 8},
        {"name": "Enterprise Industrial", "customer_group_name": "Enterprise Industrial", "parent_customer_group": "All Customer Groups", "is_group": False, "lft": 2, "rgt": 3},
        {"name": "SaaS Subscribers", "customer_group_name": "SaaS Subscribers", "parent_customer_group": "All Customer Groups", "is_group": False, "lft": 4, "rgt": 5},
        {"name": "Agricultural Cooperatives", "customer_group_name": "Agricultural Cooperatives", "parent_customer_group": "All Customer Groups", "is_group": False, "lft": 6, "rgt": 7},
    ])
    add_doc_rows("Supplier Group", [
        {"name": "All Supplier Groups", "supplier_group_name": "All Supplier Groups", "is_group": True},
        {"name": "Precision Components", "supplier_group_name": "Precision Components", "parent_supplier_group": "All Supplier Groups", "is_group": False},
        {"name": "Cloud & Datacenter Vendors", "supplier_group_name": "Cloud & Datacenter Vendors", "parent_supplier_group": "All Supplier Groups", "is_group": False},
        {"name": "Raw Materials & Seeds", "supplier_group_name": "Raw Materials & Seeds", "parent_supplier_group": "All Supplier Groups", "is_group": False},
    ])
    add_doc_rows("Territory", [
        {"name": "All Territories", "territory_name": "All Territories", "is_group": True, "lft": 1, "rgt": 8},
        {"name": "North America", "territory_name": "North America", "parent_territory": "All Territories", "is_group": False, "lft": 2, "rgt": 3},
        {"name": "Europe", "territory_name": "Europe", "parent_territory": "All Territories", "is_group": False, "lft": 4, "rgt": 5},
        {"name": "Asia Pacific", "territory_name": "Asia Pacific", "parent_territory": "All Territories", "is_group": False, "lft": 6, "rgt": 7},
    ])

    customers = [
        {"name": "CUST-0001", "customer_name": "Northwind Field Lab", "customer_type": "Company", "customer_group": "Enterprise Industrial", "territory": "North America", "default_currency": "CAD"},
        {"name": "CUST-0002", "customer_name": "Contoso Water Systems", "customer_type": "Company", "customer_group": "Enterprise Industrial", "territory": "North America", "default_currency": "CAD"},
        {"name": "CUST-0003", "customer_name": "Adventure Works Mining", "customer_type": "Company", "customer_group": "Enterprise Industrial", "territory": "North America", "default_currency": "CAD"},
        {"name": "CUST-0004", "customer_name": "Alpine Robotics GmbH", "customer_type": "Company", "customer_group": "Enterprise Industrial", "territory": "Europe", "default_currency": "EUR"},
        {"name": "CUST-0005", "customer_name": "Bluewater Maritime Logistics", "customer_type": "Company", "customer_group": "SaaS Subscribers", "territory": "North America", "default_currency": "USD"},
        {"name": "CUST-0006", "customer_name": "Prairie Grain Growers", "customer_type": "Company", "customer_group": "Agricultural Cooperatives", "territory": "North America", "default_currency": "CAD"},
        {"name": "CUST-0007", "customer_name": "Helios Solar Analytics", "customer_type": "Company", "customer_group": "SaaS Subscribers", "territory": "North America", "default_currency": "USD"},
        {"name": "CUST-0008", "customer_name": "Pacific Biotech Labs", "customer_type": "Company", "customer_group": "SaaS Subscribers", "territory": "Asia Pacific", "default_currency": "USD"},
    ]
    add_doc_rows("Customer", customers)

    suppliers = [
        {"name": "SUPP-0001", "supplier_name": "St. Lawrence Alloys Ltd.", "supplier_group": "Precision Components", "country": "Canada", "default_currency": "CAD"},
        {"name": "SUPP-0002", "supplier_name": "Boreal Semiconductor Corp.", "supplier_group": "Precision Components", "country": "United States", "default_currency": "USD"},
        {"name": "SUPP-0003", "supplier_name": "Northern Rack & Baremetal Inc.", "supplier_group": "Cloud & Datacenter Vendors", "country": "Canada", "default_currency": "CAD"},
        {"name": "SUPP-0004", "supplier_name": "Rheinland Hydraulics AG", "supplier_group": "Precision Components", "country": "Germany", "default_currency": "EUR"},
        {"name": "SUPP-0005", "supplier_name": "Heartland Organic Inputs", "supplier_group": "Raw Materials & Seeds", "country": "Canada", "default_currency": "CAD"},
    ]
    add_doc_rows("Supplier", suppliers)

    add_doc_rows("Item Group", [
        {"name": "All Item Groups", "item_group_name": "All Item Groups", "is_group": True, "lft": 1, "rgt": 10},
        {"name": "Industrial Assemblies", "item_group_name": "Industrial Assemblies", "parent_item_group": "All Item Groups", "is_group": False, "lft": 2, "rgt": 3},
        {"name": "Electronic Subsystems", "item_group_name": "Electronic Subsystems", "parent_item_group": "All Item Groups", "is_group": False, "lft": 4, "rgt": 5},
        {"name": "Cloud Subscriptions", "item_group_name": "Cloud Subscriptions", "parent_item_group": "All Item Groups", "is_group": False, "lft": 6, "rgt": 7},
        {"name": "Agricultural Inputs", "item_group_name": "Agricultural Inputs", "parent_item_group": "All Item Groups", "is_group": False, "lft": 8, "rgt": 9},
    ])

    items = [
        {"name": "ITM-PUMP-500", "item_code": "ITM-PUMP-500", "item_name": "Centrifugal Process Pump 500L", "item_group": "Industrial Assemblies", "stock_uom": "Nos", "is_stock_item": True, "standard_rate": 4250.00, "valuation_rate": 2850.00},
        {"name": "ITM-VALVE-210", "item_code": "ITM-VALVE-210", "item_name": "Actuated Control Valve DN80", "item_group": "Industrial Assemblies", "stock_uom": "Nos", "is_stock_item": True, "standard_rate": 1380.00, "valuation_rate": 890.00},
        {"name": "ITM-PLC-EDGE", "item_code": "ITM-PLC-EDGE", "item_name": "Edge Telemetry Gateway v4", "item_group": "Electronic Subsystems", "stock_uom": "Nos", "is_stock_item": True, "standard_rate": 980.00, "valuation_rate": 540.00},
        {"name": "ITM-MOTOR-15KW", "item_code": "ITM-MOTOR-15KW", "item_name": "Brushless Induction Motor 15kW", "item_group": "Electronic Subsystems", "stock_uom": "Nos", "is_stock_item": True, "standard_rate": 1650.00, "valuation_rate": 1050.00},
        {"name": "ITM-CLOUD-ENT", "item_code": "ITM-CLOUD-ENT", "item_name": "Managed Frappe Cloud Dedicated Bench", "item_group": "Cloud Subscriptions", "stock_uom": "License", "is_stock_item": False, "standard_rate": 850.00, "valuation_rate": 0.0},
        {"name": "ITM-SOIL-SENS", "item_code": "ITM-SOIL-SENS", "item_name": "LoRaWAN Soil Moisture Probe", "item_group": "Agricultural Inputs", "stock_uom": "Nos", "is_stock_item": True, "standard_rate": 320.00, "valuation_rate": 175.00},
    ]
    add_doc_rows("Item", items)

    add_doc_rows("Warehouse", [
        {"name": "All Warehouses - MTM", "warehouse_name": "All Warehouses", "company": "Maple Tech Manufacturing", "is_group": True, "lft": 1, "rgt": 6},
        {"name": "Toronto Main Stores - MTM", "warehouse_name": "Toronto Main Stores", "parent_warehouse": "All Warehouses - MTM", "company": "Maple Tech Manufacturing", "is_group": False, "lft": 2, "rgt": 3},
        {"name": "Hamilton Assembly WIP - MTM", "warehouse_name": "Hamilton Assembly WIP", "parent_warehouse": "All Warehouses - MTM", "company": "Maple Tech Manufacturing", "is_group": False, "lft": 4, "rgt": 5},
        {"name": "Saskatoon Agro Depot - HAC", "warehouse_name": "Saskatoon Agro Depot", "company": "Horizon Agritech Cooperative", "is_group": False, "lft": 7, "rgt": 8},
    ])

    # Sales Orders + Sales Order Items + Sales Invoices + Sales Invoice Items
    sales_orders = [
        {"name": "SAL-ORD-2026-0001", "customer": "CUST-0001", "customer_name": "Northwind Field Lab", "company": "Maple Tech Manufacturing", "transaction_date": "2026-09-02", "delivery_date": "2026-09-15", "currency": "CAD", "conversion_rate": 1.0, "net_total": 11260.00, "grand_total": 12723.80, "status": "Completed", "per_delivered": 100.0, "per_billed": 100.0},
        {"name": "SAL-ORD-2026-0002", "customer": "CUST-0002", "customer_name": "Contoso Water Systems", "company": "Maple Tech Manufacturing", "transaction_date": "2026-09-14", "delivery_date": "2026-09-28", "currency": "CAD", "conversion_rate": 1.0, "net_total": 17000.00, "grand_total": 19210.00, "status": "To Bill", "per_delivered": 100.0, "per_billed": 50.0},
        {"name": "SAL-ORD-2026-0003", "customer": "CUST-0003", "customer_name": "Adventure Works Mining", "company": "Maple Tech Manufacturing", "transaction_date": "2026-10-01", "delivery_date": "2026-10-20", "currency": "CAD", "conversion_rate": 1.0, "net_total": 8250.00, "grand_total": 9322.50, "status": "To Deliver and Bill", "per_delivered": 0.0, "per_billed": 0.0},
        {"name": "SAL-ORD-2026-0004", "customer": "CUST-0005", "customer_name": "Bluewater Maritime Logistics", "company": "Northstar Cloud Services", "transaction_date": "2026-10-05", "delivery_date": "2026-10-06", "currency": "USD", "conversion_rate": 1.0, "net_total": 5100.00, "grand_total": 5100.00, "status": "Completed", "per_delivered": 100.0, "per_billed": 100.0},
        {"name": "SAL-ORD-2026-0005", "customer": "CUST-0006", "customer_name": "Prairie Grain Growers", "company": "Horizon Agritech Cooperative", "transaction_date": "2026-10-12", "delivery_date": "2026-10-25", "currency": "CAD", "conversion_rate": 1.0, "net_total": 6400.00, "grand_total": 6720.00, "status": "To Deliver and Bill", "per_delivered": 40.0, "per_billed": 0.0},
    ]
    add_doc_rows("Sales Order", sales_orders)
    add_doc_rows("Sales Order Item", [
        {"name": "SOI-0001", "parent": "SAL-ORD-2026-0001", "parenttype": "Sales Order", "parentfield": "items", "item_code": "ITM-PUMP-500", "item_name": "Centrifugal Process Pump 500L", "qty": 2.0, "uom": "Nos", "rate": 4250.00, "amount": 8500.00, "warehouse": "Toronto Main Stores - MTM"},
        {"name": "SOI-0002", "parent": "SAL-ORD-2026-0001", "parenttype": "Sales Order", "parentfield": "items", "item_code": "ITM-VALVE-210", "item_name": "Actuated Control Valve DN80", "qty": 2.0, "uom": "Nos", "rate": 1380.00, "amount": 2760.00, "warehouse": "Toronto Main Stores - MTM"},
        {"name": "SOI-0003", "parent": "SAL-ORD-2026-0002", "parenttype": "Sales Order", "parentfield": "items", "item_code": "ITM-PUMP-500", "item_name": "Centrifugal Process Pump 500L", "qty": 4.0, "uom": "Nos", "rate": 4250.00, "amount": 17000.00, "warehouse": "Toronto Main Stores - MTM"},
        {"name": "SOI-0004", "parent": "SAL-ORD-2026-0003", "parenttype": "Sales Order", "parentfield": "items", "item_code": "ITM-MOTOR-15KW", "item_name": "Brushless Induction Motor 15kW", "qty": 5.0, "uom": "Nos", "rate": 1650.00, "amount": 8250.00, "warehouse": "Toronto Main Stores - MTM"},
        {"name": "SOI-0005", "parent": "SAL-ORD-2026-0004", "parenttype": "Sales Order", "parentfield": "items", "item_code": "ITM-CLOUD-ENT", "item_name": "Managed Frappe Cloud Dedicated Bench", "qty": 6.0, "uom": "License", "rate": 850.00, "amount": 5100.00},
        {"name": "SOI-0006", "parent": "SAL-ORD-2026-0005", "parenttype": "Sales Order", "parentfield": "items", "item_code": "ITM-SOIL-SENS", "item_name": "LoRaWAN Soil Moisture Probe", "qty": 20.0, "uom": "Nos", "rate": 320.00, "amount": 6400.00, "warehouse": "Saskatoon Agro Depot - HAC"},
    ])

    sales_invoices = [
        {"name": "ACC-SINV-2026-0001", "customer": "CUST-0001", "customer_name": "Northwind Field Lab", "company": "Maple Tech Manufacturing", "posting_date": "2026-09-16", "due_date": "2026-10-16", "currency": "CAD", "conversion_rate": 1.0, "debit_to": "Debtors - MTM", "net_total": 11260.00, "grand_total": 12723.80, "outstanding_amount": 0.00, "status": "Paid"},
        {"name": "ACC-SINV-2026-0002", "customer": "CUST-0002", "customer_name": "Contoso Water Systems", "company": "Maple Tech Manufacturing", "posting_date": "2026-09-29", "due_date": "2026-10-29", "currency": "CAD", "conversion_rate": 1.0, "debit_to": "Debtors - MTM", "net_total": 8500.00, "grand_total": 9605.00, "outstanding_amount": 3605.00, "status": "Partly Paid"},
        {"name": "ACC-SINV-2026-0003", "customer": "CUST-0005", "customer_name": "Bluewater Maritime Logistics", "company": "Northstar Cloud Services", "posting_date": "2026-10-06", "due_date": "2026-11-05", "currency": "USD", "conversion_rate": 1.0, "net_total": 5100.00, "grand_total": 5100.00, "outstanding_amount": 5100.00, "status": "Unpaid"},
        {"name": "ACC-SINV-2026-0004", "customer": "CUST-0007", "customer_name": "Helios Solar Analytics", "company": "Northstar Cloud Services", "posting_date": "2026-10-10", "due_date": "2026-11-09", "currency": "USD", "conversion_rate": 1.0, "net_total": 2550.00, "grand_total": 2550.00, "outstanding_amount": 0.00, "status": "Paid"},
    ]
    add_doc_rows("Sales Invoice", sales_invoices)
    add_doc_rows("Sales Invoice Item", [
        {"name": "SII-0001", "parent": "ACC-SINV-2026-0001", "parenttype": "Sales Invoice", "parentfield": "items", "item_code": "ITM-PUMP-500", "item_name": "Centrifugal Process Pump 500L", "qty": 2.0, "uom": "Nos", "rate": 4250.00, "amount": 8500.00, "income_account": "Product Sales - MTM", "cost_center": "Operations - MTM", "sales_order": "SAL-ORD-2026-0001"},
        {"name": "SII-0002", "parent": "ACC-SINV-2026-0001", "parenttype": "Sales Invoice", "parentfield": "items", "item_code": "ITM-VALVE-210", "item_name": "Actuated Control Valve DN80", "qty": 2.0, "uom": "Nos", "rate": 1380.00, "amount": 2760.00, "income_account": "Product Sales - MTM", "cost_center": "Operations - MTM", "sales_order": "SAL-ORD-2026-0001"},
        {"name": "SII-0003", "parent": "ACC-SINV-2026-0002", "parenttype": "Sales Invoice", "parentfield": "items", "item_code": "ITM-PUMP-500", "item_name": "Centrifugal Process Pump 500L", "qty": 2.0, "uom": "Nos", "rate": 4250.00, "amount": 8500.00, "income_account": "Product Sales - MTM", "cost_center": "Operations - MTM", "sales_order": "SAL-ORD-2026-0002"},
        {"name": "SII-0004", "parent": "ACC-SINV-2026-0003", "parenttype": "Sales Invoice", "parentfield": "items", "item_code": "ITM-CLOUD-ENT", "item_name": "Managed Frappe Cloud Dedicated Bench", "qty": 6.0, "uom": "License", "rate": 850.00, "amount": 5100.00, "income_account": "Service Revenue - NCS", "cost_center": "Cloud Ops - NCS", "sales_order": "SAL-ORD-2026-0004"},
        {"name": "SII-0005", "parent": "ACC-SINV-2026-0004", "parenttype": "Sales Invoice", "parentfield": "items", "item_code": "ITM-CLOUD-ENT", "item_name": "Managed Frappe Cloud Dedicated Bench", "qty": 3.0, "uom": "License", "rate": 850.00, "amount": 2550.00, "income_account": "Service Revenue - NCS", "cost_center": "Cloud Ops - NCS"},
    ])

    # Purchase Orders + Purchase Invoices + GL Entries + Stock Ledger
    add_doc_rows("Purchase Order", [
        {"name": "PUR-ORD-2026-0001", "supplier": "SUPP-0001", "supplier_name": "St. Lawrence Alloys Ltd.", "company": "Maple Tech Manufacturing", "transaction_date": "2026-08-20", "schedule_date": "2026-09-01", "currency": "CAD", "conversion_rate": 1.0, "net_total": 14250.00, "grand_total": 16102.50, "status": "Completed"},
        {"name": "PUR-ORD-2026-0002", "supplier": "SUPP-0002", "supplier_name": "Boreal Semiconductor Corp.", "company": "Maple Tech Manufacturing", "transaction_date": "2026-09-05", "schedule_date": "2026-09-18", "currency": "USD", "conversion_rate": 1.36, "net_total": 5400.00, "grand_total": 5400.00, "status": "To Bill"},
        {"name": "PUR-ORD-2026-0003", "supplier": "SUPP-0003", "supplier_name": "Northern Rack & Baremetal Inc.", "company": "Northstar Cloud Services", "transaction_date": "2026-09-25", "schedule_date": "2026-10-01", "currency": "CAD", "conversion_rate": 1.0, "net_total": 3200.00, "grand_total": 3616.00, "status": "Completed"},
    ])
    add_doc_rows("Purchase Invoice", [
        {"name": "ACC-PINV-2026-0001", "supplier": "SUPP-0001", "supplier_name": "St. Lawrence Alloys Ltd.", "company": "Maple Tech Manufacturing", "posting_date": "2026-09-03", "due_date": "2026-10-03", "currency": "CAD", "conversion_rate": 1.0, "credit_to": "Creditors - MTM", "net_total": 14250.00, "grand_total": 16102.50, "outstanding_amount": 0.00, "status": "Paid"},
        {"name": "ACC-PINV-2026-0002", "supplier": "SUPP-0003", "supplier_name": "Northern Rack & Baremetal Inc.", "company": "Northstar Cloud Services", "posting_date": "2026-10-02", "due_date": "2026-11-01", "currency": "CAD", "conversion_rate": 1.0, "net_total": 3200.00, "grand_total": 3616.00, "outstanding_amount": 3616.00, "status": "Unpaid"},
    ])
    add_doc_rows("Payment Entry", [
        {"name": "ACC-PAY-2026-0001", "payment_type": "Receive", "party_type": "Customer", "party": "CUST-0001", "party_name": "Northwind Field Lab", "company": "Maple Tech Manufacturing", "posting_date": "2026-09-25", "paid_from": "Debtors - MTM", "paid_to": "Operating Bank - MTM", "paid_amount": 12723.80, "received_amount": 12723.80, "status": "Submitted"},
        {"name": "ACC-PAY-2026-0002", "payment_type": "Receive", "party_type": "Customer", "party": "CUST-0002", "party_name": "Contoso Water Systems", "company": "Maple Tech Manufacturing", "posting_date": "2026-10-08", "paid_from": "Debtors - MTM", "paid_to": "Operating Bank - MTM", "paid_amount": 6000.00, "received_amount": 6000.00, "status": "Submitted"},
        {"name": "ACC-PAY-2026-0003", "payment_type": "Pay", "party_type": "Supplier", "party": "SUPP-0001", "party_name": "St. Lawrence Alloys Ltd.", "company": "Maple Tech Manufacturing", "posting_date": "2026-09-28", "paid_from": "Operating Bank - MTM", "paid_to": "Creditors - MTM", "paid_amount": 16102.50, "received_amount": 16102.50, "status": "Submitted"},
    ])
    add_doc_rows("GL Entry", [
        {"name": "GLE-2026-0001", "posting_date": "2026-09-16", "account": "Debtors - MTM", "party_type": "Customer", "party": "CUST-0001", "debit": 12723.80, "credit": 0.00, "voucher_type": "Sales Invoice", "voucher_no": "ACC-SINV-2026-0001", "company": "Maple Tech Manufacturing", "fiscal_year": "FY-2026", "is_cancelled": False},
        {"name": "GLE-2026-0002", "posting_date": "2026-09-16", "account": "Product Sales - MTM", "debit": 0.00, "credit": 11260.00, "voucher_type": "Sales Invoice", "voucher_no": "ACC-SINV-2026-0001", "company": "Maple Tech Manufacturing", "cost_center": "Operations - MTM", "fiscal_year": "FY-2026", "is_cancelled": False},
        {"name": "GLE-2026-0003", "posting_date": "2026-09-16", "account": "HST Payable - MTM", "debit": 0.00, "credit": 1463.80, "voucher_type": "Sales Invoice", "voucher_no": "ACC-SINV-2026-0001", "company": "Maple Tech Manufacturing", "fiscal_year": "FY-2026", "is_cancelled": False},
        {"name": "GLE-2026-0004", "posting_date": "2026-09-25", "account": "Operating Bank - MTM", "debit": 12723.80, "credit": 0.00, "voucher_type": "Payment Entry", "voucher_no": "ACC-PAY-2026-0001", "company": "Maple Tech Manufacturing", "fiscal_year": "FY-2026", "is_cancelled": False},
        {"name": "GLE-2026-0005", "posting_date": "2026-09-25", "account": "Debtors - MTM", "party_type": "Customer", "party": "CUST-0001", "debit": 0.00, "credit": 12723.80, "voucher_type": "Payment Entry", "voucher_no": "ACC-PAY-2026-0001", "company": "Maple Tech Manufacturing", "fiscal_year": "FY-2026", "is_cancelled": False},
        {"name": "GLE-2026-0006", "posting_date": "2026-09-29", "account": "Debtors - MTM", "party_type": "Customer", "party": "CUST-0002", "debit": 9605.00, "credit": 0.00, "voucher_type": "Sales Invoice", "voucher_no": "ACC-SINV-2026-0002", "company": "Maple Tech Manufacturing", "fiscal_year": "FY-2026", "is_cancelled": False},
        {"name": "GLE-2026-0007", "posting_date": "2026-09-29", "account": "Product Sales - MTM", "debit": 0.00, "credit": 8500.00, "voucher_type": "Sales Invoice", "voucher_no": "ACC-SINV-2026-0002", "company": "Maple Tech Manufacturing", "cost_center": "Operations - MTM", "fiscal_year": "FY-2026", "is_cancelled": False},
        {"name": "GLE-2026-0008", "posting_date": "2026-09-29", "account": "HST Payable - MTM", "debit": 0.00, "credit": 1105.00, "voucher_type": "Sales Invoice", "voucher_no": "ACC-SINV-2026-0002", "company": "Maple Tech Manufacturing", "fiscal_year": "FY-2026", "is_cancelled": False},
    ])
    add_doc_rows("Stock Ledger Entry", [
        {"name": "SLE-2026-0001", "item_code": "ITM-PUMP-500", "warehouse": "Toronto Main Stores - MTM", "posting_date": "2026-09-01", "actual_qty": 12.0, "qty_after_transaction": 12.0, "valuation_rate": 2850.00, "stock_value": 34200.00, "voucher_type": "Purchase Receipt", "voucher_no": "MAT-PRE-2026-0001", "company": "Maple Tech Manufacturing"},
        {"name": "SLE-2026-0002", "item_code": "ITM-PUMP-500", "warehouse": "Toronto Main Stores - MTM", "posting_date": "2026-09-15", "actual_qty": -2.0, "qty_after_transaction": 10.0, "valuation_rate": 2850.00, "stock_value": 28500.00, "voucher_type": "Delivery Note", "voucher_no": "MAT-DN-2026-0001", "company": "Maple Tech Manufacturing"},
        {"name": "SLE-2026-0003", "item_code": "ITM-VALVE-210", "warehouse": "Toronto Main Stores - MTM", "posting_date": "2026-09-01", "actual_qty": 25.0, "qty_after_transaction": 25.0, "valuation_rate": 890.00, "stock_value": 22250.00, "voucher_type": "Purchase Receipt", "voucher_no": "MAT-PRE-2026-0001", "company": "Maple Tech Manufacturing"},
        {"name": "SLE-2026-0004", "item_code": "ITM-SOIL-SENS", "warehouse": "Saskatoon Agro Depot - HAC", "posting_date": "2026-09-20", "actual_qty": 80.0, "qty_after_transaction": 80.0, "valuation_rate": 175.00, "stock_value": 14000.00, "voucher_type": "Purchase Receipt", "voucher_no": "MAT-PRE-2026-0002", "company": "Horizon Agritech Cooperative"},
    ])

    # 4. HRMS (Departments, Designations, Employees, Attendance, Salary Slips)
    add_doc_rows("Department", [
        {"name": "Engineering - MTM", "department_name": "Engineering", "company": "Maple Tech Manufacturing", "is_group": False},
        {"name": "Manufacturing - MTM", "department_name": "Manufacturing", "company": "Maple Tech Manufacturing", "is_group": False},
        {"name": "Finance & Operations - MTM", "department_name": "Finance & Operations", "company": "Maple Tech Manufacturing", "is_group": False},
        {"name": "Cloud Platform - NCS", "department_name": "Cloud Platform", "company": "Northstar Cloud Services", "is_group": False},
        {"name": "Agronomy Research - HAC", "department_name": "Agronomy Research", "company": "Horizon Agritech Cooperative", "is_group": False},
    ])
    add_doc_rows("Designation", [
        {"name": "Chief Technology Officer", "designation_name": "Chief Technology Officer"},
        {"name": "Principal Systems Engineer", "designation_name": "Principal Systems Engineer"},
        {"name": "Plant Operations Lead", "designation_name": "Plant Operations Lead"},
        {"name": "Senior Financial Analyst", "designation_name": "Senior Financial Analyst"},
        {"name": "Site Reliability Engineer", "designation_name": "Site Reliability Engineer"},
        {"name": "Agronomy Data Scientist", "designation_name": "Agronomy Data Scientist"},
    ])
    add_doc_rows("Employee", [
        {"name": "HR-EMP-0001", "employee": "HR-EMP-0001", "first_name": "Ada", "last_name": "Lovelace", "employee_name": "Ada Lovelace", "gender": "Female", "date_of_birth": "1986-12-10", "date_of_joining": "2021-02-01", "status": "Active", "company": "Maple Tech Manufacturing", "department": "Engineering - MTM", "designation": "Chief Technology Officer", "user_id": "ada.lovelace@scratchbird-demo.example"},
        {"name": "HR-EMP-0002", "employee": "HR-EMP-0002", "first_name": "Grace", "last_name": "Hopper", "employee_name": "Grace Hopper", "gender": "Female", "date_of_birth": "1988-05-19", "date_of_joining": "2021-06-15", "status": "Active", "company": "Maple Tech Manufacturing", "department": "Engineering - MTM", "designation": "Principal Systems Engineer", "reports_to": "HR-EMP-0001", "user_id": "grace.hopper@scratchbird-demo.example"},
        {"name": "HR-EMP-0003", "employee": "HR-EMP-0003", "first_name": "Katherine", "last_name": "Johnson", "employee_name": "Katherine Johnson", "gender": "Female", "date_of_birth": "1990-08-26", "date_of_joining": "2022-01-10", "status": "Active", "company": "Maple Tech Manufacturing", "department": "Finance & Operations - MTM", "designation": "Senior Financial Analyst", "reports_to": "HR-EMP-0001", "user_id": "katherine.johnson@scratchbird-demo.example"},
        {"name": "HR-EMP-0004", "employee": "HR-EMP-0004", "first_name": "Alan", "last_name": "Turing", "employee_name": "Alan Turing", "gender": "Male", "date_of_birth": "1989-06-23", "date_of_joining": "2022-04-04", "status": "Active", "company": "Northstar Cloud Services", "department": "Cloud Platform - NCS", "designation": "Site Reliability Engineer", "user_id": "alan.turing@scratchbird-demo.example"},
        {"name": "HR-EMP-0005", "employee": "HR-EMP-0005", "first_name": "Margaret", "last_name": "Hamilton", "employee_name": "Margaret Hamilton", "gender": "Female", "date_of_birth": "1991-08-17", "date_of_joining": "2022-09-01", "status": "Active", "company": "Maple Tech Manufacturing", "department": "Manufacturing - MTM", "designation": "Plant Operations Lead", "reports_to": "HR-EMP-0001", "user_id": "margaret.hamilton@scratchbird-demo.example"},
        {"name": "HR-EMP-0006", "employee": "HR-EMP-0006", "first_name": "Barbara", "last_name": "Liskov", "employee_name": "Barbara Liskov", "gender": "Female", "date_of_birth": "1993-11-07", "date_of_joining": "2023-03-15", "status": "Active", "company": "Horizon Agritech Cooperative", "department": "Agronomy Research - HAC", "designation": "Agronomy Data Scientist", "user_id": "barbara.liskov@scratchbird-demo.example"},
    ])
    add_doc_rows("Salary Slip", [
        {"name": "SAL-SLIP-2026-0001", "employee": "HR-EMP-0001", "employee_name": "Ada Lovelace", "company": "Maple Tech Manufacturing", "department": "Engineering - MTM", "designation": "Chief Technology Officer", "posting_date": "2026-09-30", "start_date": "2026-09-01", "end_date": "2026-09-30", "currency": "CAD", "gross_pay": 16500.00, "total_deduction": 4125.00, "net_pay": 12375.00, "status": "Submitted"},
        {"name": "SAL-SLIP-2026-0002", "employee": "HR-EMP-0002", "employee_name": "Grace Hopper", "company": "Maple Tech Manufacturing", "department": "Engineering - MTM", "designation": "Principal Systems Engineer", "posting_date": "2026-09-30", "start_date": "2026-09-01", "end_date": "2026-09-30", "currency": "CAD", "gross_pay": 13800.00, "total_deduction": 3312.00, "net_pay": 10488.00, "status": "Submitted"},
        {"name": "SAL-SLIP-2026-0003", "employee": "HR-EMP-0003", "employee_name": "Katherine Johnson", "company": "Maple Tech Manufacturing", "department": "Finance & Operations - MTM", "designation": "Senior Financial Analyst", "posting_date": "2026-09-30", "start_date": "2026-09-01", "end_date": "2026-09-30", "currency": "CAD", "gross_pay": 11500.00, "total_deduction": 2645.00, "net_pay": 8855.00, "status": "Submitted"},
        {"name": "SAL-SLIP-2026-0004", "employee": "HR-EMP-0004", "employee_name": "Alan Turing", "company": "Northstar Cloud Services", "department": "Cloud Platform - NCS", "designation": "Site Reliability Engineer", "posting_date": "2026-09-30", "start_date": "2026-09-01", "end_date": "2026-09-30", "currency": "USD", "gross_pay": 14200.00, "total_deduction": 3408.00, "net_pay": 10792.00, "status": "Submitted"},
    ])

    # 5. CRM, Helpdesk, Lending, Education & LMS, Press Cloud
    add_doc_rows("CRM Lead", [
        {"name": "CRM-LEAD-2026-001", "first_name": "Henrik", "last_name": "Lindqvist", "lead_name": "Henrik Lindqvist", "organization": "Nordic Hydro Power", "email": "h.lindqvist@nordichydro.example", "status": "Qualified", "annual_revenue": 4800000.00},
        {"name": "CRM-LEAD-2026-002", "first_name": "Priya", "last_name": "Natarajan", "lead_name": "Priya Natarajan", "organization": "Deccan Cold-Chain Logistics", "email": "priya@deccancold.example", "status": "Contacted", "annual_revenue": 2200000.00},
        {"name": "CRM-LEAD-2026-003", "first_name": "Claire", "last_name": "Beaumont", "lead_name": "Claire Beaumont", "organization": "St-Laurent Biofuels", "email": "c.beaumont@stlaurentbio.example", "status": "Qualified", "annual_revenue": 6100000.00},
    ])
    add_doc_rows("CRM Deal", [
        {"name": "CRM-DEAL-2026-001", "organization_name": "Nordic Hydro Power", "deal_owner": "ada.lovelace@scratchbird-demo.example", "annual_revenue": 185000.00, "probability": 75.0, "expected_closure_date": "2026-11-30"},
        {"name": "CRM-DEAL-2026-002", "organization_name": "St-Laurent Biofuels", "deal_owner": "grace.hopper@scratchbird-demo.example", "annual_revenue": 94000.00, "probability": 60.0, "expected_closure_date": "2026-12-15"},
    ])
    add_doc_rows("HD Ticket", [
        {"name": "HD-TKT-1001", "subject": "Pump 500L vibration telemetry threshold alert", "status": "Open", "priority": "High", "raised_by": "ops@northwindlab.example", "description": "Edge gateway ITM-PLC-EDGE reported 6.2 mm/s RMS vibration on bearing B."},
        {"name": "HD-TKT-1002", "subject": "Dedicated cloud bench SSL certificate renewal check", "status": "Replied", "priority": "Medium", "raised_by": "devops@bluewater.example", "description": "Confirm Let's Encrypt wildcard renewal window on prod bench."},
        {"name": "HD-TKT-1003", "subject": "Soil moisture calibration curve for clay-loam fields", "status": "Resolved", "priority": "Low", "raised_by": "agronomy@prairiegrain.example", "description": "Applied v2.4 dielectric calibration profile across 20 probes."},
    ])
    add_doc_rows("Loan", [
        {"name": "LOAN-2026-0001", "applicant_type": "Customer", "applicant": "CUST-0006", "applicant_name": "Prairie Grain Growers", "company": "Horizon Agritech Cooperative", "loan_amount": 120000.00, "rate_of_interest": 5.75, "disbursed_amount": 120000.00, "total_amount_paid": 24500.00, "status": "Disbursed"},
        {"name": "LOAN-2026-0002", "applicant_type": "Customer", "applicant": "CUST-0001", "applicant_name": "Northwind Field Lab", "company": "Maple Tech Manufacturing", "loan_amount": 85000.00, "rate_of_interest": 6.25, "disbursed_amount": 85000.00, "total_amount_paid": 85000.00, "status": "Closed"},
    ])
    add_doc_rows("LMS Course", [
        {"name": "LMS-CRS-FIREBIRD-5", "title": "Firebird 5.0 Architecture & PSQL Mastery", "published": True, "upcoming": False, "paid_course": False, "enrollments": 48},
        {"name": "LMS-CRS-DDN-MODELING", "title": "Enterprise Data Modeling & Dimensional Cubes with DDN", "published": True, "upcoming": False, "paid_course": True, "course_price": 299.00, "currency": "USD", "enrollments": 35},
        {"name": "LMS-CRS-IOT-TELEMETRY", "title": "Industrial Telemetry & Predictive Maintenance", "published": True, "upcoming": False, "paid_course": False, "enrollments": 29},
    ])
    add_doc_rows("Site", [
        {"name": "erp.mapletech.cloud", "subdomain": "erp-mapletech", "status": "Active", "cluster": "ca-central-1", "plan": "Enterprise Dedicated"},
        {"name": "portal.northstarcloud.io", "subdomain": "portal-northstar", "status": "Active", "cluster": "us-east-1", "plan": "Business Plus"},
        {"name": "coop.horizonagritech.ca", "subdomain": "coop-horizon", "status": "Active", "cluster": "ca-west-1", "plan": "Cooperative Pro"},
    ])

    # 6. Companion Schemas: Datum + Cargo, Stalwart, Boat, Mobile Accounting, PyWall, Frappe Runtime
    add_doc_rows("FRAPPE_SERIES", [
        {"SERIES_NAME": "SAL-ORD-2026-", "CURRENT_VAL": 5},
        {"SERIES_NAME": "ACC-SINV-2026-", "CURRENT_VAL": 4},
        {"SERIES_NAME": "PUR-ORD-2026-", "CURRENT_VAL": 3},
        {"SERIES_NAME": "HR-EMP-", "CURRENT_VAL": 6},
        {"SERIES_NAME": "HD-TKT-", "CURRENT_VAL": 1003},
    ], by_doctype=False)
    add_doc_rows("FRAPPE_SINGLES_KV", [
        {"DOCTYPE_NAME": "System Settings", "FIELD_NAME": "country", "FIELD_VALUE": "Canada"},
        {"DOCTYPE_NAME": "System Settings", "FIELD_NAME": "time_zone", "FIELD_VALUE": "America/Toronto"},
        {"DOCTYPE_NAME": "Global Defaults", "FIELD_NAME": "default_company", "FIELD_VALUE": "Maple Tech Manufacturing"},
        {"DOCTYPE_NAME": "Global Defaults", "FIELD_NAME": "default_currency", "FIELD_VALUE": "CAD"},
        {"DOCTYPE_NAME": "Accounts Settings", "FIELD_NAME": "unlink_payment_on_cancellation_of_invoice", "FIELD_VALUE": "1"},
    ], by_doctype=False)
    add_doc_rows("FRAPPE_AUTH", [
        {"DOCTYPE_NAME": "User", "DOC_NAME": "Administrator", "FIELD_NAME": "password", "PASSWD_HASH": "$pbkdf2-sha256$29000$demo$hash01", "ENCRYPTED_FLAG": False},
        {"DOCTYPE_NAME": "Email Account", "DOC_NAME": "Notifications", "FIELD_NAME": "password", "PASSWD_HASH": "gAAAAABdemoEncryptedToken==", "ENCRYPTED_FLAG": True},
    ], by_doctype=False)
    add_doc_rows("FRAPPE_USER_SETTINGS", [
        {"USER_ID": "Administrator", "DOCTYPE_NAME": "Sales Invoice", "SETTINGS_JSON": '{"last_view":"List","List":{"sort_by":"posting_date","sort_order":"desc"}}'},
        {"USER_ID": "ada.lovelace@scratchbird-demo.example", "DOCTYPE_NAME": "HD Ticket", "SETTINGS_JSON": '{"last_view":"Kanban"}'},
    ], by_doctype=False)
    add_doc_rows("FRAPPE_GLOBAL_SEARCH", [
        {"DOCTYPE_NAME": "Customer", "DOC_NAME": "CUST-0001", "TITLE": "Northwind Field Lab", "CONTENT_TEXT": "Northwind Field Lab Enterprise Industrial Toronto Canada", "ROUTE_PATH": "/app/customer/CUST-0001", "PUBLISHED_FLAG": True},
        {"DOCTYPE_NAME": "Item", "DOC_NAME": "ITM-PUMP-500", "TITLE": "Centrifugal Process Pump 500L", "CONTENT_TEXT": "ITM-PUMP-500 Centrifugal Process Pump 500L Industrial Assemblies", "ROUTE_PATH": "/app/item/ITM-PUMP-500", "PUBLISHED_FLAG": True},
    ], by_doctype=False)

    # Datum + Cargo samples, logs & traces (triggers will auto-populate DATUM_DAILY_* stats!)
    add_doc_rows("DATUM_SAMPLES", [
        {"SAMPLE_ID": 1, "TS": "2026-11-15 16:00:00+00:00", "METRIC": "system_cpu_usage_percent", "RESOURCE_ID": "cargo:prod-bench-01", "SERVICE_NAME": "web", "SERIES_KIND": "cpu", "LABELS_JSON": '{"service":"web","host":"bench-01"}', "SAMPLE_VALUE": 34.8},
        {"SAMPLE_ID": 2, "TS": "2026-11-15 16:01:00+00:00", "METRIC": "system_memory_usage_percent", "RESOURCE_ID": "cargo:prod-bench-01", "SERVICE_NAME": "web", "SERIES_KIND": "mem", "LABELS_JSON": '{"service":"web","host":"bench-01"}', "SAMPLE_VALUE": 61.2},
        {"SAMPLE_ID": 3, "TS": "2026-11-15 16:01:00+00:00", "METRIC": "mariadb_queries_total", "RESOURCE_ID": "cargo:prod-bench-01", "SERVICE_NAME": "db", "SERIES_KIND": "select", "LABELS_JSON": '{"service":"db","kind":"select"}', "SAMPLE_VALUE": 148200.0},
        {"SAMPLE_ID": 4, "TS": "2026-11-15 16:02:00+00:00", "METRIC": "mariadb_queries_total", "RESOURCE_ID": "cargo:prod-bench-01", "SERVICE_NAME": "db", "SERIES_KIND": "select", "LABELS_JSON": '{"service":"db","kind":"select"}', "SAMPLE_VALUE": 149650.0},
        {"SAMPLE_ID": 5, "TS": "2026-11-15 16:02:00+00:00", "METRIC": "system_cpu_usage_percent", "RESOURCE_ID": "cargo:prod-bench-02", "SERVICE_NAME": "worker", "SERIES_KIND": "cpu", "LABELS_JSON": '{"service":"worker","host":"bench-02"}', "SAMPLE_VALUE": 48.5},
        {"SAMPLE_ID": 6, "TS": "2026-11-15 16:03:00+00:00", "METRIC": "system_disk_usage_percent", "RESOURCE_ID": "cargo:prod-bench-02", "SERVICE_NAME": "storage", "SERIES_KIND": "disk", "LABELS_JSON": '{"service":"storage","host":"bench-02"}', "SAMPLE_VALUE": 42.1},
    ], by_doctype=False)
    add_doc_rows("DATUM_LOGS", [
        {"LOG_ID": 1, "TS": "2026-11-15 16:01:12+00:00", "RESOURCE_ID": "cargo:prod-bench-01", "PRODUCT": "frappe-cloud", "SERVICE_NAME": "nginx", "LOG_LEVEL": "INFO", "LOG_SOURCE": "nginx-access.log", "HTTP_STATUS": 200, "MESSAGE_TEXT": "GET /api/method/frappe.desk.reportview.get 200 18ms", "ATTRIBUTES_JSON": '{"status":"200","latency_ms":"18"}'},
        {"LOG_ID": 2, "TS": "2026-11-15 16:01:45+00:00", "RESOURCE_ID": "cargo:prod-bench-01", "PRODUCT": "frappe-cloud", "SERVICE_NAME": "gunicorn", "LOG_LEVEL": "WARN", "LOG_SOURCE": "frappe-web.log", "HTTP_STATUS": 429, "MESSAGE_TEXT": "Webhook rate threshold reached for tenant erp.mapletech.cloud", "ATTRIBUTES_JSON": '{"status":"429","site":"erp.mapletech.cloud"}'},
        {"LOG_ID": 3, "TS": "2026-11-15 16:02:10+00:00", "RESOURCE_ID": "cargo:prod-bench-02", "PRODUCT": "frappe-cloud", "SERVICE_NAME": "nginx", "LOG_LEVEL": "ERROR", "LOG_SOURCE": "nginx-access.log", "HTTP_STATUS": 502, "MESSAGE_TEXT": "Upstream worker timeout during bulk PDF print batch", "ATTRIBUTES_JSON": '{"status":"502","worker":"short-02"}'},
    ], by_doctype=False)
    add_doc_rows("DATUM_TRACES", [
        {"TRACE_ID": "4bf92f3577b34da6a3ce929d0e0e4736", "SPAN_ID": "00f067aa0ba902b7", "PARENT_SPAN_ID": None, "TS": "2026-11-15 16:01:12+00:00", "RESOURCE_ID": "cargo:prod-bench-01", "SERVICE_NAME": "frappe-web", "SPAN_NAME": "POST /api/resource/Sales Invoice", "SPAN_KIND": "SERVER", "DURATION_NS": 42500000, "STATUS_CODE": "OK", "STATUS_MESSAGE": "", "ATTRIBUTES_JSON": '{"http.method":"POST","doctype":"Sales Invoice"}'},
        {"TRACE_ID": "4bf92f3577b34da6a3ce929d0e0e4736", "SPAN_ID": "b7ad6b7169203331", "PARENT_SPAN_ID": "00f067aa0ba902b7", "TS": "2026-11-15 16:01:12+00:00", "RESOURCE_ID": "cargo:prod-bench-01", "SERVICE_NAME": "firebird-db", "SPAN_NAME": "INSERT INTO GL_ENTRY", "SPAN_KIND": "CLIENT", "DURATION_NS": 6100000, "STATUS_CODE": "OK", "STATUS_MESSAGE": "", "ATTRIBUTES_JSON": '{"db.system":"firebird","db.name":"frappe_suite.fdb"}'},
    ], by_doctype=False)

    # Stalwart Mail
    add_doc_rows("STALWART_ACCOUNTS", [
        {"ACCOUNT_NAME": "ada@mapletech.cloud", "SECRET_HASH": "$argon2id$v=19$demo$ada", "DESCRIPTION": "Ada Lovelace", "ACCOUNT_TYPE": "individual", "QUOTA_BYTES": 10737418240, "ACTIVE_FLAG": True},
        {"ACCOUNT_NAME": "grace@mapletech.cloud", "SECRET_HASH": "$argon2id$v=19$demo$grace", "DESCRIPTION": "Grace Hopper", "ACCOUNT_TYPE": "individual", "QUOTA_BYTES": 10737418240, "ACTIVE_FLAG": True},
        {"ACCOUNT_NAME": "engineering@mapletech.cloud", "SECRET_HASH": "", "DESCRIPTION": "Engineering Group", "ACCOUNT_TYPE": "group", "QUOTA_BYTES": 0, "ACTIVE_FLAG": True},
    ], by_doctype=False)
    add_doc_rows("STALWART_GROUP_MEMBERS", [
        {"ACCOUNT_NAME": "ada@mapletech.cloud", "MEMBER_OF": "engineering@mapletech.cloud"},
        {"ACCOUNT_NAME": "grace@mapletech.cloud", "MEMBER_OF": "engineering@mapletech.cloud"},
    ], by_doctype=False)
    add_doc_rows("STALWART_EMAILS", [
        {"ACCOUNT_NAME": "ada@mapletech.cloud", "EMAIL_ADDRESS": "ada@mapletech.cloud", "EMAIL_ROLE": "primary"},
        {"ACCOUNT_NAME": "ada@mapletech.cloud", "EMAIL_ADDRESS": "cto@mapletech.cloud", "EMAIL_ROLE": "alias"},
        {"ACCOUNT_NAME": "grace@mapletech.cloud", "EMAIL_ADDRESS": "grace@mapletech.cloud", "EMAIL_ROLE": "primary"},
    ], by_doctype=False)
    add_doc_rows("STALWART_STORE_DATA", [
        {"STORE_KEY": b"jmap:mailbox:ada:inbox", "STORE_VAL": b'{"name":"Inbox","role":"inbox","totalEmails":14}'},
        {"STORE_KEY": b"jmap:mailbox:grace:inbox", "STORE_VAL": b'{"name":"Inbox","role":"inbox","totalEmails":9}'},
    ], by_doctype=False)
    add_doc_rows("STALWART_STORE_INDEX", [
        {"INDEX_KEY": b"idx:email:ada:2026-11-15:0001"},
        {"INDEX_KEY": b"idx:email:grace:2026-11-15:0002"},
    ], by_doctype=False)
    add_doc_rows("STALWART_STORE_COUNTER", [
        {"COUNTER_KEY": b"seq:jmap_state", "COUNTER_VAL": 1042},
        {"COUNTER_KEY": b"seq:blob_gc", "COUNTER_VAL": 19},
    ], by_doctype=False)
    add_doc_rows("STALWART_STORE_BLOB", [
        {"BLOB_HASH": "sha256:9f86d081884c7d659a2feaa0c55ad015", "BYTE_SIZE": 78, "PAYLOAD": b"Subject: Q4 Production Pump Schedule\r\nFrom: ada@mapletech.cloud\r\n\r\nApproved."},
    ], by_doctype=False)

    # Boat Hypervisor
    add_doc_rows("BOAT_VIRTUAL_MACHINE", [
        {"VM_ID": "vm-bench-ca-01", "HOSTNAME": "bench-ca-01.internal", "DESIRED_POWER": "Running", "OBSERVED_STATUS": "Running", "VCPU_COUNT": 8, "MEM_MIB": 16384, "IPV4_CIDR": "10.42.1.10/24", "WAKE_ON_SYN": False, "UPDATED_AT": "2026-11-15 15:00:00+00:00"},
        {"VM_ID": "vm-bench-us-02", "HOSTNAME": "bench-us-02.internal", "DESIRED_POWER": "Running", "OBSERVED_STATUS": "Sleeping", "VCPU_COUNT": 4, "MEM_MIB": 8192, "IPV4_CIDR": "10.42.2.15/24", "WAKE_ON_SYN": True, "UPDATED_AT": "2026-11-15 15:30:00+00:00"},
    ], by_doctype=False)
    add_doc_rows("BOAT_DECISION_JOURNAL", [
        {"OPERATION_ID": "op-20261115-001", "STEP_NAME": "allocate_ipv4", "VM_ID": "vm-bench-ca-01", "VALUES_JSON": '{"ipv4":"10.42.1.10/24","tap":"tap01"}', "DECIDED_AT": "2026-11-15 14:58:00+00:00"},
        {"OPERATION_ID": "op-20261115-002", "STEP_NAME": "create_root_volume", "VM_ID": "vm-bench-us-02", "VALUES_JSON": '{"volume_id":"vol-us-02-root","size_gib":"80"}', "DECIDED_AT": "2026-11-15 15:25:00+00:00"},
    ], by_doctype=False)
    add_doc_rows("BOAT_VOLUME", [
        {"VOLUME_ID": "vol-ca-01-root", "VM_ID": "vm-bench-ca-01", "DEVICE_PATH": "/dev/vda", "SIZE_GIB": 120, "ROOT_FS_FLAG": True},
        {"VOLUME_ID": "vol-us-02-root", "VM_ID": "vm-bench-us-02", "DEVICE_PATH": "/dev/vda", "SIZE_GIB": 80, "ROOT_FS_FLAG": True},
    ], by_doctype=False)

    # Mobile Accounting & PyWall
    add_doc_rows("MOBACC_ACCOUNT", [
        {"DOC_NAME": "Assets", "OWNER_USER": "Administrator", "MODIFIED_BY": "Administrator", "LFT_NODE": 1, "RGT_NODE": 4, "PARENT_ACCOUNT": None, "ROOT_TYPE": "Asset", "ACCOUNT_TYPE": "Group", "IS_GROUP": True},
        {"DOC_NAME": "Cash Drawer", "OWNER_USER": "Administrator", "MODIFIED_BY": "Administrator", "LFT_NODE": 2, "RGT_NODE": 3, "PARENT_ACCOUNT": "Assets", "ROOT_TYPE": "Asset", "ACCOUNT_TYPE": "Cash", "IS_GROUP": False},
        {"DOC_NAME": "Sales Income", "OWNER_USER": "Administrator", "MODIFIED_BY": "Administrator", "LFT_NODE": 5, "RGT_NODE": 6, "PARENT_ACCOUNT": None, "ROOT_TYPE": "Income", "ACCOUNT_TYPE": "Income Account", "IS_GROUP": False},
        {"DOC_NAME": "Field Supplies Expense", "OWNER_USER": "Administrator", "MODIFIED_BY": "Administrator", "LFT_NODE": 7, "RGT_NODE": 8, "PARENT_ACCOUNT": None, "ROOT_TYPE": "Expense", "ACCOUNT_TYPE": "Expense Account", "IS_GROUP": False},
    ], by_doctype=False)
    add_doc_rows("MOBACC_PARTY", [
        {"DOC_NAME": "Northwind Retail Kiosk", "OWNER_USER": "Administrator", "MODIFIED_BY": "Administrator", "KEYWORDS": "retail,ontario", "IS_CUSTOMER": True, "IS_SUPPLIER": False},
        {"DOC_NAME": "Metro Packaging Supply", "OWNER_USER": "Administrator", "MODIFIED_BY": "Administrator", "KEYWORDS": "packaging,boxes", "IS_CUSTOMER": False, "IS_SUPPLIER": True},
    ], by_doctype=False)
    add_doc_rows("MOBACC_TAX", [
        {"DOC_NAME": "ON-HST-13", "TAX_RATE": 13.0, "ENABLED_FLAG": True},
        {"DOC_NAME": "EXEMPT-0", "TAX_RATE": 0.0, "ENABLED_FLAG": True},
    ], by_doctype=False)
    add_doc_rows("MOBACC_ITEM", [
        {"DOC_NAME": "MOB-KIT-01", "OWNER_USER": "Administrator", "MODIFIED_BY": "Administrator", "DESCRIPTION": "Portable Valve Calibration Kit", "UNIT_CODE": "Nos", "INCOME_ACCOUNT": "Sales Income", "EXPENSE_ACCOUNT": "Field Supplies Expense", "TAX_REF": "ON-HST-13", "UNIT_RATE": 245.00},
    ], by_doctype=False)
    add_doc_rows("PYWALL_WALL", [
        {"POST_ID": 1, "MESSAGE_TEXT": "Welcome to the unified ScratchRobin Firebird 5.0 Frappe Enterprise Suite!", "POSTED_BY": "Ada Lovelace", "POSTED_ON": "2026-11-15 09:30:00"},
        {"POST_ID": 2, "MESSAGE_TEXT": "All 235 donor repositories analyzed and represented with live relational integrity.", "POSTED_BY": "Grace Hopper", "POSTED_ON": "2026-11-15 10:15:00"},
    ], by_doctype=False)

    # 7. Pre-seed deterministic PK pools for EVERY remaining table (2 rows per table, 1 row for singletons)
    # so that foreign keys across all ~2,950 tables resolve 100% cleanly without missing targets!
    for tname, spec in sorted(tables_by_name.items()):
        if tname in rows_by_table:
            continue
        if spec.pk_columns != ["DOC_NAME"]:
            continue
        prefix = tname[:36].rstrip("_")
        count = 1 if spec.kind == "single" else 2
        pk_pool[tname] = [
            spec.orig_name[:76] if spec.kind == "single" else f"{prefix}-{i:03d}"
            for i in range(1, count + 1)
        ]

    # Now ensure curated tables also reject any dangling FK values if a curated row referenced
    # a Link column whose target table wasn't curated yet (or normalize it to a valid target PK).
    for tname, existing_rows in list(rows_by_table.items()):
        spec = tables_by_name[tname]
        for row in existing_rows:
            for col in spec.columns:
                target_t = fk_map.get((tname, col.col_name))
                if not target_t:
                    continue
                val = row.get(col.col_name)
                valid_pks = pk_pool.get(target_t, [])
                if val is not None and str(val) not in valid_pks:
                    row[col.col_name] = valid_pks[0] if (valid_pks and target_t != tname) else None

    # 8. Populate deterministic, domain-appropriate, FK-valid sample rows for all remaining tables!
    for tname, spec in sorted(tables_by_name.items()):
        if tname in rows_by_table:
            continue
        if spec.pk_columns != ["DOC_NAME"]:
            continue
        target_pks = pk_pool[tname]
        generated_rows: list[dict[str, object]] = []
        for idx, doc_id in enumerate(target_pks, start=1):
            row: dict[str, object] = {
                "DOC_NAME": doc_id,
                "CREATION_TS": f"2026-0{min(idx, 9)}-10 10:00:00",
                "MODIFIED_TS": f"2026-10-{10 + idx:02d} 15:30:00",
                "MODIFIED_BY": "Administrator",
                "OWNER_USER": "Administrator",
                "DOCSTATUS": 1 if spec.is_submittable else 0,
                "IDX_NO": idx,
            }
            if spec.kind == "child" or "PARENT_ID" in {c.col_name for c in spec.columns}:
                fk_parent_table = fk_map.get((tname, "PARENT_ID"))
                if fk_parent_table and pk_pool.get(fk_parent_table):
                    parent_pks = pk_pool[fk_parent_table]
                    row["PARENT_ID"] = parent_pks[(idx - 1) % len(parent_pks)]
                    row["PARENT_TYPE"] = tables_by_name[fk_parent_table].orig_name[:80]
                    row["PARENT_FIELD"] = "items"
                elif spec.parent_doctypes:
                    any_parent = sorted(spec.parent_doctypes)[0]
                    row["PARENT_TYPE"] = any_parent.replace("__BOOKS__:", "")[:80]
                    row["PARENT_ID"] = f"POLY-{idx:03d}"
                    row["PARENT_FIELD"] = "items"
            if spec.is_tree:
                row["LFT_NODE"] = idx * 2 - 1
                row["RGT_NODE"] = idx * 2
                row["OLD_PARENT"] = None

            for col in spec.columns:
                if col.col_name in row:
                    continue
                target_t = fk_map.get((tname, col.col_name))
                if target_t:
                    if target_t == tname:
                        # Self-referential hierarchy: root on row 1, child on row 2
                        row[col.col_name] = target_pks[0] if idx > 1 else None
                    else:
                        cand_pks = pk_pool.get(target_t, [])
                        row[col.col_name] = cand_pks[(idx - 1) % len(cand_pks)] if cand_pks else None
                    continue

                row[col.col_name] = _sample_scalar_value(spec, col, idx)
            generated_rows.append(row)
        rows_by_table[tname] = generated_rows

    return rows_by_table, pk_pool


def _sample_scalar_value(spec: TableSpec, col: ColumnSpec, idx: int) -> object:
    ft = col.fb_type
    fn_low = col.orig_fieldname.lower()

    if ft == "D_BOOL":
        if fn_low in ("disabled", "is_cancelled", "docstatus"):
            return False
        return idx == 1
    if ft in ("D_MONEY",):
        return round(250.0 * idx, 2)
    if ft in ("D_RATE",):
        return 1.0 if "exchange" in fn_low or "conversion" in fn_low else round(45.5 * idx, 4)
    if ft in ("D_PERCENT",):
        return round(min(12.5 * idx, 100.0), 2)
    if ft in ("D_QTY", "DOUBLE PRECISION DEFAULT 0", "DOUBLE PRECISION"):
        return float(idx * 5)
    if ft in ("INTEGER DEFAULT 0", "INTEGER", "BIGINT DEFAULT 0", "BIGINT", "SMALLINT DEFAULT 0", "SMALLINT"):
        return idx
    if ft == "DATE":
        return f"2026-{min(idx + 2, 9):02d}-{(idx % 20) + 5:02d}"
    if ft in ("TIMESTAMP", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"):
        return f"2026-{min(idx + 2, 9):02d}-{(idx % 20) + 5:02d} 11:15:00"
    if ft == "TIMESTAMP WITH TIME ZONE":
        return f"2026-{min(idx + 2, 9):02d}-{(idx % 20) + 5:02d} 11:15:00+00:00"
    if ft == "TIME":
        return f"{(8 + idx) % 24:02d}:30:00"
    if ft == "D_JSON":
        return json.dumps({"module": spec.module, "sample_index": idx})
    if ft == "D_EMAIL":
        return f"contact{idx}@{spec.source_app.replace('_', '-')}.example"
    if ft == "D_PHONE":
        return f"+1-416-555-01{idx:02d}"
    if ft == "D_URL":
        return f"/files/{spec.source_app}/{spec.table_name.lower()}_{idx}.pdf"
    if ft == "D_STATUS":
        opts = [
            line.strip()
            for line in (col.options or "").splitlines()
            if line.strip() and not line.strip().startswith("{")
        ]
        if opts:
            return opts[(idx - 1) % len(opts)][:60]
        return "Active" if idx == 1 else "Draft"
    if ft == "D_CODE":
        return f"{spec.table_name[:12]}-{idx:02d}"
    if ft == "D_TEXT":
        label = col.label or col.orig_fieldname
        return f"{spec.orig_name} — {label} sample entry #{idx} ({spec.source_app})"
    # VARCHAR / D_SHORT_TEXT / D_TITLE / D_DOC_ID
    label = col.label or col.orig_fieldname
    return f"{spec.orig_name[:40]} {label[:35]} {idx}"[:110]


def emit_firebird_sql_script(
    sql_path: Path,
    tables_by_name: dict[str, TableSpec],
    doctype_to_table: dict[str, str],
    fks: list[ForeignKeySpec],
    rows_by_table: dict[str, list[dict[str, object]]],
) -> dict[str, int]:
    """Write complete batched Firebird 5.0 SQL build script."""
    stats = {
        "domains": len(DOMAINS),
        "sequences": 12,
        "exceptions": 4,
        "roles": 4,
        "tables": len(tables_by_name),
        "rows": 0,
        "foreign_keys": len(fks),
        "indexes": 0,
        "triggers": 0,
        "views": 0,
        "procedures_and_functions": 0,
        "packages": 1,
    }

    with sql_path.open("w", encoding="utf-8") as out:
        out.write("SET NAMES UTF8;\n")
        out.write("SET SQL DIALECT 3;\n")
        out.write("SET AUTODDL OFF;\n\n")

        # 1. Domains, Sequences, Exceptions, Roles
        out.write("/* === 1. DOMAINS, SEQUENCES, EXCEPTIONS & ROLES === */\n")
        for dname, ddef, _b in DOMAINS:
            out.write(f"CREATE DOMAIN {dname} AS {ddef};\n")
        for seq_name, start_val in (
            ("SEQ_GL_ENTRY", 1000),
            ("SEQ_STOCK_LEDGER", 1000),
            ("SEQ_SALES_ORDER", 100),
            ("SEQ_SALES_INVOICE", 100),
            ("SEQ_PURCHASE_ORDER", 100),
            ("SEQ_PURCHASE_INVOICE", 100),
            ("SEQ_PAYMENT_ENTRY", 100),
            ("SEQ_EMPLOYEE", 100),
            ("SEQ_CRM_DEAL", 100),
            ("SEQ_HD_TICKET", 2000),
            ("SEQ_LMS_ENROLLMENT", 500),
            ("SEQ_PRESS_DEPLOY", 500),
        ):
            out.write(f"CREATE SEQUENCE {seq_name} START WITH {start_val};\n")
        for ex_name, ex_msg in (
            ("EX_FRAPPE_CANCELLED_EDIT", "Cancelled documents (DOCSTATUS = 2) cannot be modified"),
            ("EX_FRAPPE_NEGATIVE_STOCK", "Stock quantity cannot become negative in strict warehouse mode"),
            ("EX_FRAPPE_UNBALANCED_GL", "General Ledger voucher debit and credit totals must balance"),
            ("EX_FRAPPE_INVALID_DOCSTATUS", "Invalid Frappe document lifecycle state transition"),
        ):
            out.write(f"CREATE EXCEPTION {ex_name} {sql_lit(ex_msg)};\n")
        for role_name in (
            "FRAPPE_SYSTEM_MANAGER",
            "FRAPPE_ACCOUNTS_MANAGER",
            "FRAPPE_HR_MANAGER",
            "FRAPPE_READ_ONLY",
        ):
            out.write(f"CREATE ROLE {role_name};\n")
        out.write("COMMIT;\n\n")

        # 2. Tables + Table Comments
        out.write("/* === 2. TABLES === */\n")
        for idx, (tname, spec) in enumerate(sorted(tables_by_name.items()), start=1):
            col_defs = []
            for col in spec.columns:
                nn = (
                    " NOT NULL"
                    if (col.not_null and "NOT NULL" not in col.fb_type)
                    else ""
                )
                col_defs.append(f"  {col.col_name} {col.fb_type}{nn}")
            pk_clause = f",\n  PRIMARY KEY ({', '.join(spec.pk_columns)})"
            out.write(f"CREATE TABLE {tname} (\n" + ",\n".join(col_defs) + pk_clause + "\n);\n")
            if spec.comment:
                out.write(f"COMMENT ON TABLE {tname} IS {sql_lit(spec.comment[:240])};\n")
            if idx % 200 == 0:
                out.write("COMMIT;\n")
        out.write("COMMIT;\n\n")

        # 3. Triggers that maintain live rollups BEFORE data insert (so DATUM_SAMPLES/LOGS populate stats live!)
        out.write("/* === 3. LIVE ROLLUP & LIFECYCLE TRIGGERS === */\n")
        si_table = doctype_to_table.get("Sales Invoice", "SALES_INVOICE")
        out.write("SET TERM ^ ;\n")
        out.write("""
CREATE TRIGGER TRG_AI_DATUM_SAMPLES FOR DATUM_SAMPLES
ACTIVE AFTER INSERT POSITION 0
AS
  DECLARE VARIABLE V_DATE DATE;
BEGIN
  V_DATE = CAST(NEW.TS AS DATE);
  UPDATE OR INSERT INTO DATUM_DAILY_INGESTION_STATS (STAT_DATE, RESOURCE_ID, METRIC_COUNT)
  VALUES (
    :V_DATE,
    NEW.RESOURCE_ID,
    COALESCE(
      (SELECT METRIC_COUNT FROM DATUM_DAILY_INGESTION_STATS
       WHERE STAT_DATE = :V_DATE AND RESOURCE_ID = NEW.RESOURCE_ID),
      0
    ) + 1
  )
  MATCHING (STAT_DATE, RESOURCE_ID);
END^

CREATE TRIGGER TRG_AI_DATUM_LOGS FOR DATUM_LOGS
ACTIVE AFTER INSERT POSITION 0
AS
  DECLARE VARIABLE V_DATE DATE;
BEGIN
  V_DATE = CAST(NEW.TS AS DATE);
  UPDATE OR INSERT INTO DATUM_DAILY_LOG_STATS (
    STAT_DATE, RESOURCE_ID, PRODUCT, SERVICE_NAME, LOG_LEVEL, LOG_COUNT
  )
  VALUES (
    :V_DATE,
    NEW.RESOURCE_ID,
    NEW.PRODUCT,
    NEW.SERVICE_NAME,
    NEW.LOG_LEVEL,
    COALESCE(
      (SELECT LOG_COUNT FROM DATUM_DAILY_LOG_STATS
       WHERE STAT_DATE = :V_DATE
         AND RESOURCE_ID = NEW.RESOURCE_ID
         AND PRODUCT = NEW.PRODUCT
         AND SERVICE_NAME = NEW.SERVICE_NAME
         AND LOG_LEVEL = NEW.LOG_LEVEL),
      0
    ) + 1
  )
  MATCHING (STAT_DATE, RESOURCE_ID, PRODUCT, SERVICE_NAME, LOG_LEVEL);
END^
""")
        if si_table in tables_by_name:
            out.write(f"""
CREATE TRIGGER TRG_BU_PROTECT_CANCELLED_SI FOR {si_table}
ACTIVE BEFORE UPDATE POSITION 0
AS
BEGIN
  IF (OLD.DOCSTATUS = 2 AND NEW.DOCSTATUS = 2) THEN
    EXCEPTION EX_FRAPPE_CANCELLED_EDIT;
  NEW.MODIFIED_TS = CURRENT_TIMESTAMP;
END^
""")
            stats["triggers"] += 1
        out.write("SET TERM ; ^\nCOMMIT;\n\n")
        stats["triggers"] += 2

        # 4. Sample Data Population across ALL ~2,950+ tables
        out.write("/* === 4. ENTERPRISE & UNIVERSAL SAMPLE DATA === */\n")
        stmt_count = 0
        for tname in sorted(rows_by_table.keys()):
            spec = tables_by_name[tname]
            valid_cols = {c.col_name for c in spec.columns}
            for row in rows_by_table[tname]:
                ordered_cols = [c.col_name for c in spec.columns if c.col_name in row and c.col_name in valid_cols]
                vals = [sql_lit(row[c]) for c in ordered_cols]
                out.write(
                    f"INSERT INTO {tname} ({', '.join(ordered_cols)}) VALUES ({', '.join(vals)});\n"
                )
                stats["rows"] += 1
                stmt_count += 1
                if stmt_count % 500 == 0:
                    out.write("COMMIT;\n")
        out.write("COMMIT;\n\n")

        # 5. Polymorphic Child Composite Indexes & Enforced Foreign Keys
        out.write("/* === 5. POLYMORPHIC INDEXES & ENFORCED FOREIGN KEYS === */\n")
        idx_count = 0
        for tname, spec in sorted(tables_by_name.items()):
            if len(spec.parent_doctypes) > 1 and "PARENT_ID" in {c.col_name for c in spec.columns}:
                ix_name = f"IX_{tname[:50]}_POLY"
                out.write(f"CREATE INDEX {ix_name} ON {tname} (PARENT_TYPE, PARENT_ID);\n")
                idx_count += 1
                if idx_count % 200 == 0:
                    out.write("COMMIT;\n")
        out.write("CREATE INDEX IX_DATUM_SAMPLES_RES_TS ON DATUM_SAMPLES (RESOURCE_ID, METRIC, TS);\n")
        out.write("CREATE INDEX IX_DATUM_LOGS_RES_TS ON DATUM_LOGS (RESOURCE_ID, PRODUCT, SERVICE_NAME, TS);\n")
        idx_count += 2
        stats["indexes"] = idx_count
        out.write("COMMIT;\n\n")

        for fk_i, fk in enumerate(fks, start=1):
            clauses = " ".join(p for p in (fk.on_update, fk.on_delete) if p)
            suffix = f" {clauses}" if clauses else ""
            out.write(
                f"ALTER TABLE {fk.source_table} ADD CONSTRAINT {fk.constraint_name} "
                f"FOREIGN KEY ({fk.source_col}) REFERENCES {fk.target_table} ({fk.target_col}){suffix};\n"
            )
            if fk_i % 150 == 0:
                out.write("COMMIT;\n")
        out.write("COMMIT;\n\n")

        # 6. Cross-Project Analytical Views, Functions, Stored Procedures & Packages
        out.write("/* === 6. ANALYTICAL VIEWS, FUNCTIONS, PROCEDURES & PACKAGES === */\n")
        cust_t = doctype_to_table.get("Customer", "CUSTOMER")
        supp_t = doctype_to_table.get("Supplier", "SUPPLIER")
        pinv_t = doctype_to_table.get("Purchase Invoice", "PURCHASE_INVOICE")
        gle_t = doctype_to_table.get("GL Entry", "GL_ENTRY")
        sle_t = doctype_to_table.get("Stock Ledger Entry", "STOCK_LEDGER_ENTRY")
        item_t = doctype_to_table.get("Item", "ITEM")
        emp_t = doctype_to_table.get("Employee", "EMPLOYEE")
        sslip_t = doctype_to_table.get("Salary Slip", "SALARY_SLIP")
        hdt_t = doctype_to_table.get("HD Ticket", "HD_TICKET")
        loan_t = doctype_to_table.get("Loan", "LOAN")
        lmsc_t = doctype_to_table.get("LMS Course", "LMS_COURSE")

        views_sql = [
            f"""CREATE OR ALTER VIEW VW_SUITE_PROJECT_SUMMARY AS
SELECT
  CATEGORY,
  COUNT(*) AS REPOSITORY_COUNT,
  SUM(DOCTYPE_COUNT) AS TOTAL_DOCTYPES,
  SUM(TABLE_COUNT) AS GENERATED_TABLES
FROM SUITE_PROJECT_CATALOG
GROUP BY CATEGORY;""",
            f"""CREATE OR ALTER VIEW VW_ERP_AR_AGING AS
SELECT
  si.DOC_NAME AS INVOICE_NO,
  si.COMPANY,
  si.CUSTOMER,
  c.CUSTOMER_NAME,
  si.POSTING_DATE,
  si.DUE_DATE,
  si.CURRENCY,
  si.GRAND_TOTAL,
  si.OUTSTANDING_AMOUNT,
  si.STATUS
FROM {si_table} si
LEFT JOIN {cust_t} c ON c.DOC_NAME = si.CUSTOMER;""",
            f"""CREATE OR ALTER VIEW VW_ERP_AP_AGING AS
SELECT
  pi.DOC_NAME AS INVOICE_NO,
  pi.COMPANY,
  pi.SUPPLIER,
  s.SUPPLIER_NAME,
  pi.POSTING_DATE,
  pi.DUE_DATE,
  pi.CURRENCY,
  pi.GRAND_TOTAL,
  pi.OUTSTANDING_AMOUNT,
  pi.STATUS
FROM {pinv_t} pi
LEFT JOIN {supp_t} s ON s.DOC_NAME = pi.SUPPLIER;""",
            f"""CREATE OR ALTER VIEW VW_ERP_GL_TRIAL_BALANCE AS
SELECT
  COMPANY,
  ACCOUNT,
  FISCAL_YEAR,
  COUNT(*) AS ENTRY_COUNT,
  SUM(COALESCE(DEBIT, 0)) AS TOTAL_DEBIT,
  SUM(COALESCE(CREDIT, 0)) AS TOTAL_CREDIT,
  SUM(COALESCE(DEBIT, 0) - COALESCE(CREDIT, 0)) AS NET_BALANCE
FROM {gle_t}
WHERE COALESCE(IS_CANCELLED, FALSE) = FALSE
GROUP BY COMPANY, ACCOUNT, FISCAL_YEAR;""",
            f"""CREATE OR ALTER VIEW VW_ERP_STOCK_VALUATION AS
SELECT
  sle.COMPANY,
  sle.WAREHOUSE,
  sle.ITEM_CODE,
  i.ITEM_NAME,
  i.ITEM_GROUP,
  SUM(COALESCE(sle.ACTUAL_QTY, 0)) AS NET_QTY,
  MAX(COALESCE(sle.VALUATION_RATE, 0)) AS LATEST_VALUATION_RATE
FROM {sle_t} sle
LEFT JOIN {item_t} i ON i.DOC_NAME = sle.ITEM_CODE
GROUP BY sle.COMPANY, sle.WAREHOUSE, sle.ITEM_CODE, i.ITEM_NAME, i.ITEM_GROUP;""",
            f"""CREATE OR ALTER VIEW VW_HRMS_PAYROLL_SUMMARY AS
SELECT
  ss.COMPANY,
  ss.DEPARTMENT,
  COUNT(DISTINCT ss.EMPLOYEE) AS EMPLOYEES_PAID,
  SUM(COALESCE(ss.GROSS_PAY, 0)) AS TOTAL_GROSS_PAY,
  SUM(COALESCE(ss.TOTAL_DEDUCTION, 0)) AS TOTAL_DEDUCTIONS,
  SUM(COALESCE(ss.NET_PAY, 0)) AS TOTAL_NET_PAY
FROM {sslip_t} ss
GROUP BY ss.COMPANY, ss.DEPARTMENT;""",
            f"""CREATE OR ALTER VIEW VW_HELPDESK_SLA_BOARD AS
SELECT
  STATUS,
  PRIORITY,
  COUNT(*) AS TICKET_COUNT
FROM {hdt_t}
GROUP BY STATUS, PRIORITY;""",
            f"""CREATE OR ALTER VIEW VW_LENDING_PORTFOLIO AS
SELECT
  COMPANY,
  APPLICANT_NAME,
  DOC_NAME AS LOAN_ID,
  LOAN_AMOUNT,
  RATE_OF_INTEREST,
  DISBURSED_AMOUNT,
  TOTAL_AMOUNT_PAID,
  STATUS
FROM {loan_t};""",
            f"""CREATE OR ALTER VIEW VW_LMS_CATALOG_METRICS AS
SELECT
  DOC_NAME AS COURSE_ID,
  TITLE,
  PUBLISHED,
  PAID_COURSE,
  COURSE_PRICE,
  ENROLLMENTS
FROM {lmsc_t};""",
            """CREATE OR ALTER VIEW VW_DATUM_DAILY_INGESTION_STATS AS
SELECT
  CAST(TS AS DATE) AS STAT_DATE,
  RESOURCE_ID,
  COUNT(*) AS METRIC_COUNT
FROM DATUM_SAMPLES
GROUP BY CAST(TS AS DATE), RESOURCE_ID;""",
            """CREATE OR ALTER VIEW VW_DATUM_DAILY_LOG_STATS AS
SELECT
  CAST(TS AS DATE) AS STAT_DATE,
  RESOURCE_ID,
  PRODUCT,
  SERVICE_NAME,
  LOG_LEVEL,
  COUNT(*) AS LOG_COUNT
FROM DATUM_LOGS
GROUP BY CAST(TS AS DATE), RESOURCE_ID, PRODUCT, SERVICE_NAME, LOG_LEVEL;""",
            """CREATE OR ALTER VIEW VW_CARGO_OVERVIEW AS
SELECT
  s.RESOURCE_ID,
  s.METRIC,
  s.SERVICE_NAME,
  MAX(s.SAMPLE_VALUE) AS LATEST_VALUE,
  MAX(s.TS) AS LAST_SEEN_AT
FROM DATUM_SAMPLES s
WHERE s.RESOURCE_ID STARTING WITH 'cargo:'
GROUP BY s.RESOURCE_ID, s.METRIC, s.SERVICE_NAME;""",
            """CREATE OR ALTER VIEW VW_CARGO_DB_QUERIES AS
WITH DELTAS AS (
  SELECT
    RESOURCE_ID,
    SERIES_KIND,
    TS,
    SAMPLE_VALUE,
    LAG(SAMPLE_VALUE) OVER (PARTITION BY RESOURCE_ID, SERIES_KIND ORDER BY TS) AS PREV_VALUE
  FROM DATUM_SAMPLES
  WHERE RESOURCE_ID STARTING WITH 'cargo:'
    AND METRIC = 'mariadb_queries_total'
)
SELECT
  RESOURCE_ID,
  SERIES_KIND,
  TS,
  SAMPLE_VALUE,
  PREV_VALUE,
  (SAMPLE_VALUE - COALESCE(PREV_VALUE, SAMPLE_VALUE)) AS QUERY_DELTA
FROM DELTAS;""",
            """CREATE OR ALTER VIEW VW_CLOUD_INFRA_FLEET AS
SELECT
  vm.VM_ID,
  vm.HOSTNAME,
  vm.DESIRED_POWER,
  vm.OBSERVED_STATUS,
  vm.VCPU_COUNT,
  vm.MEM_MIB,
  vm.IPV4_CIDR,
  COALESCE(SUM(v.SIZE_GIB), 0) AS ATTACHED_STORAGE_GIB
FROM BOAT_VIRTUAL_MACHINE vm
LEFT JOIN BOAT_VOLUME v ON v.VM_ID = vm.VM_ID
GROUP BY
  vm.VM_ID, vm.HOSTNAME, vm.DESIRED_POWER, vm.OBSERVED_STATUS,
  vm.VCPU_COUNT, vm.MEM_MIB, vm.IPV4_CIDR;""",
        ]
        for v_sql in views_sql:
            out.write(v_sql + "\n")
            stats["views"] += 1
        out.write("COMMIT;\n\n")

        # Functions, Stored Procedures & Package
        out.write("SET TERM ^ ;\n")
        out.write(f"""
CREATE OR ALTER FUNCTION FN_DOCSTATUS_LABEL(P_STATUS SMALLINT)
RETURNS VARCHAR(20)
DETERMINISTIC
AS
BEGIN
  RETURN CASE P_STATUS
    WHEN 0 THEN 'Draft'
    WHEN 1 THEN 'Submitted'
    WHEN 2 THEN 'Cancelled'
    ELSE 'Unknown'
  END;
END^

CREATE OR ALTER FUNCTION FN_FISCAL_QUARTER(P_DATE DATE)
RETURNS VARCHAR(6)
DETERMINISTIC
AS
  DECLARE VARIABLE V_MONTH SMALLINT;
BEGIN
  IF (P_DATE IS NULL) THEN RETURN NULL;
  V_MONTH = EXTRACT(MONTH FROM P_DATE);
  RETURN 'Q' || CAST(((V_MONTH - 1) / 3) + 1 AS VARCHAR(2));
END^

CREATE OR ALTER PROCEDURE SP_COMPANY_FINANCIAL_SNAPSHOT(
  P_COMPANY VARCHAR(80)
)
RETURNS (
  COMPANY_NAME VARCHAR(80),
  BILLED_REVENUE NUMERIC(18, 4),
  OPEN_RECEIVABLES NUMERIC(18, 4),
  OPEN_PAYABLES NUMERIC(18, 4),
  ACTIVE_EMPLOYEES INTEGER
)
AS
BEGIN
  COMPANY_NAME = :P_COMPANY;
  SELECT
    COALESCE(SUM(GRAND_TOTAL), 0),
    COALESCE(SUM(OUTSTANDING_AMOUNT), 0)
  FROM {si_table}
  WHERE COMPANY = :P_COMPANY AND DOCSTATUS = 1
  INTO :BILLED_REVENUE, :OPEN_RECEIVABLES;

  SELECT COALESCE(SUM(OUTSTANDING_AMOUNT), 0)
  FROM {pinv_t}
  WHERE COMPANY = :P_COMPANY AND DOCSTATUS = 1
  INTO :OPEN_PAYABLES;

  SELECT COUNT(*)
  FROM {emp_t}
  WHERE COMPANY = :P_COMPANY AND STATUS = 'Active'
  INTO :ACTIVE_EMPLOYEES;

  SUSPEND;
END^

CREATE OR ALTER PACKAGE PKG_FRAPPE_SUITE
AS
BEGIN
  FUNCTION CUSTOMER_OUTSTANDING(P_CUSTOMER VARCHAR(80)) RETURNS NUMERIC(18, 4);
  FUNCTION ACCOUNT_NET_BALANCE(P_ACCOUNT VARCHAR(80)) RETURNS NUMERIC(18, 4);
END^

RECREATE PACKAGE BODY PKG_FRAPPE_SUITE
AS
BEGIN
  FUNCTION CUSTOMER_OUTSTANDING(P_CUSTOMER VARCHAR(80)) RETURNS NUMERIC(18, 4)
  AS
    DECLARE VARIABLE V_TOTAL NUMERIC(18, 4);
  BEGIN
    SELECT COALESCE(SUM(OUTSTANDING_AMOUNT), 0)
    FROM {si_table}
    WHERE CUSTOMER = :P_CUSTOMER AND DOCSTATUS = 1
    INTO :V_TOTAL;
    RETURN V_TOTAL;
  END

  FUNCTION ACCOUNT_NET_BALANCE(P_ACCOUNT VARCHAR(80)) RETURNS NUMERIC(18, 4)
  AS
    DECLARE VARIABLE V_BAL NUMERIC(18, 4);
  BEGIN
    SELECT COALESCE(SUM(COALESCE(DEBIT, 0) - COALESCE(CREDIT, 0)), 0)
    FROM {gle_t}
    WHERE ACCOUNT = :P_ACCOUNT AND COALESCE(IS_CANCELLED, FALSE) = FALSE
    INTO :V_BAL;
    RETURN V_BAL;
  END
END^
""")
        out.write("SET TERM ; ^\nCOMMIT;\n")
        stats["procedures_and_functions"] = 3

    return stats


def create_and_load_firebird_database(
    *,
    sql_path: Path,
    db_path: str,
    host: str,
    port: int,
    user: str,
    password: str,
    container: str,
    drop_existing: bool,
) -> dict[str, object]:
    """Create 32 KB UTF8 Firebird 5.0 database and execute batched SQL script via container isql."""
    from firebird.driver import connect, create_database, driver_config

    dsn = f"{host}/{port}:{db_path}"
    if drop_existing:
        try:
            existing = connect(dsn, user=user, password=password)
            existing.drop_database()
        except Exception as exc:
            msg = str(exc).lower()
            if "no such file" not in msg and "not defined" not in msg:
                raise

    cfg_name = f"frappe_suite_{uuid.uuid4().hex[:8]}"
    cfg = driver_config.register_database(cfg_name)
    cfg.database.value = dsn
    cfg.user.value = user
    cfg.password.value = password
    cfg.page_size.value = 32768
    cfg.charset.value = "UTF8"
    conn = create_database(cfg_name, overwrite=True)
    conn.close()

    # Temporarily disable synchronous page fsyncs during bulk build, then restore sync mode.
    subprocess.run(
        [
            "docker", "exec", container,
            "/opt/firebird/bin/gfix",
            "-write", "async",
            "-user", user,
            "-password", password,
            db_path,
        ],
        check=True,
    )

    # Stream SQL into container's native isql for fast local execution without TCP round-trips per row.
    container_tmp = "/tmp/_frappe_suite_build.sql"
    t0 = time.monotonic()
    subprocess.run(
        ["docker", "cp", str(sql_path), f"{container}:{container_tmp}"],
        check=True,
    )
    try:
        proc = subprocess.run(
            [
                "docker", "exec", container,
                "/opt/firebird/bin/isql",
                "-q",
                "-bail",
                "-u", user,
                "-p", password,
                "-ch", "UTF8",
                "-i", container_tmp,
                db_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"isql failed (exit {proc.returncode}):\n"
                f"STDOUT:\n{proc.stdout[-2000:]}\nSTDERR:\n{proc.stderr[-2000:]}"
            )
    finally:
        subprocess.run(
            ["docker", "exec", container, "rm", "-f", container_tmp],
            check=False,
        )
    subprocess.run(
        [
            "docker", "exec", container,
            "/opt/firebird/bin/gfix",
            "-write", "sync",
            "-user", user,
            "-password", password,
            db_path,
        ],
        check=True,
    )
    elapsed = round(time.monotonic() - t0, 2)

    # Live verification over TCP using firebird.driver
    vconn = connect(dsn, user=user, password=password, charset="UTF8")
    try:
        cur = vconn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM RDB$RELATIONS "
            "WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 AND RDB$VIEW_BLR IS NULL"
        )
        user_tables = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM RDB$RELATIONS "
            "WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 AND RDB$VIEW_BLR IS NOT NULL"
        )
        user_views = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM RDB$RELATION_CONSTRAINTS "
            "WHERE RDB$CONSTRAINT_TYPE = 'FOREIGN KEY'"
        )
        fk_count = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM RDB$FIELDS "
            "WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 AND RDB$FIELD_NAME NOT STARTING WITH 'RDB$'"
        )
        domain_count = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM RDB$GENERATORS WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0"
        )
        seq_count = cur.fetchone()[0]
        cur.execute("SELECT * FROM SP_COMPANY_FINANCIAL_SNAPSHOT('Maple Tech Manufacturing')")
        fin_snapshot = cur.fetchone()
        cur.execute("SELECT PKG_FRAPPE_SUITE.CUSTOMER_OUTSTANDING('CUST-0002') FROM RDB$DATABASE")
        cust2_out = cur.fetchone()[0]
        cur.execute("SELECT SUM(METRIC_COUNT) FROM DATUM_DAILY_INGESTION_STATS")
        datum_rollup_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM SUITE_PROJECT_CATALOG")
        cataloged_repos = cur.fetchone()[0]
    finally:
        vconn.close()

    return {
        "dsn": dsn,
        "load_seconds": elapsed,
        "user_tables": user_tables,
        "user_views": user_views,
        "foreign_keys": fk_count,
        "domains": domain_count,
        "sequences": seq_count,
        "cataloged_donor_repos": cataloged_repos,
        "maple_tech_snapshot": [
            str(x) if x is not None else None for x in (fin_snapshot or ())
        ],
        "cust_0002_outstanding": str(cust2_out),
        "datum_trigger_rollup_count": int(datum_rollup_total or 0),
    }


def register_in_scratchrobin_config(
    config_db: Path, db_path: str
) -> dict[str, object]:
    """Idempotently register frappe_suite.fdb under existing Firebird server endpoint."""
    if not config_db.is_file():
        return {"registered": False, "reason": f"{config_db} not found"}

    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup_path = config_db.with_name(f"{config_db.name}.frappe-suite-{timestamp}.bak")
    with sqlite3.connect(config_db) as src, sqlite3.connect(backup_path) as dst:
        src.backup(dst)

    display_name = Path(db_path).name
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

    with sqlite3.connect(config_db) as conn:
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT ep.id, s.id, s.name
            FROM cde_endpoint ep
            JOIN server s ON s.id = ep.legacy_server_id
            WHERE ep.experience_family = 'firebird' OR s.maintenance_db LIKE '%.fdb%'
            ORDER BY s.id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return {"registered": False, "reason": "No Firebird endpoint found in cdeadmin.db"}
        endpoint_id, server_id, server_name = row

        existing = cur.execute(
            """
            SELECT id FROM cde_endpoint_database_target
            WHERE endpoint_id = ? AND database = ?
            """,
            (endpoint_id, db_path),
        ).fetchone()

        if existing:
            target_id = existing[0]
            cur.execute(
                """
                UPDATE cde_endpoint_database_target
                SET display_name = ?, active = 1, updated_at = ?
                WHERE id = ?
                """,
                (display_name, now_str, target_id),
            )
            action = "updated"
        else:
            target_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO cde_endpoint_database_target (
                  id, endpoint_id, display_name, database,
                  configuration, active, created_at, updated_at,
                  registration_user, registration_password, registration_credentials
                ) VALUES (?, ?, ?, ?, '{}', 1, ?, ?, NULL, NULL, 0)
                """,
                (target_id, endpoint_id, display_name, db_path, now_str, now_str),
            )
            action = "inserted"
        conn.commit()

    return {
        "registered": True,
        "action": action,
        "server_id": server_id,
        "server_name": server_name,
        "endpoint_id": endpoint_id,
        "target_id": target_id,
        "database_name": db_path,
        "backup": str(backup_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-root", type=Path, default=DEFAULT_DONOR_ROOT)
    parser.add_argument("--dialect-json", type=Path, default=DEFAULT_DIALECT_JSON)
    parser.add_argument("--database-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--sql-output", type=Path, default=None)
    parser.add_argument(
        "--register-config-db",
        type=Path,
        default=None,
        help="Optional ScratchRobin cdeadmin.db path to register frappe_suite.fdb",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--drop-existing", action="store_true")
    args = parser.parse_args()

    reserved = load_reserved_words(args.dialect_json)
    project_catalog, tables_by_name, doctype_to_table, fks = discover_and_compile_schemas(
        args.donor_root, reserved
    )
    rows_by_table, _pk_pool = build_curated_and_universal_rows(
        project_catalog, tables_by_name, doctype_to_table, fks
    )

    if args.sql_output:
        sql_path = args.sql_output
        cleanup_sql = False
    else:
        tmp = tempfile.NamedTemporaryFile(
            prefix="frappe_firebird_suite_", suffix=".sql", delete=False
        )
        tmp.close()
        sql_path = Path(tmp.name)
        cleanup_sql = True

    try:
        emit_stats = emit_firebird_sql_script(
            sql_path, tables_by_name, doctype_to_table, fks, rows_by_table
        )
        summary: dict[str, object] = {
            "donor_repositories": len(project_catalog),
            "compiled": emit_stats,
        }
        if not args.dry_run:
            live_stats = create_and_load_firebird_database(
                sql_path=sql_path,
                db_path=args.database_path,
                host=args.host,
                port=args.port,
                user=args.user,
                password=args.password,
                container=args.container,
                drop_existing=args.drop_existing,
            )
            summary["live_firebird"] = live_stats
            if args.register_config_db:
                summary["scratchrobin_registration"] = register_in_scratchrobin_config(
                    args.register_config_db, args.database_path
                )
        print(json.dumps(summary, indent=2))
    finally:
        if cleanup_sql and sql_path.exists():
            sql_path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
