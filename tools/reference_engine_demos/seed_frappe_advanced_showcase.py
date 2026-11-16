#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Seed Pillars 1, 2, 4, and 5 of the Frappe Enterprise Suite Showcase:

1. Dimensional Cubes (cube.dimensional@1 in designs.db + active runtime
   cde_semantic_model & cde_semantic_model_revision in cdeadmin.db).
2. Donor-derived BI Questions, 12 multi-tab Composed BI Dashboards
   (panels.composed@1), reviewed bi_outward_effect switches, runtime
   cde_bi_alert threshold alerts, and cde_bi_embed signed embeds.
3. Multi-version directed save-point lifecycles (v1 Accepted -> v2 In Review ->
   v3 Draft), acceptance gate records, cross-design design_dependency edges for
   Where-Used, and cross-engine target_deployment matrix entries.
4. Validated project assets across all 13 CDEadmin platform modules
   (Schema Compare, Migration, ETL, CDC, Replication, Lineage, Data Quality,
   Data Contracts, Distributed Tracing, API Designer, ML/Vector, Governed AI
   Assistant, AI Interface 10-profile suite, and Discovery Intelligence).
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import glob
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from types import ModuleType
import uuid


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
WEB_DIR = REPO_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

if "pgadmin" not in sys.modules:
    pkg = ModuleType("pgadmin")
    pkg.__path__ = [str(WEB_DIR / "pgadmin")]
    sys.modules["pgadmin"] = pkg

from pgadmin.cdeadmin.design_store import (  # noqa: E402
    dashboard_to_ddn,
    default_dashboard_model,
    default_question_model,
    question_to_ddn,
    semantic_model_to_ddn,
    uuid7,
    validate_bi_dashboard,
)
from pgadmin.cdeadmin.semantic_models import (  # noqa: E402
    public_model,
    validate_model,
)
from pgadmin.cdeadmin.workspace.ai_interface_assets import (  # noqa: E402
    AI_INTERFACE_ASSET_TYPES,
)
from pgadmin.cdeadmin.workspace.assets import (  # noqa: E402
    validate_asset_request,
)


DEFAULT_DONOR_ROOT = Path("/home/dcalford/Sandbox/donor_release_acquisition/frappe")
DEFAULT_CDEADMIN_DB = Path("/home/dcalford/.cdeadmin/cdeadmin.db")
DEFAULT_DESIGNS_DB = Path("/home/dcalford/.cdeadmin/designs.db")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resource_ref(
    provider: str,
    endpoint_id: str,
    target_id: str,
    kind: str,
    identity: str,
    *,
    role: str = "referenced",
) -> dict[str, object]:
    return {
        "schema": "cdeadmin.resource-ref.v1",
        "provider": provider,
        "providerId": provider,
        "connection": endpoint_id,
        "scope": target_id,
        "kind": kind,
        "nativeIdentity": identity,
        "resource_id": f"{kind}:{identity}",
        "bindingRole": role,
        "canonical": f"cde-resource://{provider}/{endpoint_id}/{target_id}/{kind}/{identity}",
    }


def _lookup_endpoints(cconn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    rows = cconn.execute(
        """
        SELECT ep.experience_family, ep.id, t.id, t.database
        FROM cde_endpoint ep
        JOIN cde_endpoint_database_target t ON t.endpoint_id = ep.id
        ORDER BY t.active DESC, t.updated_at DESC
        """
    ).fetchall()
    out: dict[str, dict[str, str]] = {}
    for fam, ep_id, tgt_id, db_path in rows:
        if fam == "firebird" and "frappe_suite.fdb" in db_path:
            out["firebird"] = {
                "endpoint_id": ep_id,
                "target_id": tgt_id,
                "database": db_path,
            }
        elif fam == "sqlite" and "frappe_books_edge" in db_path:
            out["sqlite"] = {
                "endpoint_id": ep_id,
                "target_id": tgt_id,
                "database": db_path,
            }
        elif fam == "duckdb" and "frappe_lakehouse" in db_path:
            out["duckdb"] = {
                "endpoint_id": ep_id,
                "target_id": tgt_id,
                "database": db_path,
            }
    if "firebird" not in out:
        raise RuntimeError("frappe_suite.fdb target was not found in cdeadmin.db")
    return out


def _project_uuid_map(cconn: sqlite3.Connection) -> dict[str, str]:
    return {
        r[0]: r[1]
        for r in cconn.execute("SELECT project_key, id FROM cde_project").fetchall()
    }


def _upsert_validated_asset(
    cconn: sqlite3.Connection,
    *,
    project_key: str,
    project_uuid: str,
    user_id: int,
    asset_key: str,
    request_payload: dict[str, object],
    now_sql: str,
) -> str:
    """Validate payload through CDEadmin's authoritative server gate, then upsert."""
    validated = validate_asset_request(request_payload, project_key, asset_key)
    path = validated["path"]

    prior_by_path = cconn.execute(
        "SELECT id, asset_key FROM cde_project_asset WHERE project_id = ? AND path = ?",
        (project_uuid, path),
    ).fetchone()
    if prior_by_path and prior_by_path[1] != asset_key:
        cconn.execute("DELETE FROM cde_project_asset_revision WHERE asset_id = ?", (prior_by_path[0],))
        cconn.execute("DELETE FROM cde_project_asset WHERE id = ?", (prior_by_path[0],))

    existing = cconn.execute(
        "SELECT id FROM cde_project_asset WHERE project_id = ? AND asset_key = ?",
        (project_uuid, asset_key),
    ).fetchone()
    if existing:
        aid = existing[0]
        cconn.execute("DELETE FROM cde_project_asset_revision WHERE asset_id = ?", (aid,))
        cconn.execute(
            """
            UPDATE cde_project_asset
            SET asset_type = ?, name = ?, path = ?, schema_name = ?, schema_version = ?,
                version = 1, content = ?, asset_metadata = ?,
                dependency_references = ?, resource_bindings = ?,
                permission_reference = ?, classification_reference = ?,
                source_control_eligible = ?, editor_capable = ?, viewer_capable = ?,
                validation_state = ?, validation_details = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                validated["asset_type"],
                validated["name"],
                validated["path"],
                validated["schema_name"],
                validated["schema_version"],
                validated["content"],
                validated["asset_metadata"],
                validated["dependency_references"],
                validated["resource_bindings"],
                validated["permission_reference"],
                validated["classification_reference"],
                1 if validated["source_control_eligible"] else 0,
                1 if validated["editor_capable"] else 0,
                1 if validated["viewer_capable"] else 0,
                validated["validation_state"],
                validated["validation_details"],
                now_sql,
                aid,
            ),
        )
    else:
        aid = str(uuid.uuid4())
        cconn.execute(
            """
            INSERT INTO cde_project_asset (
              id, project_id, user_id, asset_key, asset_type, name, path,
              schema_name, schema_version, version, content, asset_metadata,
              dependency_references, resource_bindings, permission_reference,
              classification_reference, source_control_eligible,
              editor_capable, viewer_capable, validation_state,
              validation_details, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                project_uuid,
                user_id,
                asset_key,
                validated["asset_type"],
                validated["name"],
                validated["path"],
                validated["schema_name"],
                validated["schema_version"],
                validated["content"],
                validated["asset_metadata"],
                validated["dependency_references"],
                validated["resource_bindings"],
                validated["permission_reference"],
                validated["classification_reference"],
                1 if validated["source_control_eligible"] else 0,
                1 if validated["editor_capable"] else 0,
                1 if validated["viewer_capable"] else 0,
                validated["validation_state"],
                validated["validation_details"],
                now_sql,
                now_sql,
            ),
        )
    cconn.execute(
        """
        INSERT INTO cde_project_asset_revision (
          id, asset_id, user_id, version, schema_name, schema_version,
          content, asset_metadata, dependency_references, resource_bindings,
          validation_state, validation_details, created_at
        ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            aid,
            user_id,
            validated["schema_name"],
            validated["schema_version"],
            validated["content"],
            validated["asset_metadata"],
            validated["dependency_references"],
            validated["resource_bindings"],
            validated["validation_state"],
            validated["validation_details"],
            now_sql,
        ),
    )
    return aid


def _upsert_design_with_versions(
    dconn: sqlite3.Connection,
    *,
    project_key: str,
    design_key: str,
    kind: str,
    title: str,
    versions: list[tuple[int, int | None, str, str, str]],
    active_version: int | None,
    user_id: int,
    now_iso: str,
    approval_ref: str | None = None,
) -> str:
    """Upsert a design in designs.db with 1..N directed save-point versions.

    Each entry in ``versions`` is ``(ver_no, base_ver, status, ddn_text, note)``.
    """
    existing = dconn.execute(
        "SELECT id FROM design WHERE project_id = ? AND key = ?",
        (project_key, design_key),
    ).fetchone()
    head_ver = max(v[0] for v in versions)
    if existing:
        did = existing[0]
        dconn.execute("DELETE FROM binding WHERE design_id = ?", (did,))
        dconn.execute("DELETE FROM element WHERE design_id = ?", (did,))
        dconn.execute("DELETE FROM acceptance WHERE design_id = ?", (did,))
        dconn.execute("DELETE FROM design_dependency WHERE design_id = ?", (did,))
        dconn.execute("DELETE FROM target_deployment WHERE design_id = ?", (did,))
        dconn.execute("DELETE FROM design_version WHERE design_id = ?", (did,))
        dconn.execute(
            """
            UPDATE design
            SET kind = ?, title = ?, active_version = ?, head_version = ?, updated_at = ?
            WHERE id = ?
            """,
            (kind, title[:120], active_version, head_ver, now_iso, did),
        )
    else:
        did = uuid7()
        dconn.execute(
            """
            INSERT INTO design (
              id, kind, project_id, key, title,
              active_version, head_version,
              created_by, created_at, updated_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did,
                kind,
                project_key,
                design_key,
                title[:120],
                active_version,
                head_ver,
                user_id,
                now_iso,
                user_id,
                now_iso,
            ),
        )

    for ver_no, base_ver, status, ddn_text, note in versions:
        if isinstance(ddn_text, tuple):
            ddn_text = ddn_text[0]
        dconn.execute(
            """
            INSERT INTO design_version (
              design_id, version, base_version, status,
              ddn_text, ddn_sha256, dialect_version, note,
              actor_id, saved_at, origin, loss_report
            ) VALUES (?, ?, ?, ?, ?, ?, 'ddn-next-1', ?, ?, ?, 'local', NULL)
            """,
            (did, ver_no, base_ver, status, ddn_text, _sha256(ddn_text), note, user_id, now_iso),
        )
        if status == "accepted":
            dconn.execute(
                """
                INSERT INTO acceptance (
                  design_id, version, accepted_by, accepted_at, approval_ref
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    did,
                    ver_no,
                    user_id,
                    now_iso,
                    approval_ref or f"git:refs/reviews/{design_key}/v{ver_no}",
                ),
            )
    return did


def seed_pillar_1_cubes(
    dconn: sqlite3.Connection,
    cconn: sqlite3.Connection,
    *,
    projects_by_key: dict[str, str],
    endpoints: dict[str, dict[str, str]],
    user_id: int,
    now_iso: str,
    now_sql: str,
) -> dict[str, str]:
    """Seed 6 rich Dimensional Cubes in designs.db + active cde_semantic_model runtime."""
    fb_ep = endpoints["firebird"]["endpoint_id"]
    fb_tgt = endpoints["firebird"]["target_id"]

    cube_specs = [
        {
            "project_key": "erpnext-acc-general-ledger",
            "design_key": "cube-financial-general-ledger",
            "title": "Financial General Ledger Star Cube",
            "model": {
                "name": "Financial General Ledger Star Cube",
                "description": "Balanced multi-company General Ledger cube with role-playing posting/transaction dates and CoA hierarchy.",
                "semantic_family": "relational",
                "sources": [
                    {
                        "id": "gl_entry",
                        "resource_id": "table:GL_ENTRY",
                        "relation": ["GL_ENTRY"],
                        "alias": "gl_entry",
                        "source_kind": "table",
                        "classification": "fact",
                        "grain": [{"source_id": "gl_entry", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "account",
                        "resource_id": "table:ACCOUNT",
                        "relation": ["ACCOUNT"],
                        "alias": "account",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "account", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "company",
                        "resource_id": "table:COMPANY",
                        "relation": ["COMPANY"],
                        "alias": "company",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "company", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "cost_center",
                        "resource_id": "table:COST_CENTER",
                        "relation": ["COST_CENTER"],
                        "alias": "cost_center",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "cost_center", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "fiscal_year",
                        "resource_id": "table:FISCAL_YEAR",
                        "relation": ["FISCAL_YEAR"],
                        "alias": "fiscal_year",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "fiscal_year", "field": "DOC_NAME"}],
                    },
                ],
                "joins": [
                    {
                        "id": "gl_account",
                        "left_source": "gl_entry",
                        "right_source": "account",
                        "join_type": "inner",
                        "cardinality": "many-to-one",
                        "active": True,
                        "predicates": [{
                            "left": {"source_id": "gl_entry", "field": "ACCOUNT"},
                            "right": {"source_id": "account", "field": "DOC_NAME"},
                            "operator": "eq",
                        }],
                    },
                    {
                        "id": "gl_company",
                        "left_source": "gl_entry",
                        "right_source": "company",
                        "join_type": "inner",
                        "cardinality": "many-to-one",
                        "active": True,
                        "predicates": [{
                            "left": {"source_id": "gl_entry", "field": "COMPANY"},
                            "right": {"source_id": "company", "field": "DOC_NAME"},
                            "operator": "eq",
                        }],
                    },
                    {
                        "id": "gl_cost_center",
                        "left_source": "gl_entry",
                        "right_source": "cost_center",
                        "join_type": "left",
                        "cardinality": "many-to-one",
                        "active": True,
                        "predicates": [{
                            "left": {"source_id": "gl_entry", "field": "COST_CENTER"},
                            "right": {"source_id": "cost_center", "field": "DOC_NAME"},
                            "operator": "eq",
                        }],
                    },
                    {
                        "id": "gl_fiscal_year",
                        "left_source": "gl_entry",
                        "right_source": "fiscal_year",
                        "join_type": "left",
                        "cardinality": "many-to-one",
                        "active": True,
                        "predicates": [{
                            "left": {"source_id": "gl_entry", "field": "FISCAL_YEAR"},
                            "right": {"source_id": "fiscal_year", "field": "DOC_NAME"},
                            "operator": "eq",
                        }],
                    },
                ],
                "dimensions": [
                    {
                        "id": "account_dim",
                        "name": "Chart of Accounts",
                        "field": {"source_id": "account", "field": "DOC_NAME"},
                        "key_field": {"source_id": "account", "field": "DOC_NAME"},
                        "name_field": {"source_id": "account", "field": "ACCOUNT_NAME"},
                        "sort_field": {"source_id": "account", "field": "ACCOUNT_NAME"},
                        "join_id": "gl_account",
                        "attributes": [
                            {"id": "root_type", "name": "Root Type", "field": {"source_id": "account", "field": "ROOT_TYPE"}},
                            {"id": "report_type", "name": "Financial Statement", "field": {"source_id": "account", "field": "REPORT_TYPE"}},
                            {"id": "account_type", "name": "Account Category", "field": {"source_id": "account", "field": "ACCOUNT_TYPE"}},
                        ],
                        "hierarchies": [{
                            "id": "coa_hierarchy",
                            "name": "Statement -> Root -> Account",
                            "levels": [
                                {"id": "lvl_stmt", "name": "Statement", "field": {"source_id": "account", "field": "REPORT_TYPE"}},
                                {"id": "lvl_root", "name": "Root Type", "field": {"source_id": "account", "field": "ROOT_TYPE"}},
                                {"id": "lvl_acct", "name": "Account", "field": {"source_id": "account", "field": "ACCOUNT_NAME"}},
                            ],
                        }],
                    },
                    {
                        "id": "company_dim",
                        "name": "Legal Entity",
                        "field": {"source_id": "company", "field": "DOC_NAME"},
                        "key_field": {"source_id": "company", "field": "DOC_NAME"},
                        "name_field": {"source_id": "company", "field": "COMPANY_NAME"},
                        "join_id": "gl_company",
                        "attributes": [
                            {"id": "company_domain", "name": "Industry Domain", "field": {"source_id": "company", "field": "DOMAIN"}},
                            {"id": "base_currency", "name": "Base Currency", "field": {"source_id": "company", "field": "DEFAULT_CURRENCY"}},
                        ],
                    },
                    {
                        "id": "cost_center_dim",
                        "name": "Cost Center",
                        "field": {"source_id": "cost_center", "field": "DOC_NAME"},
                        "join_id": "gl_cost_center",
                    },
                    {
                        "id": "posting_date",
                        "name": "Posting Date",
                        "field": {"source_id": "gl_entry", "field": "POSTING_DATE"},
                        "is_time": True,
                        "time_role": "fiscal-time",
                        "active": True,
                    },
                    {
                        "id": "transaction_date",
                        "name": "Transaction Date (Role-Playing)",
                        "field": {"source_id": "gl_entry", "field": "TRANSACTION_DATE"},
                        "is_time": True,
                        "time_role": "event-time",
                        "role_of": "posting_date",
                        "active": False,
                    },
                ],
                "measures": [
                    {
                        "id": "total_debit",
                        "name": "Total Debit",
                        "aggregation": "sum",
                        "field": {"source_id": "gl_entry", "field": "DEBIT"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_gl",
                    },
                    {
                        "id": "total_credit",
                        "name": "Total Credit",
                        "aggregation": "sum",
                        "field": {"source_id": "gl_entry", "field": "CREDIT"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_gl",
                    },
                    {
                        "id": "sales_invoice_credit",
                        "name": "Billed Invoice Credit",
                        "aggregation": "sum",
                        "field": {"source_id": "gl_entry", "field": "CREDIT"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_gl",
                        "filters": [{
                            "field": {"source_id": "gl_entry", "field": "VOUCHER_TYPE"},
                            "operator": "eq",
                            "value": "Sales Invoice",
                        }],
                    },
                    {
                        "id": "gl_line_count",
                        "name": "GL Posting Lines",
                        "aggregation": "count",
                        "field": None,
                        "format": "#,##0",
                        "measure_group_id": "mg_gl",
                    },
                ],
                "measure_groups": [{
                    "id": "mg_gl",
                    "name": "General Ledger Postings",
                    "fact_source": "gl_entry",
                    "measures": ["total_debit", "total_credit", "sales_invoice_credit", "gl_line_count"],
                    "dimension_usage": [
                        {"dimension_id": "account_dim", "relationship_kind": "regular", "join_id": "gl_account", "active": True},
                        {"dimension_id": "company_dim", "relationship_kind": "regular", "join_id": "gl_company", "active": True},
                        {"dimension_id": "cost_center_dim", "relationship_kind": "regular", "join_id": "gl_cost_center", "active": True},
                        {"dimension_id": "posting_date", "relationship_kind": "fact", "active": True},
                        {"dimension_id": "transaction_date", "relationship_kind": "fact", "active": False},
                    ],
                }],
                "materializations": [{
                    "id": "agg_gl_monthly_coa",
                    "name": "Monthly CoA Trial Balance Aggregate",
                    "strategy": "aggregate_table",
                    "enabled": True,
                    "measure_group_id": "mg_gl",
                    "grain_dimensions": ["company_dim", "account_dim", "posting_date"],
                    "measures": ["total_debit", "total_credit", "gl_line_count"],
                    "target_relation": ["MART_GL_MONTHLY"],
                    "partition_grain": "month",
                    "refresh_policy": "on_accept_review",
                }],
            },
        },
        {
            "project_key": "erpnext-selling-orders",
            "design_key": "cube-order-to-cash-revenue",
            "title": "Order-to-Cash Commercial Revenue Cube",
            "model": {
                "name": "Order-to-Cash Commercial Revenue Cube",
                "description": "Commercial billing, net revenue, and open receivables across territories and customer segments.",
                "semantic_family": "relational",
                "sources": [
                    {
                        "id": "sales_invoice",
                        "resource_id": "table:SALES_INVOICE",
                        "relation": ["SALES_INVOICE"],
                        "alias": "sales_invoice",
                        "source_kind": "table",
                        "classification": "fact",
                        "grain": [{"source_id": "sales_invoice", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "customer",
                        "resource_id": "table:CUSTOMER",
                        "relation": ["CUSTOMER"],
                        "alias": "customer",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "customer", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "company",
                        "resource_id": "table:COMPANY",
                        "relation": ["COMPANY"],
                        "alias": "company",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "company", "field": "DOC_NAME"}],
                    },
                ],
                "joins": [
                    {
                        "id": "sinv_customer",
                        "left_source": "sales_invoice",
                        "right_source": "customer",
                        "join_type": "inner",
                        "cardinality": "many-to-one",
                        "active": True,
                        "predicates": [{
                            "left": {"source_id": "sales_invoice", "field": "CUSTOMER"},
                            "right": {"source_id": "customer", "field": "DOC_NAME"},
                            "operator": "eq",
                        }],
                    },
                    {
                        "id": "sinv_company",
                        "left_source": "sales_invoice",
                        "right_source": "company",
                        "join_type": "inner",
                        "cardinality": "many-to-one",
                        "active": True,
                        "predicates": [{
                            "left": {"source_id": "sales_invoice", "field": "COMPANY"},
                            "right": {"source_id": "company", "field": "DOC_NAME"},
                            "operator": "eq",
                        }],
                    },
                ],
                "dimensions": [
                    {
                        "id": "customer",
                        "name": "Customer",
                        "field": {"source_id": "customer", "field": "DOC_NAME"},
                        "key_field": {"source_id": "customer", "field": "DOC_NAME"},
                        "name_field": {"source_id": "customer", "field": "CUSTOMER_NAME"},
                        "join_id": "sinv_customer",
                        "attributes": [
                            {"id": "cust_group", "name": "Segment", "field": {"source_id": "customer", "field": "CUSTOMER_GROUP"}},
                            {"id": "territory", "name": "Territory", "field": {"source_id": "customer", "field": "TERRITORY"}},
                        ],
                        "hierarchies": [{
                            "id": "commercial_geo",
                            "name": "Territory -> Segment -> Customer",
                            "levels": [
                                {"id": "lvl_terr", "name": "Territory", "field": {"source_id": "customer", "field": "TERRITORY"}},
                                {"id": "lvl_grp", "name": "Customer Group", "field": {"source_id": "customer", "field": "CUSTOMER_GROUP"}},
                                {"id": "lvl_cust", "name": "Customer", "field": {"source_id": "customer", "field": "CUSTOMER_NAME"}},
                            ],
                        }],
                    },
                    {
                        "id": "company",
                        "name": "Company",
                        "field": {"source_id": "company", "field": "DOC_NAME"},
                        "join_id": "sinv_company",
                    },
                    {
                        "id": "invoice_date",
                        "name": "Invoice Posting Date",
                        "field": {"source_id": "sales_invoice", "field": "POSTING_DATE"},
                        "is_time": True,
                        "time_role": "calendar-time",
                        "active": True,
                    },
                    {
                        "id": "due_date",
                        "name": "Payment Due Date",
                        "field": {"source_id": "sales_invoice", "field": "DUE_DATE"},
                        "is_time": True,
                        "time_role": "valid-time",
                        "role_of": "invoice_date",
                        "active": False,
                    },
                ],
                "measures": [
                    {
                        "id": "net_revenue",
                        "name": "Net Revenue",
                        "aggregation": "sum",
                        "field": {"source_id": "sales_invoice", "field": "NET_TOTAL"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_sinv",
                    },
                    {
                        "id": "gross_billed",
                        "name": "Gross Billed Total",
                        "aggregation": "sum",
                        "field": {"source_id": "sales_invoice", "field": "GRAND_TOTAL"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_sinv",
                    },
                    {
                        "id": "open_ar",
                        "name": "Open Receivables",
                        "aggregation": "sum",
                        "field": {"source_id": "sales_invoice", "field": "OUTSTANDING_AMOUNT"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_sinv",
                    },
                    {
                        "id": "unpaid_invoice_count",
                        "name": "Unpaid Invoices",
                        "aggregation": "count",
                        "field": None,
                        "format": "#,##0",
                        "measure_group_id": "mg_sinv",
                        "filters": [{
                            "field": {"source_id": "sales_invoice", "field": "STATUS"},
                            "operator": "eq",
                            "value": "Unpaid",
                        }],
                    },
                ],
                "measure_groups": [{
                    "id": "mg_sinv",
                    "name": "Sales Billing Facts",
                    "fact_source": "sales_invoice",
                    "measures": ["net_revenue", "gross_billed", "open_ar", "unpaid_invoice_count"],
                    "dimension_usage": [
                        {"dimension_id": "customer", "relationship_kind": "regular", "join_id": "sinv_customer", "active": True},
                        {"dimension_id": "company", "relationship_kind": "regular", "join_id": "sinv_company", "active": True},
                        {"dimension_id": "invoice_date", "relationship_kind": "fact", "active": True},
                        {"dimension_id": "due_date", "relationship_kind": "fact", "active": False},
                    ],
                }],
                "materializations": [{
                    "id": "agg_rev_cohorts",
                    "name": "Monthly Customer Segment Revenue Mart",
                    "strategy": "aggregate_table",
                    "enabled": True,
                    "measure_group_id": "mg_sinv",
                    "grain_dimensions": ["company", "customer", "invoice_date"],
                    "measures": ["net_revenue", "gross_billed", "open_ar"],
                    "target_relation": ["MART_REVENUE_COHORTS"],
                    "partition_grain": "month",
                    "refresh_policy": "on_accept_review",
                }],
            },
        },
        {
            "project_key": "erpnext-buying-procurement",
            "design_key": "cube-procure-to-pay-spend",
            "title": "Procure-to-Pay Supplier Spend Cube",
            "model": {
                "name": "Procure-to-Pay Supplier Spend Cube",
                "description": "Direct and indirect procurement spend, AP liability, and supplier group concentration.",
                "semantic_family": "relational",
                "sources": [
                    {
                        "id": "purchase_invoice",
                        "resource_id": "table:PURCHASE_INVOICE",
                        "relation": ["PURCHASE_INVOICE"],
                        "alias": "purchase_invoice",
                        "source_kind": "table",
                        "classification": "fact",
                        "grain": [{"source_id": "purchase_invoice", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "supplier",
                        "resource_id": "table:SUPPLIER",
                        "relation": ["SUPPLIER"],
                        "alias": "supplier",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "supplier", "field": "DOC_NAME"}],
                    },
                ],
                "joins": [{
                    "id": "pinv_supplier",
                    "left_source": "purchase_invoice",
                    "right_source": "supplier",
                    "join_type": "inner",
                    "cardinality": "many-to-one",
                    "active": True,
                    "predicates": [{
                        "left": {"source_id": "purchase_invoice", "field": "SUPPLIER"},
                        "right": {"source_id": "supplier", "field": "DOC_NAME"},
                        "operator": "eq",
                    }],
                }],
                "dimensions": [
                    {
                        "id": "supplier",
                        "name": "Supplier",
                        "field": {"source_id": "supplier", "field": "DOC_NAME"},
                        "name_field": {"source_id": "supplier", "field": "SUPPLIER_NAME"},
                        "join_id": "pinv_supplier",
                        "attributes": [
                            {"id": "supp_group", "name": "Supplier Group", "field": {"source_id": "supplier", "field": "SUPPLIER_GROUP"}},
                            {"id": "supp_country", "name": "Country", "field": {"source_id": "supplier", "field": "COUNTRY"}},
                        ],
                    },
                    {
                        "id": "posting_date",
                        "name": "Posting Date",
                        "field": {"source_id": "purchase_invoice", "field": "POSTING_DATE"},
                        "is_time": True,
                        "time_role": "calendar-time",
                    },
                ],
                "measures": [
                    {
                        "id": "total_spend",
                        "name": "Total Procurement Spend",
                        "aggregation": "sum",
                        "field": {"source_id": "purchase_invoice", "field": "NET_TOTAL"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_pinv",
                    },
                    {
                        "id": "open_payables",
                        "name": "Open AP Balance",
                        "aggregation": "sum",
                        "field": {"source_id": "purchase_invoice", "field": "OUTSTANDING_AMOUNT"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_pinv",
                    },
                    {
                        "id": "bill_count",
                        "name": "Supplier Invoices",
                        "aggregation": "count",
                        "field": None,
                        "format": "#,##0",
                        "measure_group_id": "mg_pinv",
                    },
                ],
                "measure_groups": [{
                    "id": "mg_pinv",
                    "name": "Purchase Invoice Spend",
                    "fact_source": "purchase_invoice",
                    "measures": ["total_spend", "open_payables", "bill_count"],
                    "dimension_usage": [
                        {"dimension_id": "supplier", "relationship_kind": "regular", "join_id": "pinv_supplier", "active": True},
                        {"dimension_id": "posting_date", "relationship_kind": "fact", "active": True},
                    ],
                }],
                "materializations": [{
                    "id": "agg_supplier_spend",
                    "name": "Monthly Supplier Spend Rollup",
                    "strategy": "aggregate_table",
                    "enabled": True,
                    "measure_group_id": "mg_pinv",
                    "grain_dimensions": ["supplier", "posting_date"],
                    "measures": ["total_spend", "open_payables"],
                    "target_relation": ["AGG_SUPPLIER_SPEND_MONTHLY"],
                    "partition_grain": "month",
                    "refresh_policy": "manual",
                }],
            },
        },
        {
            "project_key": "erpnext-stock-ledger",
            "design_key": "cube-inventory-valuation",
            "title": "Inventory Valuation & Stock Turnover Cube",
            "model": {
                "name": "Inventory Valuation & Stock Turnover Cube",
                "description": "Warehouse stock movements, FIFO/moving-average valuation deltas, and item group velocity.",
                "semantic_family": "relational",
                "sources": [
                    {
                        "id": "sle",
                        "resource_id": "table:STOCK_LEDGER_ENTRY",
                        "relation": ["STOCK_LEDGER_ENTRY"],
                        "alias": "sle",
                        "source_kind": "table",
                        "classification": "fact",
                        "grain": [{"source_id": "sle", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "item",
                        "resource_id": "table:ITEM",
                        "relation": ["ITEM"],
                        "alias": "item",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "item", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "warehouse",
                        "resource_id": "table:WAREHOUSE",
                        "relation": ["WAREHOUSE"],
                        "alias": "warehouse",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "warehouse", "field": "DOC_NAME"}],
                    },
                ],
                "joins": [
                    {
                        "id": "sle_item",
                        "left_source": "sle",
                        "right_source": "item",
                        "join_type": "inner",
                        "cardinality": "many-to-one",
                        "active": True,
                        "predicates": [{
                            "left": {"source_id": "sle", "field": "ITEM_CODE"},
                            "right": {"source_id": "item", "field": "DOC_NAME"},
                            "operator": "eq",
                        }],
                    },
                    {
                        "id": "sle_warehouse",
                        "left_source": "sle",
                        "right_source": "warehouse",
                        "join_type": "inner",
                        "cardinality": "many-to-one",
                        "active": True,
                        "predicates": [{
                            "left": {"source_id": "sle", "field": "WAREHOUSE"},
                            "right": {"source_id": "warehouse", "field": "DOC_NAME"},
                            "operator": "eq",
                        }],
                    },
                ],
                "dimensions": [
                    {
                        "id": "item",
                        "name": "Stock Item",
                        "field": {"source_id": "item", "field": "DOC_NAME"},
                        "name_field": {"source_id": "item", "field": "ITEM_NAME"},
                        "join_id": "sle_item",
                        "attributes": [
                            {"id": "item_group", "name": "Item Group", "field": {"source_id": "item", "field": "ITEM_GROUP"}},
                        ],
                    },
                    {
                        "id": "warehouse",
                        "name": "Warehouse",
                        "field": {"source_id": "warehouse", "field": "DOC_NAME"},
                        "name_field": {"source_id": "warehouse", "field": "WAREHOUSE_NAME"},
                        "join_id": "sle_warehouse",
                    },
                    {
                        "id": "posting_date",
                        "name": "Movement Date",
                        "field": {"source_id": "sle", "field": "POSTING_DATE"},
                        "is_time": True,
                        "time_role": "event-time",
                    },
                ],
                "measures": [
                    {
                        "id": "net_qty_delta",
                        "name": "Net Quantity Change",
                        "aggregation": "sum",
                        "field": {"source_id": "sle", "field": "ACTUAL_QTY"},
                        "format": "#,##0.00",
                        "measure_group_id": "mg_sle",
                    },
                    {
                        "id": "stock_value_delta",
                        "name": "Stock Value Difference",
                        "aggregation": "sum",
                        "field": {"source_id": "sle", "field": "STOCK_VALUE_DIFFERENCE"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_sle",
                    },
                    {
                        "id": "movement_count",
                        "name": "Ledger Movements",
                        "aggregation": "count",
                        "field": None,
                        "format": "#,##0",
                        "measure_group_id": "mg_sle",
                    },
                ],
                "measure_groups": [{
                    "id": "mg_sle",
                    "name": "Stock Ledger Movements",
                    "fact_source": "sle",
                    "measures": ["net_qty_delta", "stock_value_delta", "movement_count"],
                    "dimension_usage": [
                        {"dimension_id": "item", "relationship_kind": "regular", "join_id": "sle_item", "active": True},
                        {"dimension_id": "warehouse", "relationship_kind": "regular", "join_id": "sle_warehouse", "active": True},
                        {"dimension_id": "posting_date", "relationship_kind": "fact", "active": True},
                    ],
                }],
                "materializations": [{
                    "id": "agg_wh_item_monthly",
                    "name": "Warehouse Monthly Stock Balance Aggregate",
                    "strategy": "aggregate_table",
                    "enabled": True,
                    "measure_group_id": "mg_sle",
                    "grain_dimensions": ["warehouse", "item", "posting_date"],
                    "measures": ["net_qty_delta", "stock_value_delta"],
                    "target_relation": ["AGG_STOCK_MONTHLY"],
                    "partition_grain": "month",
                    "refresh_policy": "on_accept_review",
                }],
            },
        },
        {
            "project_key": "hrms-payroll-tax",
            "design_key": "cube-workforce-payroll",
            "title": "Workforce Compensation & Payroll Cube",
            "model": {
                "name": "Workforce Compensation & Payroll Cube",
                "description": "Gross pay, statutory deductions, and net compensation across departments and designations.",
                "semantic_family": "relational",
                "sources": [
                    {
                        "id": "salary_slip",
                        "resource_id": "table:SALARY_SLIP",
                        "relation": ["SALARY_SLIP"],
                        "alias": "salary_slip",
                        "source_kind": "table",
                        "classification": "fact",
                        "grain": [{"source_id": "salary_slip", "field": "DOC_NAME"}],
                    },
                    {
                        "id": "employee",
                        "resource_id": "table:EMPLOYEE",
                        "relation": ["EMPLOYEE"],
                        "alias": "employee",
                        "source_kind": "table",
                        "classification": "dimension",
                        "grain": [{"source_id": "employee", "field": "DOC_NAME"}],
                    },
                ],
                "joins": [{
                    "id": "ss_employee",
                    "left_source": "salary_slip",
                    "right_source": "employee",
                    "join_type": "inner",
                    "cardinality": "many-to-one",
                    "active": True,
                    "predicates": [{
                        "left": {"source_id": "salary_slip", "field": "EMPLOYEE"},
                        "right": {"source_id": "employee", "field": "DOC_NAME"},
                        "operator": "eq",
                    }],
                }],
                "dimensions": [
                    {
                        "id": "employee",
                        "name": "Employee",
                        "field": {"source_id": "employee", "field": "DOC_NAME"},
                        "name_field": {"source_id": "employee", "field": "EMPLOYEE_NAME"},
                        "join_id": "ss_employee",
                        "attributes": [
                            {"id": "dept", "name": "Department", "field": {"source_id": "employee", "field": "DEPARTMENT"}},
                            {"id": "desig", "name": "Designation", "field": {"source_id": "employee", "field": "DESIGNATION"}},
                        ],
                    },
                    {
                        "id": "posting_date",
                        "name": "Pay Period End Date",
                        "field": {"source_id": "salary_slip", "field": "POSTING_DATE"},
                        "is_time": True,
                        "time_role": "fiscal-time",
                    },
                ],
                "measures": [
                    {
                        "id": "gross_pay",
                        "name": "Total Gross Pay",
                        "aggregation": "sum",
                        "field": {"source_id": "salary_slip", "field": "GROSS_PAY"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_payroll",
                    },
                    {
                        "id": "total_deduction",
                        "name": "Total Deductions",
                        "aggregation": "sum",
                        "field": {"source_id": "salary_slip", "field": "TOTAL_DEDUCTION"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_payroll",
                    },
                    {
                        "id": "net_pay",
                        "name": "Total Net Pay",
                        "aggregation": "sum",
                        "field": {"source_id": "salary_slip", "field": "NET_PAY"},
                        "format": "$#,##0.00",
                        "measure_group_id": "mg_payroll",
                    },
                ],
                "measure_groups": [{
                    "id": "mg_payroll",
                    "name": "Monthly Payroll Runs",
                    "fact_source": "salary_slip",
                    "measures": ["gross_pay", "total_deduction", "net_pay"],
                    "dimension_usage": [
                        {"dimension_id": "employee", "relationship_kind": "regular", "join_id": "ss_employee", "active": True},
                        {"dimension_id": "posting_date", "relationship_kind": "fact", "active": True},
                    ],
                }],
                "materializations": [],
            },
        },
        {
            "project_key": "datum-cargo-telemetry",
            "design_key": "cube-cloud-cargo-telemetry",
            "title": "Datum & Cargo SRE Observability Cube",
            "model": {
                "name": "Datum & Cargo SRE Observability Cube",
                "description": "Bench telemetry cube over DATUM_SAMPLES with peak/mean resource utilization and CPU series filter.",
                "semantic_family": "relational",
                "sources": [{
                    "id": "samples",
                    "resource_id": "table:DATUM_SAMPLES",
                    "relation": ["DATUM_SAMPLES"],
                    "alias": "samples",
                    "source_kind": "table",
                    "classification": "fact",
                    "grain": [{"source_id": "samples", "field": "SAMPLE_ID"}],
                }],
                "joins": [],
                "dimensions": [
                    {
                        "id": "resource_bench",
                        "name": "Cargo Bench Resource",
                        "field": {"source_id": "samples", "field": "RESOURCE_ID"},
                    },
                    {
                        "id": "service_name",
                        "name": "Service Daemon",
                        "field": {"source_id": "samples", "field": "SERVICE_NAME"},
                    },
                    {
                        "id": "metric_name",
                        "name": "Telemetry Metric",
                        "field": {"source_id": "samples", "field": "METRIC"},
                    },
                ],
                "measures": [
                    {
                        "id": "avg_sample",
                        "name": "Mean Sample Value",
                        "aggregation": "avg",
                        "field": {"source_id": "samples", "field": "SAMPLE_VALUE"},
                        "format": "#,##0.00",
                        "measure_group_id": "mg_telemetry",
                    },
                    {
                        "id": "peak_sample",
                        "name": "Peak Sample Value",
                        "aggregation": "max",
                        "field": {"source_id": "samples", "field": "SAMPLE_VALUE"},
                        "format": "#,##0.00",
                        "measure_group_id": "mg_telemetry",
                    },
                    {
                        "id": "cpu_samples",
                        "name": "CPU Series Observations",
                        "aggregation": "count",
                        "field": None,
                        "format": "#,##0",
                        "measure_group_id": "mg_telemetry",
                        "filters": [{
                            "field": {"source_id": "samples", "field": "SERIES_KIND"},
                            "operator": "eq",
                            "value": "cpu",
                        }],
                    },
                ],
                "measure_groups": [{
                    "id": "mg_telemetry",
                    "name": "Datum Telemetry Samples",
                    "fact_source": "samples",
                    "measures": ["avg_sample", "peak_sample", "cpu_samples"],
                    "dimension_usage": [
                        {"dimension_id": "resource_bench", "relationship_kind": "fact", "active": True},
                        {"dimension_id": "service_name", "relationship_kind": "fact", "active": True},
                        {"dimension_id": "metric_name", "relationship_kind": "fact", "active": True},
                    ],
                }],
                "materializations": [{
                    "id": "agg_datum_daily",
                    "name": "Daily Telemetry Stats Rollup",
                    "strategy": "aggregate_table",
                    "enabled": True,
                    "measure_group_id": "mg_telemetry",
                    "grain_dimensions": ["resource_bench", "metric_name"],
                    "measures": ["avg_sample", "peak_sample"],
                    "target_relation": ["DATUM_DAILY_SAMPLE_STATS"],
                    "partition_grain": "day",
                    "refresh_policy": "incremental",
                }],
            },
        },
    ]

    created_cubes: dict[str, str] = {}
    for spec in cube_specs:
        pkey = spec["project_key"]
        puuid = projects_by_key[pkey]
        v1_model = public_model(validate_model(spec["model"]))
        v1_ddn, id_map = semantic_model_to_ddn(
            v1_model,
            cube_notes=[f"Accepted v1.0 active cube bound to Firebird target {fb_tgt}"],
        )

        # Build v2 (In Review) & v3 (Draft) save points for the flagship GL & Revenue cubes (Pillar 4!)
        versions: list[tuple[int, int | None, str, str, str]] = [
            (1, None, "accepted", v1_ddn, "Initial accepted active semantic cube"),
        ]
        if pkey in ("erpnext-acc-general-ledger", "erpnext-selling-orders"):
            v2_raw = copy.deepcopy(spec["model"])
            v2_raw["annotations"] = {"cube_version_label": "1.1-rc1"}
            v2_ddn, _ = semantic_model_to_ddn(
                v2_raw,
                element_ids=id_map,
                cube_notes=[
                    "v1.1 In-Review: added cross-border FX & withholding review notes",
                ],
            )
            v3_raw = copy.deepcopy(spec["model"])
            v3_raw["annotations"] = {"cube_version_label": "1.2-draft"}
            v3_raw["description"] = spec["model"]["description"] + " [Draft v1.2: DuckDB lakehouse hybrid aggregate tier]"
            v3_ddn, _ = semantic_model_to_ddn(
                v3_raw,
                element_ids=id_map,
                cube_notes=[
                    "v1.2 Draft: staged DuckDB MART_GL_MONTHLY hybrid aggregate target",
                ],
            )
            versions.append((2, 1, "in_review", v2_ddn, "Submitted multi-currency review checkpoint"))
            versions.append((3, 2, "draft", v3_ddn, "Draft hybrid lakehouse materialization bump"))

        did = _upsert_design_with_versions(
            dconn,
            project_key=pkey,
            design_key=spec["design_key"],
            kind="cube",
            title=spec["title"],
            versions=versions,
            active_version=1,
            user_id=user_id,
            now_iso=now_iso,
        )
        created_cubes[spec["design_key"]] = did

        # Populate element & binding rows in designs.db for every cube source table
        rbs = []
        for src in v1_model["sources"]:
            tname = src["relation"][-1]
            el_id = uuid7()
            dconn.execute(
                """
                INSERT INTO element (
                  id, design_id, role, name, first_version, removed_version
                ) VALUES (?, ?, ?, ?, 1, NULL)
                """,
                (el_id, did, src["classification"], tname),
            )
            dconn.execute(
                """
                INSERT INTO binding (
                  id, design_id, element_id, target_kind, target_ref,
                  target_engine, target_endpoint_id, target_database_target_id,
                  state, state_reason, confirmed_by, confirmed_at
                ) VALUES (?, ?, ?, 'resource', ?, 'firebird', ?, ?, 'valid', NULL, ?, ?)
                """,
                (uuid7(), did, el_id, f"table:{tname}", fb_ep, fb_tgt, user_id, now_iso),
            )
            rbs.append(_resource_ref("firebird", fb_ep, fb_tgt, "table", tname, role="referenced_fk"))

        # Upsert active runtime row in cde_semantic_model + cde_semantic_model_revision
        def_json = json.dumps(v1_model, sort_keys=True)
        existing_sm = cconn.execute(
            "SELECT id FROM cde_semantic_model WHERE user_id = ? AND endpoint_id = ? AND name = ?",
            (user_id, fb_ep, spec["title"]),
        ).fetchone()
        sm_id = existing_sm[0] if existing_sm else did
        cconn.execute("DELETE FROM cde_semantic_model_revision WHERE model_id = ?", (sm_id,))
        if existing_sm:
            cconn.execute(
                """
                UPDATE cde_semantic_model
                SET status = 'published', revision = 1, definition = ?, updated_at = ?
                WHERE id = ?
                """,
                (def_json, now_sql, sm_id),
            )
        else:
            cconn.execute(
                """
                INSERT INTO cde_semantic_model (
                  id, user_id, endpoint_id, name, status, revision, definition, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'published', 1, ?, ?, ?)
                """,
                (sm_id, user_id, fb_ep, spec["title"], def_json, now_sql, now_sql),
            )
        cconn.execute(
            """
            INSERT INTO cde_semantic_model_revision (
              id, model_id, revision, status, definition, created_at
            ) VALUES (?, ?, 1, 'published', ?, ?)
            """,
            (str(uuid.uuid4()), sm_id, def_json, now_sql),
        )

        # Upsert Project Asset (asset_key == design_id so Project Navigator opens CubeDesignerSurface!)
        _upsert_validated_asset(
            cconn,
            project_key=pkey,
            project_uuid=puuid,
            user_id=user_id,
            asset_key=did,
            request_payload={
                "asset_type": "cdeadmin.design.cube",
                "schema_name": "cdeadmin.design.cube",
                "schema_version": 1,
                "name": spec["title"],
                "path": f"cubes/{spec['design_key']}.cube.ddn",
                "expected_version": 0,
                "content": {
                    "design_id": did,
                    "semantic_model_id": sm_id,
                    "endpoint_id": fb_ep,
                },
                "metadata": {"report_category": "graphs", "cube_profile": "cube.dimensional@1"},
                "dependency_references": [],
                "resource_bindings": rbs,
                "validation_state": "valid",
                "validation_details": [],
            },
            now_sql=now_sql,
        )

    return created_cubes


def seed_pillar_2_bi_dashboards_alerts_and_embeds(
    dconn: sqlite3.Connection,
    cconn: sqlite3.Connection,
    *,
    donor_root: Path,
    projects_by_key: dict[str, str],
    endpoints: dict[str, dict[str, str]],
    user_id: int,
    now_iso: str,
    now_sql: str,
) -> dict[str, int]:
    """Seed 36 BI Questions, 12 Composed BI Dashboards, outward effects, BI alerts & embeds."""
    fb_ep = endpoints["firebird"]["endpoint_id"]
    dk_ep = endpoints.get("duckdb", endpoints["firebird"])["endpoint_id"]

    # Sample real chart titles from donor dashboard_chart JSONs for authentic provenance metadata
    donor_chart_names: list[str] = []
    for p in sorted(glob.glob(str(donor_root / "**/dashboard_chart/*/*.json"), recursive=True))[:40]:
        try:
            c = json.loads(Path(p).read_text(encoding="utf-8"))
            if c.get("chart_name"):
                donor_chart_names.append(str(c["chart_name"]))
        except Exception:
            pass

    dashboard_blueprints = [
        {
            "project_key": "erpnext-acc-general-ledger",
            "dash_key": "dash-cfo-executive-pnl",
            "title": "CFO Executive P&L, Trial Balance & Cashflow",
            "endpoint_id": fb_ep,
            "multi_version": True,
            "filters": [
                {"id": "company", "name": "Legal Entity", "type": "string", "widget": "select", "pinned_by_author": True, "default": "Maple Tech Manufacturing"},
                {"id": "fiscal_year", "name": "Fiscal Year", "type": "string", "widget": "select", "pinned_by_author": False, "default": "FY-2026"},
            ],
            "questions": [
                ("q-gl-monthly-rev-exp", "Monthly Revenue vs Expense Trend", "line", "SELECT SUBSTRING(CAST(POSTING_DATE AS VARCHAR(10)) FROM 1 FOR 7) AS YM, SUM(CREDIT) AS TOTAL_CREDIT, SUM(DEBIT) AS TOTAL_DEBIT FROM GL_ENTRY GROUP BY 1 ORDER BY 1", [["2026-09", 412800, 298400], ["2026-10", 468900, 315200], ["2026-11", 502100, 334800]]),
                ("q-gl-trial-balance-root", "Trial Balance by Root Account Type", "bar", "SELECT ROOT_TYPE, TOTAL_DEBIT, TOTAL_CREDIT, NET_MOVEMENT FROM VW_ERP_GL_TRIAL_BALANCE", [["Asset", 1840200, 1210400, 629800], ["Income", 0, 2950400, -2950400], ["Expense", 1980100, 0, 1980100]]),
                ("q-gl-company-snapshot", "Selectable Procedure Company Snapshot", "table", "SELECT * FROM SP_COMPANY_FINANCIAL_SNAPSHOT", [["Maple Tech Manufacturing", "CAD", 1620400, 910200], ["Northstar Cloud Services", "USD", 890500, 402100]]),
            ],
        },
        {
            "project_key": "erpnext-acc-receivables",
            "dash_key": "dash-ar-collections-aging",
            "title": "Accounts Receivable Aging & Collections Velocity",
            "endpoint_id": fb_ep,
            "multi_version": True,
            "filters": [
                {"id": "status", "name": "Invoice Status", "type": "string", "widget": "select", "pinned_by_author": False},
            ],
            "questions": [
                ("q-ar-open-by-customer", "Top Open Receivables by Customer", "bar", "SELECT CUSTOMER_NAME, OPEN_RECEIVABLE_TOTAL FROM VW_ERP_CUSTOMER_REVENUE WHERE OPEN_RECEIVABLE_TOTAL > 0 ORDER BY 2 DESC", [["Contoso Water Systems", 48200], ["Bluewater Maritime Logistics", 36900], ["Alpine Robotics GmbH", 29400]]),
                ("q-ar-status-mix", "Sales Invoice Settlement Mix", "pie", "SELECT STATUS, COUNT(*) AS INVOICE_COUNT, SUM(GRAND_TOTAL) AS BILLED FROM SALES_INVOICE GROUP BY STATUS", [["Paid", 1920, 4820000], ["Partly Paid", 240, 610000], ["Unpaid", 240, 595000]]),
                ("q-ar-collections-monthly", "Monthly Customer Payment Receipts", "area", "SELECT SUBSTRING(CAST(POSTING_DATE AS VARCHAR(10)) FROM 1 FOR 7) AS YM, SUM(RECEIVED_AMOUNT) AS COLLECTED FROM PAYMENT_ENTRY WHERE PAYMENT_TYPE = 'Receive' GROUP BY 1 ORDER BY 1", [["2026-09", 388000], ["2026-10", 421500], ["2026-11", 449200]]),
            ],
        },
        {
            "project_key": "erpnext-acc-payables",
            "dash_key": "dash-ap-procurement-spend",
            "title": "Accounts Payable & Supplier Liability Console",
            "endpoint_id": fb_ep,
            "multi_version": False,
            "filters": [],
            "questions": [
                ("q-ap-top-suppliers", "Spend by Supplier", "bar", "SELECT SUPPLIER_NAME, SUM(NET_TOTAL) AS SPEND FROM PURCHASE_INVOICE GROUP BY SUPPLIER_NAME ORDER BY 2 DESC", [["St. Lawrence Alloys Ltd.", 412000], ["Boreal Semiconductor Corp.", 368000], ["Northern Rack & Baremetal Inc.", 284000]]),
                ("q-ap-open-status", "AP Paid vs Unpaid Vouchers", "pie", "SELECT STATUS, COUNT(*) AS BILLS, SUM(OUTSTANDING_AMOUNT) AS OPEN_AP FROM PURCHASE_INVOICE GROUP BY STATUS", [["Paid", 900, 0], ["Unpaid", 300, 294500]]),
                ("q-ap-monthly-outflow", "Monthly Procurement Spend Trend", "line", "SELECT SUBSTRING(CAST(POSTING_DATE AS VARCHAR(10)) FROM 1 FOR 7) AS YM, SUM(GRAND_TOTAL) AS BILLED_SPEND FROM PURCHASE_INVOICE GROUP BY 1 ORDER BY 1", [["2026-09", 182000], ["2026-10", 196400], ["2026-11", 204800]]),
            ],
        },
        {
            "project_key": "erpnext-selling-orders",
            "dash_key": "dash-order-to-cash-commercial",
            "title": "Order-to-Cash Commercial Revenue & Territory Mix",
            "endpoint_id": fb_ep,
            "multi_version": False,
            "filters": [
                {"id": "territory", "name": "Sales Territory", "type": "string", "widget": "select", "pinned_by_author": False},
            ],
            "questions": [
                ("q-sell-territory-rev", "Booked Order Value by Territory", "bar", "SELECT TERRITORY, COUNT(*) AS ORDERS, SUM(NET_TOTAL) AS ORDER_VALUE FROM SALES_ORDER GROUP BY TERRITORY ORDER BY 3 DESC", [["North America", 1680, 4920000], ["Europe", 480, 1480000], ["Asia Pacific", 240, 740000]]),
                ("q-sell-top-items", "Top Revenue Generating Products", "bar", "SELECT ITEM_NAME, SUM(QTY) AS UNITS_SOLD, SUM(AMOUNT) AS REVENUE FROM SALES_INVOICE_ITEM GROUP BY ITEM_NAME ORDER BY 3 DESC", [["Centrifugal Process Pump 500L", 820, 3485000], ["Brazed Plate Heat Exchanger", 540, 1879200], ["Managed Frappe Cloud Dedicated Bench", 960, 816000]]),
                ("q-sell-order-fulfillment", "Sales Order Fulfillment Status", "table", "SELECT STATUS, COUNT(*) AS ORDER_COUNT, SUM(GRAND_TOTAL) AS TOTAL_VALUE FROM SALES_ORDER GROUP BY STATUS", [["Completed", 1920, 5810000], ["To Bill", 480, 1330000]]),
            ],
        },
        {
            "project_key": "erpnext-stock-ledger",
            "dash_key": "dash-inventory-warehouse-health",
            "title": "Inventory Valuation & Warehouse Movement Operations",
            "endpoint_id": fb_ep,
            "multi_version": True,
            "filters": [
                {"id": "warehouse", "name": "Warehouse", "type": "string", "widget": "select", "pinned_by_author": False},
            ],
            "questions": [
                ("q-stk-warehouse-balance", "Stock Balance & Value by Warehouse", "bar", "SELECT WAREHOUSE, ITEM_CODE, NET_QTY, LATEST_STOCK_VALUE FROM VW_ERP_STOCK_VALUATION ORDER BY LATEST_STOCK_VALUE DESC", [["Toronto Main Stores - MTM", "ITM-PUMP-500", 142, 404700], ["Saskatoon Agro Depot - HAC", "ITM-WEATHER-ST", 96, 74880]]),
                ("q-stk-item-velocity", "Item Movement Count by Voucher Type", "bar", "SELECT VOUCHER_TYPE, COUNT(*) AS MOVEMENTS, SUM(ABS(ACTUAL_QTY)) AS GROSS_UNITS FROM STOCK_LEDGER_ENTRY GROUP BY VOUCHER_TYPE", [["Sales Invoice", 3200, 14800], ["Purchase Invoice", 1800, 19600]]),
                ("q-stk-monthly-delta", "Monthly Net Stock Value Delta", "line", "SELECT SUBSTRING(CAST(POSTING_DATE AS VARCHAR(10)) FROM 1 FOR 7) AS YM, SUM(STOCK_VALUE_DIFFERENCE) AS VALUE_DELTA FROM STOCK_LEDGER_ENTRY GROUP BY 1 ORDER BY 1", [["2026-09", 42800], ["2026-10", 31900], ["2026-11", 54200]]),
            ],
        },
        {
            "project_key": "erpnext-mfg-production",
            "dash_key": "dash-manufacturing-shopfloor",
            "title": "Manufacturing Shop-Floor, BOM & Work Order Yield",
            "endpoint_id": fb_ep,
            "multi_version": False,
            "filters": [],
            "questions": [
                ("q-mfg-assemblies-rate", "Industrial Assembly Standard vs Valuation Cost", "bar", "SELECT ITEM_CODE, STANDARD_RATE, VALUATION_RATE, (STANDARD_RATE - VALUATION_RATE) AS UNIT_MARGIN FROM ITEM WHERE ITEM_GROUP = 'Industrial Assemblies'", [["ITM-PUMP-500", 4250, 2850, 1400], ["ITM-HEAT-EX4", 3480, 2210, 1270], ["ITM-FLOW-900", 2190, 1340, 850]]),
                ("q-mfg-work-orders", "Work Order & BOM Catalog Readiness", "table", "SELECT FIRST 25 DOC_NAME, STATUS, CREATION_TS FROM WORK_ORDER", [["WORK_ORDER-001", "In Process", "2026-10-15 09:00:00"], ["WORK_ORDER-002", "Completed", "2026-10-18 14:30:00"]]),
                ("q-mfg-quality-inspections", "Quality Inspection Records", "table", "SELECT FIRST 25 DOC_NAME, STATUS, MODIFIED_TS FROM QUALITY_INSPECTION", [["QUALITY_INSPECTION-001", "Accepted", "2026-10-20 11:00:00"]]),
            ],
        },
        {
            "project_key": "hrms-payroll-tax",
            "dash_key": "dash-hr-workforce-payroll",
            "title": "HR Headcount, Attendance & Monthly Payroll Analytics",
            "endpoint_id": fb_ep,
            "multi_version": False,
            "filters": [
                {"id": "department", "name": "Department", "type": "string", "widget": "select", "pinned_by_author": False},
            ],
            "questions": [
                ("q-hr-dept-payroll", "Department Headcount & Compensation Summary", "bar", "SELECT COMPANY, DEPARTMENT, HEADCOUNT, GROSS_PAY_TOTAL, NET_PAY_TOTAL FROM VW_HRMS_PAYROLL_SUMMARY", [["Maple Tech Manufacturing", "Engineering - MTM", 6, 1984000, 1507840], ["Northstar Cloud Services", "Cloud Platform - NCS", 7, 2412000, 1833120]]),
                ("q-hr-monthly-payroll", "24-Month Gross vs Net Payroll Run", "area", "SELECT SUBSTRING(CAST(POSTING_DATE AS VARCHAR(10)) FROM 1 FOR 7) AS YM, SUM(GROSS_PAY) AS GROSS, SUM(NET_PAY) AS NET FROM SALARY_SLIP GROUP BY 1 ORDER BY 1", [["2026-09", 331200, 251712], ["2026-10", 331200, 251712], ["2026-11", 331200, 251712]]),
                ("q-hr-attendance-mode", "Workforce Attendance Mode Distribution", "pie", "SELECT STATUS, COUNT(*) AS SHIFT_DAYS, AVG(WORKING_HOURS) AS AVG_HOURS FROM ATTENDANCE GROUP BY STATUS", [["Present", 5340, 8.45], ["Work From Home", 420, 8.35]]),
            ],
        },
        {
            "project_key": "frappe-crm",
            "dash_key": "dash-crm-revenue-funnel",
            "title": "Frappe CRM Lead-to-Deal Pipeline & Forecast",
            "endpoint_id": fb_ep,
            "multi_version": False,
            "filters": [],
            "questions": [
                ("q-crm-lead-funnel", "Lead Qualification Funnel", "bar", "SELECT STATUS, COUNT(*) AS LEADS, SUM(ANNUAL_REVENUE) AS EST_COMPANY_REV FROM CRM_LEAD GROUP BY STATUS", [["Qualified", 122, 51200000], ["Converted", 120, 48900000], ["Contacted", 121, 46400000]]),
                ("q-crm-deal-stages", "Deal Pipeline by Stage & Probability", "bar", "SELECT STATUS, COUNT(*) AS DEALS, AVG(PROBABILITY) AS AVG_PROB, SUM(ANNUAL_REVENUE) AS PIPELINE_ARR FROM CRM_DEAL GROUP BY STATUS", [["Won", 87, 95.0, 4120000], ["Negotiation", 87, 75.0, 3890000], ["Proposal", 86, 55.0, 3540000]]),
                ("q-crm-owner-leaderboard", "Deal Owner Pipeline Leaderboard", "table", "SELECT DEAL_OWNER, COUNT(*) AS DEAL_COUNT, SUM(ANNUAL_REVENUE) AS TOTAL_ARR FROM CRM_DEAL GROUP BY DEAL_OWNER ORDER BY 3 DESC", [["ada.lovelace@scratchbird-demo.example", 109, 5140000], ["grace.hopper@scratchbird-demo.example", 109, 4980000]]),
            ],
        },
        {
            "project_key": "frappe-helpdesk",
            "dash_key": "dash-helpdesk-sla-ops",
            "title": "Helpdesk Ticket Volume, Priority & SLA Fulfillment",
            "endpoint_id": fb_ep,
            "multi_version": False,
            "filters": [
                {"id": "priority", "name": "Ticket Priority", "type": "string", "widget": "select", "pinned_by_author": False},
            ],
            "questions": [
                ("q-hd-priority-status", "Support Backlog by Priority & Status", "bar", "SELECT PRIORITY, STATUS, TICKET_COUNT FROM VW_HELPDESK_SLA_QUEUE", [["Urgent", "Open", 75], ["High", "Replied", 76], ["Medium", "Resolved", 75]]),
                ("q-hd-sla-compliance", "SLA Agreement Fulfillment Rate", "pie", "SELECT AGREEMENT_STATUS, COUNT(*) AS TICKETS FROM HD_TICKET GROUP BY AGREEMENT_STATUS", [["Fulfilled", 1029], ["Failed", 174]]),
                ("q-hd-monthly-intake", "Monthly Support Ticket Intake", "line", "SELECT SUBSTRING(CAST(CREATION_TS AS VARCHAR(19)) FROM 1 FOR 7) AS YM, COUNT(*) AS TICKETS FROM HD_TICKET GROUP BY 1 ORDER BY 1", [["2026-09", 50], ["2026-10", 50], ["2026-11", 53]]),
            ],
        },
        {
            "project_key": "lending-servicing-ledger",
            "dash_key": "dash-lending-portfolio-risk",
            "title": "Lending Portfolio Disbursement & Repayment Risk",
            "endpoint_id": fb_ep,
            "multi_version": False,
            "filters": [],
            "questions": [
                ("q-loan-exposure", "Loan Portfolio Exposure by Company", "bar", "SELECT COMPANY, STATUS, LOAN_COUNT, TOTAL_DISBURSED, TOTAL_REPAID FROM VW_LENDING_PORTFOLIO_RISK", [["Horizon Agritech Cooperative", "Disbursed", 1, 120000, 24500], ["Maple Tech Manufacturing", "Closed", 1, 85000, 85000]]),
                ("q-loan-interest-rates", "Active Loan Interest Rate Schedule", "table", "SELECT DOC_NAME, APPLICANT_NAME, LOAN_AMOUNT, RATE_OF_INTEREST, TOTAL_AMOUNT_PAID, STATUS FROM LOAN", [["LOAN-2026-0001", "Prairie Grain Growers", 120000, 5.75, 24500, "Disbursed"]]),
                ("q-loan-security", "Loan Security & Repayment Overview", "table", "SELECT FIRST 20 DOC_NAME, CREATION_TS, DOCSTATUS FROM LOAN_REPAYMENT", [["LOAN_REPAYMENT-001", "2026-10-01 09:00:00", 1]]),
            ],
        },
        {
            "project_key": "datum-cargo-telemetry",
            "dash_key": "dash-cloud-cargo-sre",
            "title": "Frappe Cloud, Cargo Bench & Boat Hypervisor SRE Console",
            "endpoint_id": fb_ep,
            "multi_version": True,
            "include_static_metric_panel": True,
            "filters": [
                {"id": "resource_id", "name": "Cargo Bench", "type": "string", "widget": "select", "pinned_by_author": True, "default": "cargo:prod-bench-01"},
            ],
            "questions": [
                ("q-sre-bench-metrics", "Cargo Bench CPU, Memory & Firebird I/O Telemetry", "line", "SELECT RESOURCE_ID, METRIC, AVG(SAMPLE_VALUE) AS MEAN_VAL, MAX(SAMPLE_VALUE) AS PEAK_VAL FROM DATUM_SAMPLES GROUP BY RESOURCE_ID, METRIC", [["cargo:prod-bench-01", "system_cpu_usage_percent", 38.4, 47.5], ["cargo:prod-bench-03", "firebird_page_reads_per_sec", 418.2, 524.0]]),
                ("q-sre-http-log-levels", "Cloud Log Severity & HTTP Status Distribution", "bar", "SELECT SERVICE_NAME, LOG_LEVEL, HTTP_STATUS, COUNT(*) AS EVENTS FROM DATUM_LOGS GROUP BY 1, 2, 3 ORDER BY 4 DESC", [["web", "INFO", 200, 720], ["worker", "WARN", 429, 240], ["firebird-db", "ERROR", 502, 240]]),
                ("q-sre-trace-latencies", "OpenTelemetry Span P95 Latency Waterfall", "table", "SELECT SERVICE_NAME, SPAN_NAME, STATUS_CODE, COUNT(*) AS SPANS, AVG(DURATION_NS / 1000000.0) AS AVG_MS FROM DATUM_TRACES GROUP BY 1, 2, 3", [["frappe-web", "POST /api/resource/Sales Invoice", "OK", 427, 66.8], ["firebird-db", "INSERT INTO GL_ENTRY", "OK", 427, 9.1]]),
            ],
        },
        {
            "project_key": "collab-insights",
            "dash_key": "dash-polyglot-lakehouse-exec",
            "title": "Polyglot 3-Engine Lakehouse & Macro Public Datasets Overview",
            "endpoint_id": dk_ep,
            "multi_version": False,
            "filters": [],
            "questions": [
                ("q-lake-exec-pnl", "DuckDB Lakehouse Monthly Operating Income", "area", "SELECT CAST(MONTH_START AS VARCHAR) AS MONTH_START, COMPANY, REVENUE, EXPENSE, NET_OPERATING_INCOME FROM VW_LAKEHOUSE_EXEC_PNL LIMIT 36", [["2026-09-01", "Maple Tech Manufacturing", 284500, 142100, 142400], ["2026-10-01", "Northstar Cloud Services", 198200, 88400, 109800]]),
                ("q-lake-rev-cohorts", "Customer Cohort Active Accounts & Open AR", "bar", "SELECT CUSTOMER_GROUP, TERRITORY, SUM(ACTIVE_CUSTOMERS) AS COHORT_ACCOUNTS, SUM(NET_REVENUE) AS NET_REV FROM MART_REVENUE_COHORTS GROUP BY 1, 2", [["Enterprise Industrial", "North America", 192, 4920000], ["SaaS Subscribers", "North America", 144, 2180000]]),
                ("q-lake-gov-catalog", "Ingested data-gov-in Public CSV Datasets", "table", "SELECT TABLE_NAME, COLUMN_COUNT, ROW_COUNT FROM GOV_IN_DATASET_CATALOG ORDER BY ROW_COUNT DESC", [["GOV_IN_ACTIVITYWISE_CLASSIFICATION_OF_BUDGE", 7, 42]]),
            ],
        },
    ]

    q_count = 0
    d_count = 0
    dep_count = 0
    effect_count = 0
    first_question_ids: list[tuple[str, str]] = []
    first_dashboard_ids: list[tuple[str, str]] = []

    for bp_idx, bp in enumerate(dashboard_blueprints):
        pkey = bp["project_key"]
        puuid = projects_by_key[pkey]
        ep_id = bp["endpoint_id"]

        q_cards = []
        q_ids_for_dash: list[str] = []

        for q_idx, (q_key, q_title, v_type, sql_text, raw_prev_rows) in enumerate(bp["questions"]):
            prev_rows = [
                [
                    " · ".join(str(x) for x in r if isinstance(x, str)) or f"Row {i + 1}",
                    float(next((x for x in r if isinstance(x, (int, float))), 0)),
                ]
                for i, r in enumerate(raw_prev_rows)
            ]
            donor_ref = donor_chart_names[(bp_idx * 3 + q_idx) % max(1, len(donor_chart_names))] if donor_chart_names else q_title
            q_model = default_question_model(
                q_title,
                endpoint_id=ep_id,
                raw_sql=sql_text,
                visualization={"type": v_type},
                preview_rows=prev_rows,
            )
            q_ddn = question_to_ddn(q_model)
            q_did = _upsert_design_with_versions(
                dconn,
                project_key=pkey,
                design_key=q_key,
                kind="question",
                title=q_title,
                versions=[(1, None, "accepted", q_ddn[0] if isinstance(q_ddn, tuple) else q_ddn, f"Derived from Frappe chart pattern: {donor_ref}")],
                active_version=1,
                user_id=user_id,
                now_iso=now_iso,
            )
            q_ids_for_dash.append(q_did)
            first_question_ids.append((q_did, q_title))
            q_count += 1

            _upsert_validated_asset(
                cconn,
                project_key=pkey,
                project_uuid=puuid,
                user_id=user_id,
                asset_key=q_did,
                request_payload={
                    "asset_type": "cdeadmin.design.question",
                    "schema_name": "cdeadmin.design.question",
                    "schema_version": 1,
                    "name": q_title,
                    "path": f"reports/graphs/{q_key}.bi.ddn",
                    "expected_version": 0,
                    "content": {"design_id": q_did, "endpoint_id": ep_id},
                    "metadata": {"report_category": "graphs", "donor_chart_reference": donor_ref},
                    "dependency_references": [],
                    "resource_bindings": [],
                    "validation_state": "valid",
                    "validation_details": [],
                },
                now_sql=now_sql,
            )

            q_cards.append({
                "id": f"card_{q_idx + 1}",
                "tab_id": "overview" if q_idx < 2 else "details",
                "type": "question",
                "title": q_title,
                "click_behavior": "cross_filter" if q_idx == 0 else "inherit",
                "layout": {
                    "x": (q_idx % 2) * 12 if q_idx < 2 else 0,
                    "y": 0 if q_idx < 2 else 9,
                    "w": 12 if q_idx < 2 else 24,
                    "h": 8,
                },
                "question": {
                    "question_design_id": q_did,
                    "pinned_version": 1,
                    "follow_latest_accepted": True,
                },
                "visualization": {"type": v_type, "settings": {}},
                "preview_rows": prev_rows,
            })

        # Add header markdown summary card + optional static metric_panel snapshot card (owner rule 2026-11-10!)
        q_cards.insert(0, {
            "id": "card_exec_banner",
            "tab_id": "overview",
            "type": "text",
            "title": "Executive Governance Banner",
            "click_behavior": "none",
            "layout": {"x": 0, "y": 0, "w": 24, "h": 3},
            "text": {
                "markdown": f"### {bp['title']}\nBacked by governed **DDN `panels.composed@1`** cards with personal filter scope and cross-filtering.",
            },
        })
        for c in q_cards[1:]:
            if c["tab_id"] == "overview":
                c["layout"]["y"] += 3

        if bp.get("include_static_metric_panel"):
            q_cards.append({
                "id": "card_boat_static_snapshot",
                "tab_id": "details",
                "type": "metric_panel",
                "title": "Boat Hypervisor Baseline Snapshot (Static Collector Capture)",
                "click_behavior": "none",
                "layout": {"x": 0, "y": 17, "w": 24, "h": 6},
                "metric_panel": {
                    "panel_id": "boat_vm_snapshot",
                    "snapshot_mode": "static",
                    "columns": [
                        {"id": "measure", "label": "Hypervisor Metric"},
                        {"id": "value", "label": "Captured Baseline"},
                    ],
                    "rows": [
                        ["vm-bench-ca-01 vCPU / RAM", "8 vCPU / 16 GiB (Running)"],
                        ["vm-bench-us-02 Wake-on-SYN", "4 vCPU / 8 GiB (Sleeping -> SYN Armed)"],
                        ["Firebird ODS 13.1 Page Cache", "32 KB pages, Forced Writes SYNC"],
                    ],
                },
            })

        dash_raw = validate_bi_dashboard({
            "name": bp["title"],
            "description": f"Composed multi-tab BI dashboard for project {pkey}.",
            "tabs": [
                {"id": "overview", "name": "Executive Overview"},
                {"id": "details", "name": "Operational Drill-Down"},
            ],
            "cards": q_cards,
            "filters": bp["filters"],
            "links": [{
                "id": "drill_primary",
                "card_id": "card_1",
                "kind": "drill_through",
                "target_design_id": q_ids_for_dash[-1],
                "carry_filter_context": True,
                "field_map": {"COMPANY": "company"},
            }],
            "interaction": {
                "default_click_behavior": "cross_filter",
                "auto_apply_filters": True,
                "filter_state_scope": "personal",
            },
        })
        d_v1_ddn, d_id_map = dashboard_to_ddn(dash_raw)

        dash_versions: list[tuple[int, int | None, str, str, str]] = [
            (1, None, "accepted", d_v1_ddn, "Accepted v1.0 executive dashboard composition"),
        ]
        if bp["multi_version"]:
            dash_v2_raw = copy.deepcopy(dash_raw)
            dash_v2_raw["description"] += " [v2 In-Review: added Q4 variance commentary]"
            d_v2_ddn, _ = dashboard_to_ddn(
                dash_v2_raw, element_ids=d_id_map, dashboard_notes="In-review Q4 board pack adjustments"
            )
            dash_v3_raw = copy.deepcopy(dash_v2_raw)
            dash_v3_raw["interaction"]["default_click_behavior"] = "highlight"
            d_v3_ddn, _ = dashboard_to_ddn(
                dash_v3_raw, element_ids=d_id_map, dashboard_notes="Draft highlight-mode UX experiment"
            )
            dash_versions.append((2, 1, "in_review", d_v2_ddn, "Added Q4 board review annotations"))
            dash_versions.append((3, 2, "draft", d_v3_ddn, "Testing highlight interaction mode"))

        d_did = _upsert_design_with_versions(
            dconn,
            project_key=pkey,
            design_key=bp["dash_key"],
            kind="dashboard",
            title=bp["title"],
            versions=dash_versions,
            active_version=1,
            user_id=user_id,
            now_iso=now_iso,
        )
        first_dashboard_ids.append((d_did, bp["title"]))
        d_count += 1

        # Record design_dependency links (dashboard -> each question) so Cross-Design Where-Used shines!
        for q_did in q_ids_for_dash:
            dconn.execute(
                """
                INSERT OR IGNORE INTO design_dependency (
                  design_id, version, depends_on_design_id, depends_on_version
                ) VALUES (?, 1, ?, 1)
                """,
                (d_did, q_did),
            )
            dep_count += 1

        # Reviewed outward effects in designs.db (separate reviewed switches per owner rule 2026-11-10)
        dconn.execute("DELETE FROM bi_outward_effect WHERE design_id = ?", (d_did,))
        for eff_kind, eff_enabled, pub_uid, cfg in [
            ("subscription", 1 if bp_idx < 4 else 0, None, {"cadence": "daily_0700", "channel": "finance-digest"}),
            ("embed", 1 if bp_idx < 3 else 0, None, {"locked_domain": "portal.mapletech.cloud", "narrow_only": True}),
            ("dashboard_server", 1 if bp_idx in (0, 10, 11) else 0, user_id if bp_idx in (0, 10, 11) else None, {"wallboard_mode": "display_only", "refresh_seconds": 300}),
        ]:
            dconn.execute(
                """
                INSERT INTO bi_outward_effect (
                  id, design_id, version, effect_kind, enabled,
                  publisher_user_id, reviewed_by, reviewed_at,
                  config_json, exposure_diff_json
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid7(),
                    d_did,
                    eff_kind,
                    eff_enabled,
                    pub_uid,
                    user_id,
                    now_iso,
                    json.dumps({**cfg, "enabled": bool(eff_enabled)}),
                    json.dumps({"effect_kind": eff_kind, "transition": "reviewed_seed"}),
                ),
            )
            effect_count += 1

        _upsert_validated_asset(
            cconn,
            project_key=pkey,
            project_uuid=puuid,
            user_id=user_id,
            asset_key=d_did,
            request_payload={
                "asset_type": "cdeadmin.design.dashboard",
                "schema_name": "cdeadmin.design.dashboard",
                "schema_version": 1,
                "name": bp["title"],
                "path": f"reports/graphs/{bp['dash_key']}.dashboard.ddn",
                "expected_version": 0,
                "content": {"design_id": d_did, "question_count": len(q_ids_for_dash)},
                "metadata": {"report_category": "graphs", "profile": "panels.composed@1"},
                "dependency_references": [
                    {"schema": "cdeadmin.asset-ref.v1", "projectId": pkey, "assetId": qid}
                    for qid in q_ids_for_dash
                ],
                "resource_bindings": [],
                "validation_state": "valid",
                "validation_details": [],
            },
            now_sql=now_sql,
        )

    # Seed runtime cde_bi_alert & cde_bi_embed rows in cdeadmin.db
    cconn.execute("DELETE FROM cde_bi_alert WHERE name LIKE 'Frappe Showcase:%'")
    cconn.execute("DELETE FROM cde_bi_embed WHERE name LIKE 'Frappe Showcase:%'")
    alert_specs = [
        ("alert", "Frappe Showcase: Overdue AR > $40k Threshold", first_question_ids[3][0], "breach", '{"metric":"OPEN_RECEIVABLE_TOTAL","operator":"gt","threshold":40000}'),
        ("alert", "Frappe Showcase: Helpdesk Failed SLA Spike", first_question_ids[25][0], "ok", '{"metric":"FAILED_TICKETS","operator":"gt","threshold":200}'),
        ("subscription", "Frappe Showcase: Daily CFO Trial Balance Digest", first_question_ids[0][0], "ok", '{"cadence":"daily_0700","channel":"finance-digest"}'),
    ]
    for a_kind, a_name, q_id, b_state, a_def in alert_specs:
        cconn.execute(
            """
            INSERT INTO cde_bi_alert (
              id, user_id, endpoint_id, kind, name, resource_type, resource_id,
              resource_revision, status, breach_state, pending_notify,
              consecutive_failures, schedule_anchor, revision, definition,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'question', ?, 1, 'active', ?, 0, 0, ?, 1, ?, ?, ?)
            """,
            (str(uuid.uuid4()), user_id, fb_ep, a_kind, a_name, q_id, b_state, now_sql, a_def, now_sql, now_sql),
        )

    embed_specs = [
        ("Frappe Showcase: Executive Board Portal Signed Embed", first_dashboard_ids[0][0], '{"locked_filters":{"company":"Maple Tech Manufacturing"},"theme":"corporate"}'),
        ("Frappe Showcase: Shop-Floor Wallboard Display Embed", first_dashboard_ids[5][0], '{"locked_filters":{},"kiosk_mode":true}'),
        ("Frappe Showcase: NOC Cargo Telemetry Status Embed", first_dashboard_ids[10][0], '{"locked_filters":{"resource_id":"cargo:prod-bench-01"}}'),
    ]
    for e_name, d_id, e_def in embed_specs:
        cconn.execute(
            """
            INSERT INTO cde_bi_embed (
              id, user_id, endpoint_id, name, resource_type, resource_id,
              resource_revision, status, revision, definition, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'dashboard', ?, 1, 'enabled', 1, ?, ?, ?)
            """,
            (str(uuid.uuid4()), user_id, fb_ep, e_name, d_id, e_def, now_sql, now_sql),
        )

    return {
        "bi_questions_seeded": q_count,
        "composed_dashboards_seeded": d_count,
        "design_dependencies_recorded": dep_count,
        "reviewed_outward_effects": effect_count,
        "runtime_bi_alerts": len(alert_specs),
        "runtime_bi_embeds": len(embed_specs),
    }


def seed_pillar_4_erd_lifecycle_and_deployments(
    dconn: sqlite3.Connection,
    *,
    endpoints: dict[str, dict[str, str]],
    user_id: int,
    now_iso: str,
) -> dict[str, int]:
    """Evolve flagship ERDs & Screen Meshes to v1 Accepted -> v2 In Review -> v3 Draft + target_deployment matrix."""
    flagship_keys = [
        ("erpnext-acc-general-ledger", "erpnext-acc-general-ledger-erd"),
        ("erpnext-acc-receivables", "erpnext-acc-receivables-erd"),
        ("erpnext-stock-ledger", "erpnext-stock-ledger-erd"),
        ("hrms-payroll-tax", "hrms-payroll-tax-erd"),
        ("frappe-crm", "frappe-crm-erd"),
        ("datum-cargo-telemetry", "datum-cargo-telemetry-erd"),
    ]
    evolved = 0
    deployments = 0
    acceptances = 0

    # Backfill acceptance records for all accepted v1 designs that don't yet have one
    accepted_rows = dconn.execute(
        """
        SELECT dv.design_id, dv.version, d.key
        FROM design_version dv
        JOIN design d ON d.id = dv.design_id
        LEFT JOIN acceptance a ON a.design_id = dv.design_id AND a.version = dv.version
        WHERE dv.status = 'accepted' AND a.design_id IS NULL
        """
    ).fetchall()
    for did, ver, dkey in accepted_rows:
        dconn.execute(
            """
            INSERT OR IGNORE INTO acceptance (
              design_id, version, accepted_by, accepted_at, approval_ref
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (did, ver, user_id, now_iso, f"git:refs/reviews/{dkey}/v{ver}"),
        )
        acceptances += 1

    for pkey, dkey in flagship_keys:
        row = dconn.execute(
            "SELECT id, title FROM design WHERE project_id = ? AND key = ?",
            (pkey, dkey),
        ).fetchone()
        if not row:
            continue
        did, _ = row
        v1_row = dconn.execute(
            "SELECT ddn_text FROM design_version WHERE design_id = ? AND version = 1",
            (did,),
        ).fetchone()
        if not v1_row:
            continue
        v1_ddn = v1_row[0]

        dconn.execute("DELETE FROM design_version WHERE design_id = ? AND version > 1", (did,))
        v2_ddn = (
            v1_ddn.rstrip()
            + "\n\n// Checkpoint v2 (in_review): Added cross-border tax withholding & FX audit attributes\n"
        )
        v3_ddn = (
            v2_ddn.rstrip()
            + "\n// Checkpoint v3 (draft): Staged polyglot DuckDB analytical replica & CDC watermark columns\n"
        )
        dconn.execute(
            """
            INSERT INTO design_version (
              design_id, version, base_version, status, ddn_text, ddn_sha256,
              dialect_version, note, actor_id, saved_at, origin
            ) VALUES (?, 2, 1, 'in_review', ?, ?, 'ddn-next-1', ?, ?, ?, 'local')
            """,
            (did, v2_ddn, _sha256(v2_ddn), "v2 In-Review: added FX & withholding audit metadata", user_id, now_iso),
        )
        dconn.execute(
            """
            INSERT INTO design_version (
              design_id, version, base_version, status, ddn_text, ddn_sha256,
              dialect_version, note, actor_id, saved_at, origin
            ) VALUES (?, 3, 2, 'draft', ?, ?, 'ddn-next-1', ?, ?, ?, 'local')
            """,
            (did, v3_ddn, _sha256(v3_ddn), "v3 Draft: staged DuckDB lakehouse & CDC sync columns", user_id, now_iso),
        )
        dconn.execute(
            "UPDATE design SET active_version = 1, head_version = 3, updated_at = ? WHERE id = ?",
            (now_iso, did),
        )
        evolved += 1

        # Record multi-engine target_deployment matrix entries (Firebird + SQLite Edge + DuckDB Lakehouse)
        dconn.execute("DELETE FROM target_deployment WHERE design_id = ?", (did,))
        for eng_name in ("firebird", "sqlite", "duckdb"):
            if eng_name not in endpoints:
                continue
            ep_info = endpoints[eng_name]
            dconn.execute(
                """
                INSERT INTO target_deployment (
                  design_id, engine, endpoint_id, database_target_id,
                  deployed_version, plan_sha256, target_fingerprint,
                  applied_by, applied_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    did,
                    eng_name,
                    ep_info["endpoint_id"],
                    ep_info["target_id"],
                    _sha256(f"plan:{did}:{eng_name}:v1"),
                    _sha256(f"catalog:{ep_info['database']}:v1"),
                    user_id,
                    now_iso,
                ),
            )
            deployments += 1

    return {
        "flagship_erd_multi_version_chains": evolved,
        "acceptance_records_backfilled": acceptances,
        "cross_engine_target_deployments": deployments,
    }


def seed_pillar_5_all_13_platform_modules(
    cconn: sqlite3.Connection,
    *,
    projects_by_key: dict[str, str],
    endpoints: dict[str, dict[str, str]],
    user_id: int,
    now_sql: str,
) -> dict[str, int]:
    """Seed validated assets across all 13 CDEadmin platform modules!"""
    fb = endpoints["firebird"]
    sq = endpoints.get("sqlite", fb)
    dk = endpoints.get("duckdb", fb)

    fb_db_ref = _resource_ref("firebird", fb["endpoint_id"], fb["target_id"], "database", "frappe_suite.fdb")
    sq_db_ref = _resource_ref("sqlite", sq["endpoint_id"], sq["target_id"], "database", "frappe_books_edge.sqlite")
    dk_db_ref = _resource_ref("duckdb", dk["endpoint_id"], dk["target_id"], "database", "frappe_lakehouse.duckdb")

    fb_gl_ref = _resource_ref("firebird", fb["endpoint_id"], fb["target_id"], "table", "GL_ENTRY")
    fb_sinv_ref = _resource_ref("firebird", fb["endpoint_id"], fb["target_id"], "table", "SALES_INVOICE")
    fb_sle_ref = _resource_ref("firebird", fb["endpoint_id"], fb["target_id"], "table", "STOCK_LEDGER_ENTRY")
    fb_hd_ref = _resource_ref("firebird", fb["endpoint_id"], fb["target_id"], "table", "HD_TICKET")
    fb_traces_ref = _resource_ref("firebird", fb["endpoint_id"], fb["target_id"], "table", "DATUM_TRACES")
    sq_sinv_ref = _resource_ref("sqlite", sq["endpoint_id"], sq["target_id"], "table", "SALES_INVOICE")
    dk_gl_ref = _resource_ref("duckdb", dk["endpoint_id"], dk["target_id"], "table", "MART_GL_MONTHLY")

    counts_by_module: dict[str, int] = {}

    def bump(mod: str) -> None:
        counts_by_module[mod] = counts_by_module.get(mod, 0) + 1

    # 1. Schema Comparison (cdeadmin.schema_compare.v1) — 3 cross-engine comparisons!
    for pkey, akey, title, left_r, right_r, ddl_stmt in [
        (
            "erpnext-acc-general-ledger",
            "compare-firebird-vs-duckdb-gl",
            "Cross-Engine Schema Comparison: Firebird ERP <-> DuckDB Lakehouse",
            fb_db_ref,
            dk_db_ref,
            "ALTER TABLE SALES_INVOICE ADD COLUMN LAKEHOUSE_COHORT_TAG VARCHAR;",
        ),
        (
            "books-desktop-ledger",
            "compare-sqlite-edge-vs-firebird-erp",
            "Cross-Engine Schema Comparison: SQLite POS Edge <-> Firebird 5.0 ERP",
            sq_db_ref,
            fb_db_ref,
            "ALTER TABLE SALES_INVOICE ADD EDGE_TERMINAL_ID VARCHAR(40);",
        ),
        (
            "collab-insights",
            "compare-sqlite-edge-vs-duckdb-lakehouse",
            "Cross-Engine Schema Comparison: SQLite Edge <-> DuckDB Analytical Marts",
            sq_db_ref,
            dk_db_ref,
            "CREATE TABLE IF NOT EXISTS POS_SYNC_AUDIT (OUTBOX_ID BIGINT, SYNC_TS TIMESTAMP);",
        ),
    ]:
        _upsert_validated_asset(
            cconn,
            project_key=pkey,
            project_uuid=projects_by_key[pkey],
            user_id=user_id,
            asset_key=akey,
            request_payload={
                "asset_type": "cdeadmin.schema_compare.v1",
                "name": title,
                "path": f"comparisons/{akey}.json",
                "schema_name": "cdeadmin.schema_compare.v1",
                "schema_version": 1,
                "expected_version": 0,
                "content": {
                    "schema": "cdeadmin.schema-compare.asset.v1",
                    "schemaVersion": 1,
                    "moduleId": "cdeadmin.schema_compare",
                    "leftRef": left_r,
                    "rightRef": right_r,
                    "options": {"compareIndexes": True, "compareForeignKeys": True},
                    "acceptedMappings": [],
                    "ignoredDiffs": [],
                    "comparisonResultRef": None,
                    "changePlan": {
                        "schema": "cdeadmin.schema-compare.change-plan.v1",
                        "targetSide": "right",
                        "targetRef": right_r,
                        "operations": [{
                            "id": "op:align-1",
                            "action": "alter",
                            "risk": "low",
                            "dependencies": [],
                            "nativeStatement": ddl_stmt,
                        }],
                    },
                },
                "metadata": {"moduleId": "cdeadmin.schema_compare"},
                "dependency_references": [],
                "resource_bindings": [left_r, right_r],
                "validation_state": "valid",
                "validation_details": [],
            },
            now_sql=now_sql,
        )
        bump("cdeadmin.schema_compare.v1")

    # 2. Data Quality Suites (cdeadmin.quality.v1) — 3 governed rule suites!
    for pkey, akey, title, target_r, col_name, doc_note in [
        (
            "erpnext-acc-general-ledger",
            "quality-gl-double-entry-integrity",
            "General Ledger Double-Entry & Account Completeness Rules",
            fb_gl_ref,
            "ACCOUNT",
            "Every posted GL_ENTRY must carry a valid CoA ACCOUNT and Fiscal Year.",
        ),
        (
            "erpnext-acc-receivables",
            "quality-sales-invoice-completeness",
            "Sales Invoice Customer & Receivable Quality Gate",
            fb_sinv_ref,
            "CUSTOMER",
            "Submitted invoices must reference a governed CUSTOMER master record.",
        ),
        (
            "erpnext-stock-ledger",
            "quality-stock-valuation-guard",
            "Stock Ledger Item & Warehouse Completeness Suite",
            fb_sle_ref,
            "ITEM_CODE",
            "Stock movements must bind to a catalog ITEM_CODE and physical WAREHOUSE.",
        ),
    ]:
        _upsert_validated_asset(
            cconn,
            project_key=pkey,
            project_uuid=projects_by_key[pkey],
            user_id=user_id,
            asset_key=akey,
            request_payload={
                "asset_type": "cdeadmin.quality.v1",
                "name": title,
                "path": f"quality/{akey}.json",
                "schema_name": "cdeadmin.quality.v1",
                "schema_version": 1,
                "expected_version": 0,
                "content": {
                    "schema": "cdeadmin.quality.asset.v1",
                    "schemaVersion": 1,
                    "moduleId": "cdeadmin.quality",
                    "name": title,
                    "owner": "finance-data-stewards",
                    "tags": ["frappe", "governed", pkey],
                    "rules": [{
                        "schema": "cdeadmin.quality-rule.v1",
                        "id": f"rule-{col_name.lower()}-nn",
                        "name": f"{col_name} is populated",
                        "type": "not_null",
                        "dimension": "completeness",
                        "scope": None,
                        "parameters": {"column": col_name},
                        "threshold": {"operator": ">=", "value": 1.0},
                        "ratio": True,
                        "severity": "critical",
                        "evaluationMode": "exact",
                        "enabled": True,
                        "generatedSuggestion": False,
                        "sourceSampleRef": {"schema": "cdeadmin.external-ref.v1", "id": f"sample:{akey}:v1"},
                        "sourceRevision": "ods:13.1:frappe_suite",
                        "actionIds": ["block-close"],
                        "documentation": doc_note,
                        "nativeDetails": {"catalog": "RDB$RELATION_FIELDS"},
                    }],
                    "parameters": {"checkpoint": "period_close"},
                    "defaultScope": {
                        "schema": "cdeadmin.quality-data-slice.v1",
                        "id": f"slice-{akey}",
                        "resourceRef": target_r,
                        "partition": None,
                        "window": None,
                        "filter": {"DOCSTATUS": 1},
                        "samplePolicy": {"mode": "random_n", "limit": 1000},
                        "nativeDetails": {},
                    },
                    "severityPolicy": {"weights": {"info": 1, "warning": 2, "critical": 5}},
                    "schedule": {"cron": "0 3 * * *", "timezone": "UTC"},
                    "actions": [{
                        "schema": "cdeadmin.quality-action.v1",
                        "id": "block-close",
                        "type": "block",
                        "label": "Block Period Close",
                        "severities": ["critical"],
                        "enabled": True,
                        "parameters": {"gate": "accounting_close"},
                    }],
                    "baselineRefs": [{"schema": "cdeadmin.external-ref.v1", "id": f"baseline:{akey}"}],
                },
                "metadata": {"moduleId": "cdeadmin.quality"},
                "dependency_references": [],
                "resource_bindings": [target_r],
                "validation_state": "valid",
                "validation_details": [],
            },
            now_sql=now_sql,
        )
        bump("cdeadmin.quality.v1")

    # 3. Data Contracts (cdeadmin.contract.v1) — ODCS-aligned contracts linked to quality suites!
    for pkey, akey, qkey, title, domain, target_r, elem_id in [
        (
            "erpnext-acc-general-ledger",
            "contract-certified-general-ledger",
            "quality-gl-double-entry-integrity",
            "Certified General Ledger Financial Postings Contract",
            "finance",
            fb_gl_ref,
            "gl_entry",
        ),
        (
            "erpnext-acc-receivables",
            "contract-commercial-sales-invoices",
            "quality-sales-invoice-completeness",
            "Commercial Sales Invoice & Receivables SLA Contract",
            "commercial",
            fb_sinv_ref,
            "sales_invoice",
        ),
    ]:
        q_ref = {"schema": "cdeadmin.asset-ref.v1", "projectId": pkey, "assetId": qkey}
        _upsert_validated_asset(
            cconn,
            project_key=pkey,
            project_uuid=projects_by_key[pkey],
            user_id=user_id,
            asset_key=akey,
            request_payload={
                "asset_type": "cdeadmin.contract.v1",
                "name": title,
                "path": f"contracts/{akey}.json",
                "schema_name": "cdeadmin.contract.v1",
                "schema_version": 1,
                "expected_version": 0,
                "content": {
                    "schema": "cdeadmin.contract.asset.v1",
                    "schemaVersion": 1,
                    "moduleId": "cdeadmin.contract",
                    "contractVersion": "1.0.0",
                    "status": "active",
                    "name": title,
                    "domain": domain,
                    "description": f"Authoritative ODCS v3.1 data contract for {elem_id.upper()} across OLTP and Lakehouse.",
                    "elements": [{
                        "schema": "cdeadmin.contract-element.v1",
                        "id": elem_id,
                        "name": elem_id.upper(),
                        "logicalType": "table",
                        "parentId": None,
                        "description": f"Governed {elem_id.upper()} relation",
                        "required": True,
                        "classification": "internal",
                        "constraints": {"balancedDoubleEntry": True},
                        "physicalDefinition": {"engine": "firebird", "table": elem_id.upper()},
                        "authoritativeDefinitionRefs": [],
                        "extensions": {},
                    }],
                    "bindings": [{
                        "schema": "cdeadmin.contract-binding.v1",
                        "id": f"{elem_id}-prod",
                        "elementId": elem_id,
                        "targetRef": target_r,
                        "environment": "production",
                        "bindingStatus": "observed",
                        "observedRevision": "ods:13.1",
                        "nativeDetails": {"pageSize": 32768},
                    }],
                    "qualityObligations": [{
                        "schema": "cdeadmin.contract-quality-obligation.v1",
                        "id": f"qo-{elem_id}",
                        "elementId": elem_id,
                        "qualityRef": q_ref,
                        "importedDefinition": None,
                        "severity": "critical",
                        "threshold": {"maximumFailures": 0},
                        "description": "Zero critical completeness violations permitted",
                        "extensions": {},
                    }],
                    "sla": [{
                        "schema": "cdeadmin.contract-service-level.v1",
                        "id": "freshness-sla",
                        "measure": "freshness",
                        "target": 15,
                        "comparison": "<=",
                        "unit": "minutes",
                        "window": {"rolling": "1h"},
                        "elementId": elem_id,
                        "description": "Ledger postings replicated to Lakehouse within 15 minutes",
                        "extensions": {},
                    }],
                    "team": [{
                        "schema": "cdeadmin.contract-team-role.v1",
                        "id": "steward",
                        "name": "Financial Data Steward",
                        "principalRefs": [{"schema": "cdeadmin.external-ref.v1", "id": "team:finance-controllers"}],
                        "responsibilities": ["publish", "approve_schema_change"],
                        "accessExpectations": [],
                        "support": {"channel": "#erpnext-acc-general-ledger"},
                        "extensions": {},
                    }],
                    "roles": [],
                    "servers": [{
                        "schema": "cdeadmin.contract-server-binding.v1",
                        "id": "fb-prod",
                        "providerId": "firebird",
                        "environment": "production",
                        "interface": "firebird-wire-v16",
                        "resourceRef": target_r,
                        "apiRef": None,
                        "nativeDetails": {},
                    }],
                    "authoritativeDefinitions": [{
                        "schema": "cdeadmin.contract-authoritative-definition.v1",
                        "id": "ifrs-coa",
                        "type": "business_glossary",
                        "uri": "https://docs.frappe.example/contracts/ledger",
                        "assetRef": None,
                        "description": "Multi-company IFRS & GAAP ledger posting standard",
                        "extensions": {},
                    }],
                    "extensions": {},
                },
                "metadata": {"moduleId": "cdeadmin.contract"},
                "dependency_references": [q_ref],
                "resource_bindings": [target_r],
                "validation_state": "valid",
                "validation_details": [],
            },
            now_sql=now_sql,
        )
        bump("cdeadmin.contract.v1")

    # 4. End-to-End Field Lineage (cdeadmin.lineage.v1)
    for pkey, akey, title, src_r, dst_r, src_f, dst_f in [
        (
            "erpnext-acc-general-ledger",
            "lineage-order-to-gl-to-lakehouse",
            "Field Lineage: SALES_INVOICE -> Firebird GL_ENTRY -> DuckDB MART_GL_MONTHLY",
            fb_sinv_ref,
            dk_gl_ref,
            "SALES_INVOICE.GRAND_TOTAL",
            "MART_GL_MONTHLY.TOTAL_DEBIT",
        ),
        (
            "books-desktop-ledger",
            "lineage-pos-edge-to-core-erp",
            "Field Lineage: SQLite POS Edge SALES_INVOICE -> Firebird Core SALES_INVOICE",
            sq_sinv_ref,
            fb_sinv_ref,
            "SALES_INVOICE.GRAND_TOTAL",
            "SALES_INVOICE.GRAND_TOTAL",
        ),
    ]:
        ev = {
            "schema": "cdeadmin.lineage-evidence.v1",
            "id": f"ev-{akey}",
            "origin": "user_curated",
            "confidence": 1,
            "capturedAt": "2026-11-15T18:00:00Z",
            "validFrom": None,
            "validTo": None,
            "stale": False,
            "providerVersion": "5.0.4",
            "reference": src_r,
            "details": {"review": "accepted"},
        }
        _upsert_validated_asset(
            cconn,
            project_key=pkey,
            project_uuid=projects_by_key[pkey],
            user_id=user_id,
            asset_key=akey,
            request_payload={
                "asset_type": "cdeadmin.lineage.v1",
                "name": title,
                "path": f"lineage/{akey}.json",
                "schema_name": "cdeadmin.lineage.v1",
                "schema_version": 1,
                "expected_version": 0,
                "content": {
                    "schema": "cdeadmin.lineage.asset.v1",
                    "schemaVersion": 1,
                    "moduleId": "cdeadmin.lineage",
                    "scopeRefs": [src_r, dst_r],
                    "sourcePolicies": [{
                        "id": "polyglot-curated",
                        "sourcePriority": ["provider_declared", "user_curated"],
                        "inferenceEnabled": True,
                        "retentionDays": 90,
                        "providerId": "firebird",
                    }],
                    "savedFilters": {"origin": "user_curated"},
                    "layoutPreferences": {"mode": "graph"},
                    "curatedEdges": [{
                        "schema": "cdeadmin.lineage-edge.v1",
                        "id": f"edge-{akey}",
                        "from": src_r["canonical"],
                        "to": dst_r["canonical"],
                        "type": "derives",
                        "origin": "user_curated",
                        "confidence": 1,
                        "validFrom": None,
                        "validTo": None,
                        "evidence": [ev],
                        "fieldLineage": [{
                            "schema": "cdeadmin.field-lineage.v1",
                            "id": f"fl-{akey}",
                            "sourceField": src_f,
                            "targetField": dst_f,
                            "transformation": "AGGREGATE" if "MART_" in dst_f else "DIRECT_IDENTITY",
                            "expressionRef": None,
                            "evidenceIds": [ev["id"]],
                            "nativeDetails": {},
                        }],
                        "presentationState": "confirmed",
                        "suppressed": False,
                        "nativeDetails": {},
                    }],
                    "suppressedInferenceRules": [],
                    "snapshotRefs": [{"schema": "cdeadmin.external-ref.v1", "id": f"lineage-snap:{akey}"}],
                },
                "metadata": {"moduleId": "cdeadmin.lineage"},
                "dependency_references": [],
                "resource_bindings": [src_r, dst_r],
                "validation_state": "valid",
                "validation_details": [],
            },
            now_sql=now_sql,
        )
        bump("cdeadmin.lineage.v1")

    # 5. Cross-Engine ETL Pipelines (cdeadmin.etl.v1) — SQLite -> Firebird & Firebird -> DuckDB!
    for pkey, akey, title, desc, src_r, sink_r in [
        (
            "books-desktop-ledger",
            "etl-sqlite-pos-outbox-to-firebird",
            "ETL Pipeline: SQLite Retail POS Outbox -> Firebird 5.0 Core ERP",
            "Syncs offline store POS invoices and GL postings from SQLite Edge into Firebird 5.0.",
            sq_sinv_ref,
            fb_sinv_ref,
        ),
        (
            "collab-insights",
            "etl-firebird-gl-to-duckdb-lakehouse",
            "ETL Pipeline: Firebird GL_ENTRY -> DuckDB MART_GL_MONTHLY Star Mart",
            "Incremental analytical rollup from Firebird 5.0 OLTP ledger into DuckDB columnar lakehouse.",
            fb_gl_ref,
            dk_gl_ref,
        ),
    ]:
        f_spec = {
            "schema": "cdeadmin.etl-schema-field.v1",
            "id": "doc_name",
            "name": "DOC_NAME",
            "nativeType": "VARCHAR(140)",
            "semanticType": "string",
            "nullable": False,
            "precision": None,
            "scale": None,
            "timezone": None,
            "encoding": "UTF-8",
            "path": None,
            "nativeDetails": {},
        }
        _upsert_validated_asset(
            cconn,
            project_key=pkey,
            project_uuid=projects_by_key[pkey],
            user_id=user_id,
            asset_key=akey,
            request_payload={
                "asset_type": "cdeadmin.etl.v1",
                "name": title,
                "path": f"etl/{akey}.json",
                "schema_name": "cdeadmin.etl.v1",
                "schema_version": 1,
                "expected_version": 0,
                "content": {
                    "schema": "cdeadmin.etl.asset.v1",
                    "schemaVersion": 1,
                    "moduleId": "cdeadmin.etl",
                    "name": title,
                    "description": desc,
                    "mode": "batch",
                    "parameters": [{
                        "schema": "cdeadmin.etl-parameter.v1",
                        "id": "svc_cred",
                        "name": "Endpoint Service Credential",
                        "type": "credential",
                        "required": True,
                        "secret": True,
                        "default": None,
                        "credentialRef": {"schema": "cdeadmin.credential-ref.v1", "scheme": "keyring", "id": f"cred-{akey}"},
                        "description": "Managed endpoint keyring reference",
                        "nativeDetails": {},
                    }],
                    "nodes": [
                        {
                            "schema": "cdeadmin.etl-node.v1",
                            "id": "source",
                            "name": "Source Table",
                            "kind": "source",
                            "config": {},
                            "resourceRef": src_r,
                            "ports": [{
                                "schema": "cdeadmin.etl-port.v1",
                                "id": "out",
                                "name": "out",
                                "direction": "output",
                                "mode": "batch",
                                "schemaState": "known",
                                "schemaRef": None,
                                "fields": [f_spec],
                                "cardinality": None,
                                "ordering": [],
                                "partitioning": {},
                                "watermark": {},
                                "nativeDetails": {},
                            }],
                            "capabilityRequirements": ["batch_read"],
                            "executionPreference": "source_pushdown",
                            "errorRoute": None,
                            "checkpointEnabled": True,
                            "nativeDetails": {},
                        },
                        {
                            "schema": "cdeadmin.etl-node.v1",
                            "id": "sink",
                            "name": "Target Mart",
                            "kind": "sink",
                            "config": {},
                            "resourceRef": sink_r,
                            "ports": [{
                                "schema": "cdeadmin.etl-port.v1",
                                "id": "in",
                                "name": "in",
                                "direction": "input",
                                "mode": "batch",
                                "schemaState": "known",
                                "schemaRef": None,
                                "fields": [f_spec],
                                "cardinality": None,
                                "ordering": [],
                                "partitioning": {},
                                "watermark": {},
                                "nativeDetails": {},
                            }],
                            "capabilityRequirements": ["batch_write"],
                            "executionPreference": "target_pushdown",
                            "errorRoute": {
                                "schema": "cdeadmin.etl-error-route.v1",
                                "action": "stop",
                                "maximumAttempts": 3,
                                "targetRef": None,
                                "retryPolicy": {"backoffSeconds": 10},
                                "nativeDetails": {},
                            },
                            "checkpointEnabled": True,
                            "nativeDetails": {},
                        },
                    ],
                    "edges": [{
                        "schema": "cdeadmin.etl-edge.v1",
                        "id": "flow",
                        "fromNodeId": "source",
                        "fromPort": "out",
                        "toNodeId": "sink",
                        "toPort": "in",
                        "mappingPolicy": "explicit",
                        "mappings": [{
                            "schema": "cdeadmin.etl-schema-mapping.v1",
                            "id": "doc_name_map",
                            "source": "doc_name",
                            "target": "doc_name",
                            "sourceNativeType": "VARCHAR(140)",
                            "semanticType": "string",
                            "targetNativeType": "VARCHAR",
                            "conversion": "exact",
                            "nullPolicy": "preserve",
                            "nullable": False,
                            "precision": None,
                            "scale": None,
                            "timezone": None,
                            "encoding": "UTF-8",
                            "lossy": False,
                            "lossAcknowledged": False,
                            "nativeDetails": {},
                        }],
                        "deliveryGuarantee": "at_least_once",
                        "partitioning": {},
                        "ordering": {},
                        "nativeDetails": {},
                    }],
                    "deployments": [{
                        "schema": "cdeadmin.etl-deployment.v1",
                        "id": "prod",
                        "name": "Production Polyglot Sync",
                        "environment": "production",
                        "bindings": [
                            {"schema": "cdeadmin.etl-deployment-binding.v1", "id": "b-src", "nodeId": "source", "resourceRef": src_r, "nativeDetails": {}},
                            {"schema": "cdeadmin.etl-deployment-binding.v1", "id": "b-snk", "nodeId": "sink", "resourceRef": sink_r, "nativeDetails": {}},
                        ],
                        "parameterBindings": {
                            "svc_cred": {"schema": "cdeadmin.credential-ref.v1", "scheme": "keyring", "id": f"cred-{akey}"},
                        },
                        "resourceLimits": {},
                        "nativeDetails": {},
                    }],
                    "schedules": [{
                        "schema": "cdeadmin.etl-schedule.v1",
                        "id": "hourly",
                        "name": "Hourly Lakehouse Refresh",
                        "enabled": True,
                        "trigger": "cron",
                        "expression": "15 * * * *",
                        "timezone": "UTC",
                        "deploymentId": "prod",
                        "dependencyRefs": [],
                        "parameters": {},
                        "nativeDetails": {},
                    }],
                    "tests": [{"id": "row-present", "name": "Minimum row check", "definition": {"minimum": 100}}],
                    "visualLayout": {"source": {"x": 80, "y": 120}, "sink": {"x": 460, "y": 120}},
                    "extensions": {},
                },
                "metadata": {"moduleId": "cdeadmin.etl", "mode": "batch"},
                "dependency_references": [],
                "resource_bindings": [src_r, sink_r],
                "validation_state": "valid",
                "validation_details": [],
            },
            now_sql=now_sql,
        )
        bump("cdeadmin.etl.v1")

    # 6. Change Data Capture (cdeadmin.cdc.v1)
    _upsert_validated_asset(
        cconn,
        project_key="erpnext-acc-general-ledger",
        project_uuid=projects_by_key["erpnext-acc-general-ledger"],
        user_id=user_id,
        asset_key="cdc-gl-ledger-stream",
        request_payload={
            "asset_type": "cdeadmin.cdc.v1",
            "schema_name": "cdeadmin.cdc.v1",
            "schema_version": 1,
            "name": "CDC Stream: Firebird GL_ENTRY -> DuckDB Lakehouse Feed",
            "path": "cdc/gl-ledger-stream.json",
            "expected_version": 0,
            "content": {
                "schema": "cdeadmin.cdc.asset.v1",
                "schemaVersion": 1,
                "moduleId": "cdeadmin.cdc",
                "name": "GL_ENTRY Ledger Change Stream",
                "description": "Captures committed GL_ENTRY postings and streams into DuckDB analytical marts.",
                "source": {
                    "schema": "cdeadmin.cdc-capture-source.v1",
                    "resourceRef": fb_gl_ref,
                    "captureMechanism": "trigger_based",
                    "nativeMechanism": "Firebird AFTER INSERT OR UPDATE trigger log",
                    "requiredPrivileges": ["SELECT", "TRIGGER"],
                    "credentialRef": {"schema": "cdeadmin.credential-ref.v1", "scheme": "vault", "id": "fb-cdc-reader"},
                    "startPosition": {
                        "schema": "cdeadmin.cdc-start-position.v1",
                        "kind": "latest",
                        "value": None,
                        "nativeDetails": {},
                    },
                    "snapshotPolicy": {
                        "schema": "cdeadmin.cdc-snapshot-policy.v1",
                        "mode": "initial",
                        "consistency": "snapshot",
                        "batchSize": None,
                        "nativeDetails": {},
                    },
                    "nativeDetails": {},
                },
                "filters": [],
                "transforms": [{
                    "schema": "cdeadmin.cdc-event-transform.v1",
                    "id": "mask-party-remarks",
                    "name": "Redact sensitive party remarks",
                    "kind": "redaction",
                    "enabled": True,
                    "rules": {"path": "after.REMARKS"},
                    "schemaMapping": {},
                    "nativeDetails": {},
                }],
                "sink": {
                    "schema": "cdeadmin.cdc-sink-binding.v1",
                    "resourceRef": dk_gl_ref,
                    "credentialRef": None,
                    "serialization": "JSONEachRow",
                    "nativeDetails": {},
                },
                "deliveryPolicy": {
                    "schema": "cdeadmin.cdc-delivery-policy.v1",
                    "guarantee": "at_least_once",
                    "deduplication": {"key": "DOC_NAME"},
                    "proof": {},
                    "nativeDetails": {},
                },
                "schemaEvolutionPolicy": {
                    "schema": "cdeadmin.cdc-evolution-policy.v1",
                    "defaultAction": "pause_and_review",
                    "changes": [],
                    "nativeDetails": {},
                },
                "alerts": [{
                    "schema": "cdeadmin.cdc-alert.v1",
                    "id": "gl-cdc-lag",
                    "event": "lag",
                    "threshold": {"maximum": 60},
                    "enabled": True,
                    "nativeDetails": {},
                }],
                "visualLayout": {},
                "extensions": {},
            },
            "metadata": {"moduleId": "cdeadmin.cdc"},
            "dependency_references": [],
            "resource_bindings": [fb_gl_ref, dk_gl_ref],
            "validation_state": "valid",
            "validation_details": [],
        },
        now_sql=now_sql,
    )
    bump("cdeadmin.cdc.v1")

    # 7. Replication Topology (cdeadmin.replication.v1)
    rep_health = {
        "schema": "cdeadmin.replication-health.v1",
        "overall": "healthy",
        "dimensions": {
            "connectivity": "healthy",
            "linkState": "healthy",
            "quorum": "healthy",
            "errors": "healthy",
            "provider": "healthy",
        },
        "policyAllowsUnknownCritical": False,
        "providerReported": "STREAMING_SYNC",
        "nativeDetails": {},
    }
    _upsert_validated_asset(
        cconn,
        project_key="press-sites-benches",
        project_uuid=projects_by_key["press-sites-benches"],
        user_id=user_id,
        asset_key="replication-firebird-ha-bench",
        request_payload={
            "asset_type": "cdeadmin.replication.v1",
            "schema_name": "cdeadmin.replication.v1",
            "schema_version": 1,
            "name": "Firebird 5.0 Journal Replication Topology (ca-central-1 -> us-east-1)",
            "path": "replication/firebird-ha-bench.json",
            "expected_version": 0,
            "content": {
                "schema": "cdeadmin.replication.asset.v1",
                "schemaVersion": 1,
                "moduleId": "cdeadmin.replication",
                "name": "Frappe Cloud Firebird 5.0 HA Bench Topology",
                "description": "Synchronous journal shipping from Toronto primary bench to Virginia warm standby.",
                "savedTopologies": [{
                    "schema": "cdeadmin.replication-topology.v1",
                    "id": "fb-press-ha",
                    "name": "Firebird 5.0 Primary/Standby Journal Stream",
                    "scopeRef": fb_db_ref,
                    "providerId": "firebird",
                    "revision": "ods-13.1-seq-4820",
                    "participants": [
                        {
                            "schema": "cdeadmin.replication-participant.v1",
                            "id": "ca-primary",
                            "name": "bench-ca-01 (Primary Writer)",
                            "resourceRef": fb_db_ref,
                            "normalizedRole": "writer_capable",
                            "nativeRole": "primary",
                            "nativeState": "streaming",
                            "groupId": "ha-group-1",
                            "health": rep_health,
                            "position": {
                                "schema": "cdeadmin.replication-position.v1",
                                "provider": "firebird",
                                "positionType": "JOURNAL_SEQ",
                                "rawValue": "4820:194028",
                                "comparableWithinScope": True,
                                "observedAt": "2026-11-15T19:00:00Z",
                                "nativeDetails": {},
                            },
                            "storage": {},
                            "connections": {},
                            "nativeDetails": {},
                        },
                        {
                            "schema": "cdeadmin.replication-participant.v1",
                            "id": "us-standby",
                            "name": "bench-us-02 (Read Replica)",
                            "resourceRef": _resource_ref("firebird", fb["endpoint_id"], fb["target_id"], "database", "frappe_suite_dr.fdb"),
                            "normalizedRole": "read_only_replica",
                            "nativeRole": "replica",
                            "nativeState": "streaming",
                            "groupId": "ha-group-1",
                            "health": rep_health,
                            "position": {
                                "schema": "cdeadmin.replication-position.v1",
                                "provider": "firebird",
                                "positionType": "JOURNAL_SEQ",
                                "rawValue": "4820:193980",
                                "comparableWithinScope": True,
                                "observedAt": "2026-11-15T19:00:00Z",
                                "nativeDetails": {},
                            },
                            "storage": {},
                            "connections": {},
                            "nativeDetails": {},
                        },
                    ],
                    "groups": [{
                        "schema": "cdeadmin.replica-group.v1",
                        "id": "ha-group-1",
                        "name": "Press Dedicated HA Pair",
                        "nativeType": "firebird_journal_replication",
                        "memberIds": ["ca-primary", "us-standby"],
                        "quorumState": "not_applicable",
                        "roleMetadata": {},
                        "nativeDetails": {},
                    }],
                    "links": [{
                        "schema": "cdeadmin.replication-link.v1",
                        "id": "link-ca-us",
                        "name": "ca-central-1 -> us-east-1",
                        "sourceParticipantId": "ca-primary",
                        "targetParticipantId": "us-standby",
                        "mechanism": "journal_shipping",
                        "nativeState": "streaming",
                        "health": rep_health,
                        "position": None,
                        "checkpoint": {},
                        "errors": [],
                        "nativeDetails": {},
                    }],
                    "lagSamples": [{
                        "schema": "cdeadmin.replication-lag-sample.v1",
                        "id": "lag-sample-1",
                        "linkId": "link-ca-us",
                        "observedAt": "2026-11-15T19:00:00Z",
                        "unit": "bytes",
                        "value": 512,
                        "source": "provider_calculated",
                        "calculation": {"method": "journal_offset_delta"},
                        "nativeDetails": {},
                    }],
                    "conflictPolicy": {},
                    "healthPolicy": {},
                    "events": [],
                    "nativeDetails": {},
                }],
                "alertPolicies": [{
                    "schema": "cdeadmin.replication-alert-policy.v1",
                    "id": "alert-journal-lag",
                    "topologyId": "fb-press-ha",
                    "linkId": "link-ca-us",
                    "metric": "provider_lag",
                    "maximum": 65536,
                    "unit": "bytes",
                    "enabled": True,
                    "nativeDetails": {},
                }],
                "failoverPlans": [{
                    "schema": "cdeadmin.replication-failover-plan.v1",
                    "id": "plan-promote-us",
                    "name": "Controlled Switchover to bench-us-02",
                    "topologyId": "fb-press-ha",
                    "candidateParticipantId": "us-standby",
                    "targetRole": "primary",
                    "preconditions": [{"id": "drain", "label": "Drain active writers", "action": "gfix_shut_tran", "targetRef": None, "parameters": {}, "evidenceRequirements": {}, "nativeDetails": {}}],
                    "commands": [{"id": "promote", "label": "Promote replica mode read-write", "action": "nbackup_promote", "targetRef": None, "parameters": {}, "evidenceRequirements": {}, "nativeDetails": {}}],
                    "expectedTopology": {"participantRoles": {"us-standby": "primary"}},
                    "verification": [{"id": "verify-rw", "label": "Verify RDB$GET_CONTEXT replica mode", "action": "verify_rw", "targetRef": None, "parameters": {}, "evidenceRequirements": {}, "nativeDetails": {}}],
                    "rollback": [{"id": "restore-ca", "label": "Re-point journal stream back to bench-ca-01", "action": "restore_primary", "targetRef": None, "parameters": {}, "evidenceRequirements": {}, "nativeDetails": {}}],
                    "dataLossRisk": "Zero RPO after transaction drain",
                    "estimatedRPO": {"value": 0, "unit": "bytes", "evidence": {"provider": "firebird"}},
                    "estimatedRTO": None,
                    "nativeDetails": {},
                }],
                "visualLayouts": [{
                    "schema": "cdeadmin.replication-layout.v1",
                    "id": "layout-ha",
                    "topologyId": "fb-press-ha",
                    "positions": {"ca-primary": {"x": 120, "y": 140}, "us-standby": {"x": 460, "y": 140}},
                    "nativeDetails": {},
                }],
                "snapshotRefs": [{
                    "schema": "cdeadmin.replication-snapshot-ref.v1",
                    "id": "snap-ha-1",
                    "topologyId": "fb-press-ha",
                    "capturedAt": "2026-11-15T19:00:00Z",
                    "reference": {"schema": "cdeadmin.external-ref.v1", "id": "replication-snap://fb-press-ha/1"},
                    "nativeDetails": {},
                }],
                "extensions": {},
            },
            "metadata": {"moduleId": "cdeadmin.replication"},
            "dependency_references": [],
            "resource_bindings": [fb_db_ref],
            "validation_state": "valid",
            "validation_details": [],
        },
        now_sql=now_sql,
    )
    bump("cdeadmin.replication.v1")

    # 8. Distributed Tracing (cdeadmin.tracing.v1) — correlated with DATUM_TRACES!
    _upsert_validated_asset(
        cconn,
        project_key="datum-cargo-telemetry",
        project_uuid=projects_by_key["datum-cargo-telemetry"],
        user_id=user_id,
        asset_key="tracing-frappe-otlp-firebird",
        request_payload={
            "asset_type": "cdeadmin.tracing.v1",
            "schema_name": "cdeadmin.tracing.v1",
            "schema_version": 1,
            "name": "Distributed Tracing: Frappe Web -> Firebird 5.0 Span Waterfall",
            "path": "tracing/frappe-otlp-firebird.json",
            "expected_version": 0,
            "content": {
                "schema": "cdeadmin.tracing.asset.v1",
                "schemaVersion": 1,
                "moduleId": "cdeadmin.tracing",
                "name": "Datum OpenTelemetry & Firebird Trace Correlation",
                "description": "Correlates HTTP invoice submissions with Firebird GL_ENTRY SQL spans.",
                "savedSearches": [
                    {
                        "schema": "cdeadmin.tracing-saved-search.v1",
                        "id": "lock-conflicts",
                        "name": "Firebird Lock Conflict Spans",
                        "filters": {"status": "ERROR", "service": "firebird-db"},
                        "pageSize": 100,
                        "sort": {"startTime": "desc"},
                        "description": "Traces experiencing lock retry or HTTP 502",
                    },
                    {
                        "schema": "cdeadmin.tracing-saved-search.v1",
                        "id": "slow-invoice-post",
                        "name": "Sales Invoice POST > 50ms",
                        "filters": {"spanName": "POST /api/resource/Sales Invoice"},
                        "pageSize": 50,
                        "sort": {"durationNs": "desc"},
                        "description": "High-latency voucher submission waterfalls",
                    },
                ],
                "savedViews": [{
                    "schema": "cdeadmin.tracing-saved-view.v1",
                    "id": "waterfall-errors",
                    "name": "Lock Conflict Span Waterfall",
                    "kind": "waterfall",
                    "searchId": "lock-conflicts",
                    "layout": {},
                    "observedWindow": None,
                    "description": "End-to-end span waterfall view",
                }],
                "sourceConfigs": [{
                    "schema": "cdeadmin.trace-source.v1",
                    "id": "firebird-datum-native",
                    "name": "Firebird DATUM_TRACES Native Store",
                    "sourceType": "provider_native",
                    "enabled": True,
                    "endpoint": None,
                    "providerId": "firebird",
                    "resourceRef": fb_traces_ref,
                    "credentialRef": {"schema": "cdeadmin.credential-ref.v1", "id": "fb-trace-reader"},
                    "transport": {"tls": False},
                    "sensitivityPolicyId": "redact-bind-params",
                    "nativeDetails": {"table": "DATUM_TRACES"},
                }],
                "samplingPolicies": [{
                    "schema": "cdeadmin.tracing-sampling-policy.v1",
                    "id": "redact-bind-params",
                    "name": "100% Error Tail + Redacted Bind Literals",
                    "rate": 0.25,
                    "tailCriteria": {"errors": True},
                    "sensitiveAttributePolicy": {
                        "captureRawStatements": False,
                        "capturePayloads": False,
                    },
                    "retention": {"days": 30},
                    "enabled": True,
                }],
                "retentionPolicyRef": {"schema": "cdeadmin.external-ref.v1", "id": "retention://datum-30d"},
                "extensions": {},
            },
            "metadata": {"moduleId": "cdeadmin.tracing"},
            "dependency_references": [],
            "resource_bindings": [fb_traces_ref],
            "validation_state": "valid",
            "validation_details": [],
        },
        now_sql=now_sql,
    )
    bump("cdeadmin.tracing.v1")

    # 9. Cross-Engine Migration Planning (cdeadmin.migration.v1)
    _upsert_validated_asset(
        cconn,
        project_key="books-desktop-ledger",
        project_uuid=projects_by_key["books-desktop-ledger"],
        user_id=user_id,
        asset_key="migration-sqlite-books-to-firebird-erp",
        request_payload={
            "asset_type": "cdeadmin.migration.v1",
            "schema_name": "cdeadmin.migration.v1",
            "schema_version": 1,
            "name": "Migration Plan: Frappe Books SQLite Edge -> Firebird 5.0 Enterprise Suite",
            "path": "migration/sqlite-books-to-firebird-erp.json",
            "expected_version": 0,
            "content": {
                "schema": "cdeadmin.migration.asset.v1",
                "schemaVersion": 1,
                "moduleId": "cdeadmin.migration",
                "name": "Frappe Books SQLite to Firebird 5.0 Enterprise Consolidation",
                "description": "Graduates standalone retail Frappe Books SQLite stores into multi-company Firebird 5.0.",
                "sourceBinding": sq_sinv_ref,
                "targetBinding": fb_sinv_ref,
                "strategy": "offline",
                "phase": "design",
                "assessment": {
                    "schema": "cdeadmin.migration-assessment.v1",
                    "id": "assess-books-fb",
                    "sourceRevision": "sqlite-3.53-wal",
                    "targetRevision": "firebird-5.0.4-ods13.1",
                    "findings": [{
                        "schema": "cdeadmin.migration-finding.v1",
                        "id": "finding-sinv",
                        "sourceRef": sq_sinv_ref,
                        "targetRef": fb_sinv_ref,
                        "objectKind": "table",
                        "category": "supported_exact",
                        "evidenceSource": "provider_adapter",
                        "evidence": {"rule": "real_to_numeric_18_2"},
                        "message": "SQLite REAL currency columns map cleanly to Firebird D_MONEY NUMERIC(18,2)",
                        "blocker": False,
                        "waived": False,
                        "waiverRef": None,
                        "nativeDetails": {"sourceType": "REAL", "targetType": "NUMERIC(18,2)"},
                    }],
                    "estimates": {"rows": 900},
                    "evidence": {"observed": True},
                    "completedAt": "2026-11-15T19:10:00Z",
                    "nativeDetails": {},
                },
                "mappingSet": [{
                    "schema": "cdeadmin.migration-mapping.v1",
                    "id": "map-grand-total",
                    "sourceRef": sq_sinv_ref,
                    "targetRef": fb_sinv_ref,
                    "mappingKind": "type",
                    "category": "supported_exact",
                    "decision": "accepted",
                    "sourceNativeType": "REAL",
                    "targetNativeType": "NUMERIC(18,2)",
                    "expression": None,
                    "lossy": False,
                    "lossAcknowledged": False,
                    "behaviorChange": False,
                    "evidence": {"rule": "currency_exact"},
                    "nativeDetails": {},
                }],
                "schemaPlan": {
                    "schema": "cdeadmin.migration-schema-plan.v1",
                    "id": "schema-plan-books",
                    "operations": [{
                        "schema": "cdeadmin.migration-schema-operation.v1",
                        "id": "op-add-terminal-col",
                        "action": "alter",
                        "sourceRef": sq_sinv_ref,
                        "targetRef": fb_sinv_ref,
                        "dependencies": [],
                        "preconditions": [{"kind": "table_exists"}],
                        "rollback": [{"action": "drop_column"}],
                        "risk": "low",
                        "nativeDefinition": {"statement": "ALTER TABLE SALES_INVOICE ADD EDGE_TERMINAL_ID VARCHAR(40)"},
                    }],
                    "schemaCompareRef": {
                        "schema": "cdeadmin.asset-ref.v1",
                        "projectId": "books-desktop-ledger",
                        "assetId": "compare-sqlite-edge-vs-firebird-erp",
                    },
                    "expectedTargetRevision": "ods-13.1",
                    "nativeDetails": {},
                },
                "dataMovePlan": {
                    "schema": "cdeadmin.migration-data-move-plan.v1",
                    "id": "move-sinv",
                    "units": [{
                        "schema": "cdeadmin.migration-copy-unit.v1",
                        "id": "copy-pos-invoices",
                        "sourceRef": sq_sinv_ref,
                        "targetRef": fb_sinv_ref,
                        "partition": {"range": "all"},
                        "orderingKey": ["DOC_NAME"],
                        "batchSize": 500,
                        "parallelism": 1,
                        "restartPolicy": "resume_committed",
                        "transformRef": None,
                        "nativeDetails": {},
                    }],
                    "concurrency": 1,
                    "consistencyBoundary": {"snapshot": "sqlite-wal-checkpoint"},
                    "errorPolicy": {"stop": True},
                    "nativeDetails": {},
                },
                "cdcPlanRef": None,
                "validationPlan": [{
                    "schema": "cdeadmin.migration-verification.v1",
                    "id": "verify-sinv-counts",
                    "type": "row_document_counts",
                    "sourceRef": sq_sinv_ref,
                    "targetRef": fb_sinv_ref,
                    "canonicalization": None,
                    "policy": {"minimumTargetRows": 900},
                    "blocking": True,
                    "qualityAssetRef": None,
                    "nativeDetails": {},
                }],
                "cutoverPlan": {
                    "schema": "cdeadmin.migration-cutover-plan.v1",
                    "id": "cutover-pos",
                    "steps": [
                        {"schema": "cdeadmin.migration-runbook-step.v1", "id": "quiesce-pos", "label": "Quiesce POS outbox", "action": "quiesce_pos", "dependencies": [], "preconditions": [], "expectedEvidence": {"outboxEmpty": True}, "providerMutation": False, "nativeDetails": {}},
                        {"schema": "cdeadmin.migration-runbook-step.v1", "id": "switch-route", "label": "Point POS sync to Firebird ERP", "action": "switch_endpoint", "dependencies": ["quiesce-pos"], "preconditions": [], "expectedEvidence": {"connected": True}, "providerMutation": True, "nativeDetails": {}},
                    ],
                    "cdcLagThreshold": None,
                    "armWindowMinutes": 30,
                    "targetEnvironment": "production",
                    "targetConnection": fb["endpoint_id"],
                    "endpointChange": {"route": "firebird-erp"},
                    "postChecks": [{"check": "trial_balance_zero_diff"}],
                    "nativeDetails": {},
                },
                "rollbackPlan": {
                    "schema": "cdeadmin.migration-rollback-plan.v1",
                    "id": "rollback-pos",
                    "classification": "fully_automatable",
                    "pointOfNoReturn": "switch-route",
                    "deadline": None,
                    "conditions": [{"when": "verification_failed"}],
                    "steps": [{"schema": "cdeadmin.migration-runbook-step.v1", "id": "resume-local", "label": "Resume offline SQLite POS mode", "action": "resume_sqlite", "dependencies": [], "preconditions": [], "expectedEvidence": {"localReady": True}, "providerMutation": False, "nativeDetails": {}}],
                    "recoverability": {"sourcePreserved": True},
                    "nativeDetails": {},
                },
                "waivers": [],
                "extensions": {},
            },
            "metadata": {"moduleId": "cdeadmin.migration"},
            "dependency_references": [],
            "resource_bindings": [sq_sinv_ref, fb_sinv_ref],
            "validation_state": "valid",
            "validation_details": [],
        },
        now_sql=now_sql,
    )
    bump("cdeadmin.migration.v1")

    # 10. API Designer (cdeadmin.api.v1) — OpenAPI 3.2 bound to Firebird SALES_INVOICE!
    api_cred = {
        "schema": "cdeadmin.credential-ref.v1",
        "id": "erpnext-api-oauth-vault",
        "providerId": "credential-vault",
        "scope": "api:sales_invoice",
        "displayName": "ERPNext Commercial API Service Credential",
    }
    _upsert_validated_asset(
        cconn,
        project_key="erpnext-selling-orders",
        project_uuid=projects_by_key["erpnext-selling-orders"],
        user_id=user_id,
        asset_key="api-erpnext-sales-invoice-v1",
        request_payload={
            "asset_type": "cdeadmin.api.v1",
            "schema_name": "cdeadmin.api.v1",
            "schema_version": 1,
            "name": "OpenAPI 3.2: ERPNext Sales Invoice & Receivables REST Service",
            "path": "apis/erpnext-sales-invoice.openapi.json",
            "expected_version": 0,
            "content": {
                "schema": "cdeadmin.api.asset.v1",
                "schemaVersion": 1,
                "moduleId": "cdeadmin.api",
                "profile": "openapi_http",
                "externalSpecVersion": "3.2.0",
                "info": {"title": "ERPNext Sales Invoice & Receivables API", "version": "1.0.0"},
                "servers": [{
                    "schema": "cdeadmin.api-server.v1",
                    "id": "production",
                    "name": "Maple Tech Cloud API Gateway",
                    "environment": "production",
                    "urlTemplate": "https://erp.mapletech.cloud/api/v2/{company}",
                    "protocol": "https",
                    "credentialRef": api_cred,
                    "variables": {"company": "MTM"},
                    "tlsPolicyRef": {"schema": "cdeadmin.asset-ref.v1", "projectId": "erpnext-selling-orders", "assetId": "tls-mtm-prod"},
                    "description": "Production Frappe REST gateway",
                    "extensions": [],
                }],
                "operations": [{
                    "schema": "cdeadmin.api-operation.v1",
                    "id": "list-sales-invoices",
                    "name": "List Submitted Sales Invoices",
                    "method": "GET",
                    "path": "/sales-invoices",
                    "summary": "Query paginated sales invoices by customer and status",
                    "description": "Backed directly by Firebird 5.0 SALES_INVOICE relation.",
                    "parameters": [{
                        "schema": "cdeadmin.api-parameter.v1",
                        "id": "limit",
                        "name": "limit",
                        "location": "query",
                        "required": False,
                        "description": "Page row cap",
                        "schemaRef": None,
                        "definition": {"type": "integer"},
                        "extensions": [],
                    }],
                    "requestSchemaRef": None,
                    "responses": [{
                        "schema": "cdeadmin.api-response.v1",
                        "id": "200",
                        "status": "200",
                        "description": "Sales invoice collection",
                        "schemaRef": "sales_invoice_dto",
                        "headers": {},
                        "examples": {"sample": {"doc_name": "ACC-SINV-2026-0001", "grand_total": 12723.80}},
                        "extensions": [],
                    }],
                    "binding": {
                        "schema": "cdeadmin.api-binding.v1",
                        "id": "bind-fb-sinv",
                        "type": "provider_resource_read",
                        "targetRef": fb_sinv_ref,
                        "mode": "read",
                        "queryAssetRef": None,
                        "command": None,
                        "inputMap": {"limit": "limit"},
                        "outputMap": {"rows": "body"},
                        "nativeDetails": {"providerOperation": "select"},
                        "extensions": [],
                    },
                    "securityRequirementIds": ["oauth2_cc"],
                    "policyIds": ["std_rate_limit"],
                    "tags": ["selling", "receivables"],
                    "deprecated": False,
                    "idempotent": True,
                    "callbacks": {},
                    "extensions": [],
                }],
                "channels": [],
                "messages": [],
                "schemas": [{
                    "schema": "cdeadmin.api-schema.v1",
                    "id": "sales_invoice_dto",
                    "name": "SalesInvoiceDTO",
                    "kind": "object",
                    "definition": {"type": "object"},
                    "fields": [
                        {"id": "doc_name", "name": "doc_name", "definition": {"type": "string"}, "required": True, "description": "Primary voucher ID"},
                        {"id": "grand_total", "name": "grand_total", "definition": {"type": "number"}, "required": True, "description": "Billed total"},
                    ],
                    "physicalBindings": [fb_sinv_ref],
                    "description": "Sales Invoice wire representation",
                    "extensions": [],
                }],
                "security": [{
                    "schema": "cdeadmin.api-security.v1",
                    "id": "oauth2_cc",
                    "name": "Frappe OAuth2 Client Credentials",
                    "type": "oauth2",
                    "scheme": None,
                    "location": None,
                    "parameterName": None,
                    "flows": {"source": '{"clientCredentials":true}'},
                    "scopes": {"sales_invoice:read": "Read submitted sales invoices"},
                    "credentialRef": api_cred,
                    "description": "OAuth2 machine-to-machine token",
                    "extensions": [],
                }],
                "policies": [{
                    "schema": "cdeadmin.api-policy.v1",
                    "id": "std_rate_limit",
                    "name": "Tenant Burst Guard",
                    "type": "rate_limit",
                    "config": {"requestsPerMinute": 300},
                    "extensions": [],
                }],
                "tests": [{
                    "schema": "cdeadmin.api-test.v1",
                    "id": "smoke-list-sinv",
                    "name": "Verify HTTP 200 on /sales-invoices?limit=10",
                    "operationId": "list-sales-invoices",
                    "channelId": None,
                    "environmentId": "production",
                    "mode": "live",
                    "parameters": {"limit": 10},
                    "headers": {"accept": "application/json"},
                    "body": {},
                    "expected": {"status": 200},
                    "sensitiveHeaderNames": ["authorization"],
                    "extensions": [],
                }],
                "deploymentBindings": [{
                    "schema": "cdeadmin.api-deployment.v1",
                    "id": "deploy-mtm-gw",
                    "name": "Maple Tech Production Gateway",
                    "environment": "production",
                    "targetRef": {"schema": "cdeadmin.asset-ref.v1", "projectId": "erpnext-selling-orders", "assetId": "gw-mtm"},
                    "gatewayProfile": "generic_http_gateway",
                    "credentialRef": api_cred,
                    "config": {"stage": "v2"},
                    "extensions": [],
                }],
                "externalReferences": [],
                "extensions": [{"id": "x-frappe-doctype", "name": "x-frappe-doctype", "value": {"doctype": "Sales Invoice"}}],
            },
            "metadata": {"moduleId": "cdeadmin.api"},
            "dependency_references": [],
            "resource_bindings": [fb_sinv_ref],
            "validation_state": "valid",
            "validation_details": [],
        },
        now_sql=now_sql,
    )
    bump("cdeadmin.api.v1")

    # 11. ML / Vector Index & Retrieval Designer (cdeadmin.ml_vector.v1) — Helpdesk semantic triage!
    ml_model_ref = {
        "schema": "cdeadmin.embedding-model-ref.v1",
        "modelId": "bge-small-en",
        "versionId": "bge-small-v1.5",
        "providerId": "local-onnx",
        "external": False,
        "providerIdentity": None,
        "credentialRef": None,
        "nativeDetails": {"runtime": "onnxruntime-cpu"},
    }
    _upsert_validated_asset(
        cconn,
        project_key="frappe-helpdesk",
        project_uuid=projects_by_key["frappe-helpdesk"],
        user_id=user_id,
        asset_key="ml-vector-helpdesk-semantic-triage",
        request_payload={
            "asset_type": "cdeadmin.ml_vector.v1",
            "schema_name": "cdeadmin.ml_vector.v1",
            "schema_version": 1,
            "name": "ML / Vector Index: Helpdesk Ticket & Knowledge Article HNSW Triage",
            "path": "ml-vector/helpdesk-semantic-triage.json",
            "expected_version": 0,
            "content": {
                "schema": "cdeadmin.ml-vector.asset.v1",
                "schemaVersion": 1,
                "moduleId": "cdeadmin.ml_vector",
                "name": "Helpdesk Semantic Ticket Triage & Duplicate Detection",
                "description": "Local ONNX 384-dim HNSW index over HD_TICKET subject & description.",
                "vectorDesigns": [{
                    "schema": "cdeadmin.vector-design.v1",
                    "id": "hd_tickets_vec",
                    "name": "HD_TICKET Embeddings",
                    "resourceRef": fb_hd_ref,
                    "dimensions": 384,
                    "fields": [{
                        "schema": "cdeadmin.embedding-field.v1",
                        "id": "ticket_embedding",
                        "name": "Ticket Embedding",
                        "sourceFields": ["SUBJECT", "DESCRIPTION"],
                        "modelRef": ml_model_ref,
                        "dimensions": 384,
                        "targetField": "EMBEDDING_VEC",
                        "normalizationTemplate": "{{SUBJECT}}\n{{DESCRIPTION}}",
                        "nativeDetails": {"dataType": "FLOAT_VECTOR"},
                    }],
                    "indexes": [{
                        "schema": "cdeadmin.vector-index-plan.v1",
                        "id": "hd-tickets-hnsw",
                        "name": "HD Tickets Cosine HNSW",
                        "fieldId": "ticket_embedding",
                        "algorithm": "HNSW",
                        "normalizedMetric": "cosine",
                        "nativeMetric": "COSINE",
                        "dimensions": 384,
                        "providerConfig": {"M": 16, "efConstruction": 200},
                        "buildMode": "online",
                        "description": "Sub-10ms similar-ticket lookup",
                        "extensions": [],
                    }],
                    "description": "Support ticket semantic vector store",
                    "nativeDetails": {"table": "HD_TICKET"},
                    "extensions": [],
                }],
                "embeddingPipelines": [{
                    "schema": "cdeadmin.embedding-pipeline.v1",
                    "id": "hd-ticket-embedder",
                    "name": "Local Ticket Embedding Pipeline",
                    "resourceRef": fb_hd_ref,
                    "sourceFields": ["SUBJECT", "DESCRIPTION"],
                    "normalizationTemplate": "{{SUBJECT}}\n{{DESCRIPTION}}",
                    "modelRef": ml_model_ref,
                    "outputDimensions": 384,
                    "targetField": "EMBEDDING_VEC",
                    "batching": {"size": 64},
                    "rateLimitPolicy": {"perSecond": 25},
                    "dataSharingPolicy": {
                        "containsSensitiveData": False,
                        "approvedForSensitiveData": False,
                        "providerIdentity": "local-onnx",
                    },
                    "description": "Air-gapped local ONNX embedding pipeline",
                    "extensions": [],
                }],
                "modelEntries": [{
                    "schema": "cdeadmin.model-entry.v1",
                    "id": "bge-small-en",
                    "name": "BGE Small English v1.5 (ONNX)",
                    "description": "Approved local sentence embedding model",
                    "tags": ["embedding", "helpdesk"],
                    "aliases": [{"id": "prod", "name": "production", "versionId": "bge-small-v1.5"}],
                    "versionTags": [{"id": "v15-tags", "versionId": "bge-small-v1.5", "tags": ["certified"]}],
                    "versions": [{
                        "schema": "cdeadmin.model-version.v1",
                        "id": "bge-small-v1.5",
                        "version": "1.5.0",
                        "artifactRef": {"schema": "cdeadmin.asset-ref.v1", "projectId": "frappe-helpdesk", "assetId": "onnx-bge-small"},
                        "originatingRunRef": {"schema": "cdeadmin.result-ref.v1", "id": "run-bge-eval-01"},
                        "datasetRefs": [{"schema": "cdeadmin.asset-ref.v1", "projectId": "frappe-helpdesk", "assetId": "hd-golden-pairs"}],
                        "evaluationRefs": [{"schema": "cdeadmin.result-ref.v1", "id": "eval-recall-091"}],
                        "deploymentRefs": [],
                        "contentDigest": "sha256:4f8a9c01b2e3d4f5",
                        "description": "Quantized INT8 ONNX build",
                        "nativeDetails": {"format": "onnx"},
                    }],
                    "extensions": [],
                }],
                "experiments": [{
                    "schema": "cdeadmin.ml-experiment.v1",
                    "id": "exp-hnsw-m16",
                    "name": "HNSW M=16 Recall Benchmark",
                    "inputRefs": [{"schema": "cdeadmin.asset-ref.v1", "projectId": "frappe-helpdesk", "assetId": "hd-golden-pairs"}],
                    "parameters": {"M": 16, "efSearch": 64},
                    "metricDefinitions": {"recall": "recall@10"},
                    "artifactRefs": [],
                    "datasetRevisionRef": {"schema": "cdeadmin.asset-ref.v1", "projectId": "frappe-helpdesk", "assetId": "hd-golden-v1"},
                    "description": "Achieved 0.914 recall@10 at 3.2ms p95",
                    "extensions": [],
                }],
                "evaluationCases": [{
                    "schema": "cdeadmin.vector-evaluation-case.v1",
                    "id": "eval-vibration-alert",
                    "name": "Pump Vibration Duplicate Ticket Retrieval",
                    "vectorDesignId": "hd_tickets_vec",
                    "indexId": "hd-tickets-hnsw",
                    "querySource": {"kind": "text", "value": "bearing vibration RMS threshold"},
                    "filters": {},
                    "k": 10,
                    "metrics": ["recall@10", "latency_ms"],
                    "groundTruthRef": {"schema": "cdeadmin.asset-ref.v1", "projectId": "frappe-helpdesk", "assetId": "hd-golden-pairs"},
                    "datasetRevisionRef": {"schema": "cdeadmin.asset-ref.v1", "projectId": "frappe-helpdesk", "assetId": "hd-golden-v1"},
                    "expected": {"recallAt10": 0.9},
                    "description": "Verifies industrial telemetry tickets cluster accurately",
                    "extensions": [],
                }],
                "deploymentBindings": [{
                    "schema": "cdeadmin.ml-deployment.v1",
                    "id": "hd-triage-prod",
                    "name": "Helpdesk Triage Read-Only Index",
                    "environment": "production",
                    "endpointRef": fb_hd_ref,
                    "modelId": "bge-small-en",
                    "modelVersionId": "bge-small-v1.5",
                    "vectorDesignId": "hd_tickets_vec",
                    "indexId": "hd-tickets-hnsw",
                    "credentialRef": None,
                    "policy": {"readOnly": True},
                    "config": {"replicas": 1},
                    "extensions": [],
                }],
                "extensions": [],
            },
            "metadata": {"moduleId": "cdeadmin.ml_vector"},
            "dependency_references": [],
            "resource_bindings": [fb_hd_ref],
            "validation_state": "valid",
            "validation_details": [],
        },
        now_sql=now_sql,
    )
    bump("cdeadmin.ml_vector.v1")

    # 12. Governed AI Assistant (cdeadmin.ai.v1) + Complete 10-Contract AI Interface Suite (cdeadmin.ai_interface.*)
    ai_proj = "collab-raven" if "collab-raven" in projects_by_key else "erpnext-acc-general-ledger"
    # Let's check exact raven/ai project key or place in collab-raven!
    if "collab-raven" in projects_by_key:
        ai_proj = "collab-raven"

    _upsert_validated_asset(
        cconn,
        project_key=ai_proj,
        project_uuid=projects_by_key[ai_proj],
        user_id=user_id,
        asset_key="ai-assistant-frappe-ledger-copilot",
        request_payload={
            "asset_type": "cdeadmin.ai.v1",
            "schema_name": "cdeadmin.ai.v1",
            "schema_version": 1,
            "name": "Governed AI Assistant: Frappe Suite SQL & DDN Draft Copilot",
            "path": "ai/frappe-ledger-copilot.json",
            "expected_version": 0,
            "content": {
                "schema": "cdeadmin.ai.asset.v1",
                "schemaVersion": 1,
                "moduleId": "cdeadmin.ai",
                "name": "Frappe Enterprise Suite Read-Only Draft Copilot",
                "description": "Searches existing BI questions first and drafts DDN diffs for human review; never auto-accepts.",
                "sessionPolicy": {
                    "id": "byok-draft-only",
                    "allowedModes": ["ask", "explain", "plan"],
                    "defaultMode": "ask",
                    "allowedReadToolIds": ["metadata.describe", "discovery.search"],
                    "allowedProposalCommandIds": ["bi.question.draft"],
                    "maximumPlanSteps": 8,
                    "requireEvidence": True,
                    "nativeDetails": {},
                },
                "savedContextRefs": [{
                    "schema": "cdeadmin.ai-context-scope.v1",
                    "id": "frappe-catalog-metadata",
                    "name": "Firebird Frappe Suite Metadata Scope",
                    "reference": fb_db_ref,
                    "type": "database_metadata",
                    "environment": "production",
                    "sensitivity": "internal",
                    "exposure": "metadata_only",
                    "timeRange": {},
                    "description": "Catalog metadata only; zero raw PII row exposure",
                    "nativeDetails": {},
                }],
                "savedPlans": [{
                    "schema": "cdeadmin.ai-action-plan.v1",
                    "id": "plan-draft-q4-variance",
                    "name": "Draft Q4 CoA Variance BI Question",
                    "revision": 1,
                    "targetRevision": "ods-13.1",
                    "contextScopeIds": ["frappe-catalog-metadata"],
                    "actions": [{
                        "schema": "cdeadmin.ai-proposed-action.v1",
                        "id": "propose-q4-question",
                        "type": "proposed_command",
                        "commandId": "bi.question.draft",
                        "taskType": None,
                        "assetChangeRef": None,
                        "targetRef": fb_gl_ref,
                        "arguments": {"table": "GL_ENTRY"},
                        "rationale": "Creates a Draft BI question comparing Q3 vs Q4 net credit by Cost Center for human review",
                        "effects": ["creates draft DDN question only"],
                        "permissions": ["project.asset.edit"],
                        "rollbackNote": "Discard unaccepted draft version",
                        "dependencies": [],
                        "validation": {"valid": True},
                        "evidenceRefs": [fb_gl_ref],
                        "diff": {"after": "draft"},
                        "extensions": [],
                    }],
                    "validation": {"valid": True},
                    "rollbackNotes": "Draft-only; human reviewer accepts or discards.",
                    "evidenceRefs": [fb_gl_ref],
                    "description": "Reviewed BYOK draft proposal",
                    "extensions": [],
                }],
                "modelProfileRef": {"schema": "cdeadmin.asset-ref.v1", "projectId": ai_proj, "assetId": "AIModelProfile"},
                "conversationPersistencePolicy": {
                    "persistMessages": False,
                    "storePrompts": False,
                    "storeResponses": False,
                    "retentionDays": None,
                    "nativeDetails": {},
                },
                "extensions": [],
            },
            "metadata": {"moduleId": "cdeadmin.ai"},
            "dependency_references": [{"schema": "cdeadmin.asset-ref.v1", "projectId": ai_proj, "assetId": "AIModelProfile"}],
            "resource_bindings": [fb_db_ref],
            "validation_state": "valid",
            "validation_details": [],
        },
        now_sql=now_sql,
    )
    bump("cdeadmin.ai.v1")

    ai_interface_contracts = {
        "AIModelProfile": {
            "schemaVersion": 1, "profileId": "byok-local-reviewer",
            "displayName": "BYOK Governed Analyst Model", "runtimeClass": "remote",
            "endpointRef": "endpoint:byok-gateway", "modelId": "analyst-pro-v1",
            "credentialRef": "keyring:byok-analyst", "toolCallingSupport": True,
            "structuredOutputSupport": True, "contextLimit": 128000,
            "outputLimit": 8192, "streamingSupport": True,
            "dataResidency": "Canada", "retentionStatement": "Zero provider retention",
            "approvedClassificationMax": "INTERNAL",
            "costModel": {"currency": "CAD"}, "enabled": True,
        },
        "AIConnectorProfile": {
            "schemaVersion": 1, "connectorId": "conn-frappe-firebird",
            "name": "Firebird 5.0 Frappe Suite Metadata Connector", "connectorClass": "database_provider",
            "enabled": True, "providerId": "provider.firebird",
            "connectionProfileRef": f"connection:{fb['endpoint_id']}",
            "dialectId": "firebird", "workareaSchemaRef": None,
            "mcpEndpointRef": None, "mcpProtocolProfile": None,
            "principalBinding": "cdeadmin-readonly-ai",
            "credentialRef": "keyring:fb-readonly", "policyRef": "data-metadata-only",
            "resourceScopeRefs": [fb_db_ref["canonical"]],
            "state": "unconfigured", "capabilitySnapshotRef": None,
        },
        "AIAgentProfile": {
            "schemaVersion": 1, "profileId": "agent-bi-drafter",
            "name": "Frappe BI & ERD Draft Assistant", "description": "Drafts DDN questions and ERD notes; never accepts or mutates live catalogs.",
            "enabled": True, "autonomyMode": "READ_ONLY_TOOLS",
            "modelProfileRef": "byok-local-reviewer",
            "connectorRefs": ["conn-frappe-firebird"], "toolPolicyRef": "tool-read-discovery",
            "dataPolicyRef": "data-metadata-only",
            "approvalPolicyRef": "approval-human-gate",
            "budgetPolicyRef": "budget-analyst",
            "retentionPolicyRef": "retention-audit",
            "instructionAssetRef": "instruction-clean-room", "tags": ["byok", "draft-only"],
        },
        "AIToolPolicy": {
            "schemaVersion": 1, "policyId": "tool-read-discovery",
            "name": "Catalog Discovery & Draft-Only Tool Policy",
            "moduleIds": ["cdeadmin.discovery_intelligence"],
            "commandIds": ["discovery.search"],
            "deniedCommandIds": ["provider.drop", "design.accept", "bi.publish"],
            "maxAutomaticRisk": "R1", "allowProjectDrafts": True,
            "allowBackgroundTasks": False,
        },
        "AIDataPolicy": {
            "schemaVersion": 1, "policyId": "data-metadata-only",
            "name": "Metadata Summary Only (Zero Raw Customer PII)",
            "defaultExposureLevel": "METADATA_SUMMARY",
            "maxClassification": "INTERNAL", "allowRemoteSamples": False,
            "allowRemoteSource": False,
            "sensitiveColumnHandling": "excluded", "maxSampleRows": 10,
            "maxTextCharacters": 2000,
            "allowedModelProfileRefs": ["byok-local-reviewer"],
            "requireLocalForRestricted": True,
            "queryPolicy": {
                "allowRead": True, "allowWrite": False, "allowDDL": False,
                "allowTransactionControl": False, "allowExplain": True,
                "allowSystemCatalog": True, "allowCrossSurface": False,
                "maxRows": 250, "maxResultBytes": 2097152,
                "maxStatementSeconds": 15, "maxStatementsPerPlan": 5,
                "maxParallelQueries": 2,
                "allowedResourceRefs": [fb_db_ref["canonical"]],
                "blockedResourceRefs": [], "allowTemporaryObjects": False,
                "allowStoredProcedureCall": False,
                "allowExternalSideEffectFunctions": False,
            },
        },
        "AIApprovalPolicy": {
            "schemaVersion": 1, "policyId": "approval-human-gate",
            "name": "Mandatory Human Review Gate",
            "riskRules": {
                "R0": "auto", "R1": "auto", "R2": "review_diff",
                "R3": "review", "R4": "confirm_each",
                "R5": "typed_confirm", "R6": "dual_or_typed",
            },
            "expiryMinutes": {"R4": 15, "R5": 5, "R6": 5},
        },
        "AIBudgetPolicy": {
            "schemaVersion": 1, "policyId": "budget-analyst",
            "name": "Analyst Session Token & Query Budget",
            "maxModelInputTokens": 64000, "maxModelOutputTokens": 8192,
            "maxToolCallsPerTurn": 12, "maxToolCallsPerPlan": 40,
            "maxDatabaseQueriesPerTurn": 6, "maxDatabaseRowsPerQuery": 250,
            "maxDatabaseBytesPerQuery": 2097152, "maxParallelTools": 2,
            "maxRunMinutes": 15, "maxBackgroundTasks": 1,
            "maxEstimatedCostPerTurn": 1.5, "maxEstimatedCostPerDay": 20.0,
        },
        "AIRetentionPolicy": {
            "schemaVersion": 1, "policyId": "retention-audit",
            "name": "365-Day Prompt-Redacted Governance Audit",
            "retainMessages": True, "conversationDays": 30,
            "retainToolResults": False, "auditDays": 365,
            "retainPromptsInAudit": False,
        },
        "AIInstructionAsset": {
            "schemaVersion": 1, "instructionId": "instruction-clean-room",
            "name": "ScratchRobin BYOK Clean-Room Drafting Rules",
            "scope": "project",
            "instructions": "Search existing accepted BI questions before proposing new drafts. Never auto-accept, publish, or execute DDL.",
            "locked": True, "versionNote": "Owner rule 2026-11-10 compliance",
        },
        "AIPlan": {
            "schemaVersion": 1, "planId": "plan-inspect-coa", "revision": 1,
            "baseContextRevision": "frappe-ods-13.1",
            "agentProfileRef": "agent-bi-drafter",
            "modelProfileSnapshot": {"profileId": "byok-local-reviewer", "revision": 1},
            "connectorSnapshots": [{"connectorId": "conn-frappe-firebird", "revision": 1}],
            "steps": [{
                "stepId": "step-read-gl-cols", "kind": "READ_METADATA",
                "status": "validated", "commandId": "metadata.read",
                "connectorRef": "conn-frappe-firebird",
                "resourceRefs": [fb_gl_ref["canonical"]], "assetRefs": [],
                "arguments": {"includeColumns": True},
            }],
            "risks": ["R0"], "requiredApprovals": [],
            "validationChecks": ["connector-ready", "metadata-only"],
            "status": "ready_for_approval",
        },
    }
    for kind, content_dict in ai_interface_contracts.items():
        atype = next(k for k, v in AI_INTERFACE_ASSET_TYPES.items() if v == kind)
        _upsert_validated_asset(
            cconn,
            project_key=ai_proj,
            project_uuid=projects_by_key[ai_proj],
            user_id=user_id,
            asset_key=kind,
            request_payload={
                "asset_type": atype,
                "schema_name": atype,
                "schema_version": 1,
                "name": f"AI Governance ({kind}): {content_dict.get('name') or content_dict.get('displayName') or kind}",
                "path": f"ai/{kind}/main.json",
                "expected_version": 0,
                "content": content_dict,
                "metadata": {"moduleId": "cdeadmin.ai_interface", "assetKind": kind},
                "dependency_references": [],
                "resource_bindings": [],
                "validation_state": "valid",
                "validation_details": [],
            },
            now_sql=now_sql,
        )
        bump("cdeadmin.ai_interface.*")

    # 13. Discovery Intelligence Administration & Catalog Assets (cdeadmin.discovery.*)
    disc_proj = "collab-insights"
    discovery_assets = [
        (
            "cdeadmin.discovery.ranking_profile",
            "RankingProfile:frappe-finance-balanced",
            "Discovery Ranking Profile: Frappe Certified Finance & ERP Catalog",
            "discovery/RankingProfile/frappe-finance-balanced.json",
            {
                "schemaVersion": 1,
                "profileId": "frappe-finance-balanced",
                "name": "Frappe Certified Finance & ERP Ranking",
                "weights": {
                    "lexical": 0.22, "semantic": 0.20, "business": 0.14, "trust": 0.12,
                    "quality": 0.08, "freshness": 0.06, "usage": 0.06, "context": 0.04,
                    "lineage": 0.04, "documentation": 0.04,
                },
                "boosts": {
                    "exact_visible_qualified_name": 0.12,
                    "exact_business_term": 0.09,
                    "active_certified_data_product": 0.08,
                },
                "penalties": {
                    "deprecated": -0.30, "retired_archived": -0.45,
                    "critical_quality_failure": -0.20, "freshness_sla_breach": -0.15,
                    "no_owner_steward": -0.03, "unstable_breaking_schema": -0.08,
                },
                "publishedRevision": "frappe-finance-balanced@1",
                "status": "published",
            },
            "RankingProfile",
            [],
        ),
        (
            "cdeadmin.discovery.index_source_config",
            "IndexSourceConfig:firebird-frappe-catalog",
            "Discovery Index Source: Firebird 5.0 Frappe Enterprise Suite (2,939 Tables)",
            "discovery/IndexSourceConfig/firebird-frappe-catalog.json",
            {
                "schemaVersion": 1,
                "sourceId": "firebird-frappe-catalog",
                "name": "Firebird 5.0 Frappe Suite Metadata Indexer",
                "type": "provider_metadata",
                "scope": [fb_db_ref, dk_db_ref, sq_db_ref],
                "enabled": True,
                "mode": "INCREMENTAL_POLL",
                "schedule": "0 */2 * * *",
                "mandatory": True,
                "credentialRef": None,
                "respectProviderVisibility": True,
                "version": "1.0.0",
            },
            "IndexSourceConfig",
            [fb_db_ref, dk_db_ref, sq_db_ref],
        ),
    ]
    for d_type, akey, title, path, content_obj, d_kind, rbs in discovery_assets:
        _upsert_validated_asset(
            cconn,
            project_key=disc_proj,
            project_uuid=projects_by_key[disc_proj],
            user_id=user_id,
            asset_key=akey,
            request_payload={
                "asset_type": d_type,
                "schema_name": d_type,
                "schema_version": 1,
                "name": title,
                "path": path,
                "expected_version": 0,
                "content": content_obj,
                "metadata": {
                    "moduleId": "cdeadmin.discovery_intelligence",
                    "assetKind": d_kind,
                    "logicalId": content_obj.get("profileId") or content_obj.get("sourceId"),
                },
                "dependency_references": [],
                "resource_bindings": rbs,
                "validation_state": "valid",
                "validation_details": [],
            },
            now_sql=now_sql,
        )
        bump("cdeadmin.discovery_intelligence.*")

    return counts_by_module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-root", type=Path, default=DEFAULT_DONOR_ROOT)
    parser.add_argument("--cdeadmin-db", type=Path, default=DEFAULT_CDEADMIN_DB)
    parser.add_argument("--designs-db", type=Path, default=DEFAULT_DESIGNS_DB)
    args = parser.parse_args()

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    now_sql = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    cconn = sqlite3.connect(args.cdeadmin_db, timeout=30.0)
    dconn = sqlite3.connect(args.designs_db, timeout=30.0)
    try:
        user_row = cconn.execute("SELECT id FROM user ORDER BY id LIMIT 1").fetchone()
        user_id = int(user_row[0]) if user_row else 1
        endpoints = _lookup_endpoints(cconn)
        projects_by_key = _project_uuid_map(cconn)

        p1 = seed_pillar_1_cubes(
            dconn,
            cconn,
            projects_by_key=projects_by_key,
            endpoints=endpoints,
            user_id=user_id,
            now_iso=now_iso,
            now_sql=now_sql,
        )
        p2 = seed_pillar_2_bi_dashboards_alerts_and_embeds(
            dconn,
            cconn,
            donor_root=args.donor_root,
            projects_by_key=projects_by_key,
            endpoints=endpoints,
            user_id=user_id,
            now_iso=now_iso,
            now_sql=now_sql,
        )
        p4 = seed_pillar_4_erd_lifecycle_and_deployments(
            dconn,
            endpoints=endpoints,
            user_id=user_id,
            now_iso=now_iso,
        )
        p5 = seed_pillar_5_all_13_platform_modules(
            cconn,
            projects_by_key=projects_by_key,
            endpoints=endpoints,
            user_id=user_id,
            now_sql=now_sql,
        )

        dconn.commit()
        cconn.commit()

        design_totals = dict(
            dconn.execute("SELECT kind, COUNT(*) FROM design GROUP BY kind ORDER BY kind").fetchall()
        )
        version_totals = dict(
            dconn.execute("SELECT status, COUNT(*) FROM design_version GROUP BY status ORDER BY status").fetchall()
        )
        asset_totals = dict(
            cconn.execute("SELECT asset_type, COUNT(*) FROM cde_project_asset GROUP BY asset_type ORDER BY asset_type").fetchall()
        )
    finally:
        dconn.close()
        cconn.close()

    print(
        json.dumps(
            {
                "pillar_1_cubes": len(p1),
                "pillar_2_bi": p2,
                "pillar_4_lifecycle": p4,
                "pillar_5_platform_modules": p5,
                "designs_db_totals_by_kind": design_totals,
                "design_versions_by_status": version_totals,
                "cde_project_asset_totals_by_type": asset_totals,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
