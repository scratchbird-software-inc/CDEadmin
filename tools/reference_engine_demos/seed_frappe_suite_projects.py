#!/usr/bin/env python3
# SPDX-License-Identifier: PostgreSQL
"""Seed a hierarchical, acyclic multi-project Frappe Suite in ScratchRobin.

Creates parent and child projects across every Frappe application, sub-suite,
and accounting/domain sub-section (enforcing strict DAG acyclicity), links
every table used by each application/sub-section (owned tables + foreign-key
referenced master tables) in both ``cdeadmin.db`` (``cde_project``,
``cde_project_asset``, ``cde_project_asset_revision``) and ``designs.db``
(``design``, ``design_version``, ``element``, ``binding``,
``resource_identity``).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
WEB_DIR = REPO_ROOT / "web"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import generate_frappe_firebird_suite as suite_gen  # noqa: E402
from pgadmin.cdeadmin.design_store.bi_ddn import (  # noqa: E402
    default_question_model,
    question_to_ddn,
)
from pgadmin.cdeadmin.design_store.identifiers import uuid7  # noqa: E402
from pgadmin.cdeadmin.design_store.schema import apply_schema  # noqa: E402
from pgadmin.cdeadmin.design_store.screen_mesh_ddn import (  # noqa: E402
    default_screen_mesh_model,
    screen_mesh_to_ddn,
)
from pgadmin.cdeadmin.design_store.shared_ddn import (  # noqa: E402
    apply_layout_to_ddn_text,
    build_four_level_erd_ddn,
    compute_server_layout,
)


DEFAULT_CONFIG_DB = Path("/home/dcalford/.cdeadmin/cdeadmin.db")
DEFAULT_DESIGNS_DB = Path("/home/dcalford/.cdeadmin/designs.db")
DEFAULT_DB_PATH = "/var/lib/firebird/data/frappe_suite.fdb"


def slugify(text: str, max_len: int = 64) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return (s[:max_len].rstrip("-") or "project")


# Structural parent projects forming levels 1..3 of the acyclic DAG.
STRUCTURAL_PARENTS: list[tuple[str, str | None, str, str]] = [
    (
        "frappe-enterprise-suite",
        None,
        "Frappe Enterprise Suite (Firebird 5.0)",
        "Umbrella multi-project workspace uniting all Frappe applications, sub-ledgers, cloud orchestration, and companion SQL services on Firebird 5.0.",
    ),
    # Level 2 domain suites
    (
        "suite-frappe-framework",
        "frappe-enterprise-suite",
        "Frappe Core Framework & Desk",
        "Core metadata engine, authentication, workspaces, website portal, workflow automation, printing, email, and integrations.",
    ),
    (
        "suite-erpnext",
        "frappe-enterprise-suite",
        "ERPNext Enterprise Suite",
        "Full enterprise resource planning suite partitioned into Accounting Ledgers, Supply Chain, and Manufacturing/Asset sub-projects.",
    ),
    (
        "suite-hrms",
        "frappe-enterprise-suite",
        "Human Resources & Payroll (HRMS)",
        "Employee lifecycle, organizational hierarchy, attendance/leave ledgers, appraisals, expenses, and payroll/tax processing.",
    ),
    (
        "suite-crm-support",
        "frappe-enterprise-suite",
        "CRM, Helpdesk & Omnichannel",
        "Customer acquisition, sales pipeline deals, SLA support ticketing, telephony, WhatsApp, and live chat.",
    ),
    (
        "suite-financial-services",
        "frappe-enterprise-suite",
        "Lending, Payments & Accounting Apps",
        "Loan origination & servicing ledgers, payment gateways, standalone Frappe Books, and Mobile Accounting.",
    ),
    (
        "suite-education-lms",
        "frappe-enterprise-suite",
        "Education, Campus & LMS",
        "Academic curriculum, student admissions & fee ledgers, grading assessments, and online LMS cohorts.",
    ),
    (
        "suite-collaboration-bi",
        "frappe-enterprise-suite",
        "Collaboration, BI & Content Apps",
        "Insights analytics, Raven team messaging, Gameplan async projects, Drive storage, Wiki, Web Builder, and Mail/Stalwart.",
    ),
    (
        "suite-cloud-infra",
        "frappe-enterprise-suite",
        "Cloud, Press, Telemetry & Hypervisor",
        "Frappe Cloud (Press), Central billing, Suite Cloud, Datum + Cargo telemetry, and Boat Firecracker VM orchestration.",
    ),
    (
        "suite-industry-verticals",
        "frappe-enterprise-suite",
        "Industry Verticals & Regional Compliance",
        "Agriculture, Hospitality, Non-Profit, regional tax compliance extensions, and specialized Frappe applications.",
    ),
    # Level 3 sub-suites under ERPNext & Cloud
    (
        "erpnext-accounting",
        "suite-erpnext",
        "ERPNext Accounting & Sub-Ledgers",
        "Financial accounting decomposed into General Ledger, Accounts Receivable, Accounts Payable, Banking/Treasury, Costing/Budgets, Tax/Pricing, and POS/Subscriptions.",
    ),
    (
        "erpnext-supply-chain",
        "suite-erpnext",
        "ERPNext Supply Chain & Inventory",
        "Stock ledger valuation, warehouse bins, fulfillment/receipts, selling orders, buying procurement, and quality management.",
    ),
    (
        "erpnext-manufacturing-ops",
        "suite-erpnext",
        "ERPNext Manufacturing, Assets & Projects",
        "BOM engineering, shop-floor work orders, fixed asset depreciation schedules, project costing, and enterprise setup.",
    ),
    (
        "press-cloud-platform",
        "suite-cloud-infra",
        "Frappe Press Cloud Platform",
        "Multi-tenant cloud control plane decomposed into Sites/Benches, Clusters/Servers, SaaS/Billing, Monitoring/TLS, and Compute Agents.",
    ),
]


def classify_table_to_project(spec: suite_gen.TableSpec) -> tuple[str, str, str, str]:
    """Return (project_key, parent_project_key, display_name, description) for a TableSpec."""
    app = spec.source_app
    mod = spec.module
    oname = spec.orig_name.lower()
    tname = spec.table_name

    # 1. Companion & Standalone non-DocType apps
    if tname == "SUITE_PROJECT_CATALOG" or app == "frappe" and spec.kind == "system":
        return (
            "frappe-core-engine",
            "suite-frappe-framework",
            "Frappe — Core Metadata, Auth & Runtime",
            "Core DocType metadata, authentication, series counters, singles store, users, roles, and permissions.",
        )
    if app == "books":
        if any(k in oname for k in ("ledger", "journal", "account", "tax", "budget")):
            return (
                "books-desktop-ledger",
                "suite-financial-services",
                "Standalone Books — Ledger, Accounts & Tax (FBK)",
                "Frappe Books desktop general ledger, chart of accounts, journal entries, and tax schemas.",
            )
        return (
            "books-desktop-commercial",
            "suite-financial-services",
            "Standalone Books — Invoicing, Inventory & POS (FBK)",
            "Frappe Books desktop sales/purchase invoices, items, batches, POS, and party schemas.",
        )
    if app in ("datum", "cargo"):
        return (
            "datum-cargo-telemetry",
            "suite-cloud-infra",
            "Datum & Cargo — Metrics, Logs & Traces",
            "Time-series metrics, structured logs, daily rollup triggers, distributed OpenTelemetry spans, and Cargo fleet views.",
        )
    if app == "stalwart":
        return (
            "stalwart-mail-store",
            "suite-collaboration-bi",
            "Stalwart — JMAP/SMTP Directory & Binary Store",
            "Stalwart SQL directory accounts, groups, email aliases, and binary KV/blob mail store.",
        )
    if app == "boat":
        return (
            "boat-hypervisor",
            "suite-cloud-infra",
            "Boat — Firecracker VMs, Volumes & Decision Journal",
            "Boat hypervisor virtual machine power states, attached volumes, and write-ahead idempotency journal.",
        )
    if app == "mobile-accounting":
        return (
            "mobile-accounting-app",
            "suite-financial-services",
            "Mobile Accounting — Accounts, Parties & Items",
            "Mobile Accounting SQLite schema adapted to Firebird with cascading account and tax foreign keys.",
        )
    if app == "pywall":
        return (
            "pywall-board",
            "suite-industry-verticals",
            "PyWall — Community Message Wall",
            "PyWall community message board schema adapted to Firebird 5.0.",
        )

    # 2. ERPNext Accounting decomposed into 7 individual Ledger / Sub-Section projects!
    if app in ("erpnext", "erpnext_local", "erpnext-14") and mod == "Accounts":
        if any(k in oname for k in ("pos ", "pos_", "point of sale", "loyalty", "coupon", "subscription", "shareholder", "share ")):
            return (
                "erpnext-acc-pos-subscriptions",
                "erpnext-accounting",
                "Accounting — POS, Loyalty, Subscriptions & Equity",
                "Point-of-sale invoices, POS profiles, loyalty point ledgers, recurring subscriptions, and shareholder equity.",
            )
        if any(k in oname for k in ("sales invoice", "dunning", "payment request", "promotional", "customer", "debit note")):
            return (
                "erpnext-acc-receivables",
                "erpnext-accounting",
                "Accounting — Accounts Receivable & Sales Billing",
                "Customer billing sub-ledger, sales invoices, invoice line items, payment requests, and dunning workflows.",
            )
        if any(k in oname for k in ("purchase invoice", "supplier", "payment order", "withholding", "lower deduction", "bill")):
            return (
                "erpnext-acc-payables",
                "erpnext-accounting",
                "Accounting — Accounts Payable & Purchase Billing",
                "Vendor payables sub-ledger, purchase invoices, tax withholding ledgers, and supplier payment orders.",
            )
        if any(k in oname for k in ("payment entry", "payment ledger", "bank", "cheque", "mode of payment", "pegged", "clearance", "process payment")):
            return (
                "erpnext-acc-banking-payments",
                "erpnext-accounting",
                "Accounting — Payment Ledger, Banking & Treasury",
                "Payment ledger entries, payment vouchers, bank accounts, statement imports, and reconciliation.",
            )
        if any(k in oname for k in ("cost center", "budget", "financial report", "monthly distribution", "bisect", "cash flow")):
            return (
                "erpnext-acc-costing-budgets",
                "erpnext-accounting",
                "Accounting — Cost Centers, Budgets & Financial Statements",
                "Cost center hierarchy, allocation rules, departmental budgets, and financial report templates.",
            )
        if any(k in oname for k in ("tax", "pricing rule", "shipping rule", "exchange rate", "currency exchange", "payment term")):
            return (
                "erpnext-acc-taxes-pricing",
                "erpnext-accounting",
                "Accounting — Taxes, Pricing Rules & FX",
                "Sales/purchase tax templates, tax categories, multi-currency exchange revaluation, payment terms, and pricing rules.",
            )
        return (
            "erpnext-acc-general-ledger",
            "erpnext-accounting",
            "Accounting — General Ledger, Journals & Chart of Accounts",
            "Core double-entry General Ledger (GL_ENTRY), hierarchical Chart of Accounts, Journal Entries, Fiscal Years, and Accounting Dimensions.",
        )

    # 3. ERPNext Stock, Selling, Buying, Manufacturing, Assets, Projects, Setup
    if app in ("erpnext", "erpnext_local", "erpnext-14"):
        if mod == "Stock":
            if any(k in oname for k in ("delivery", "purchase receipt", "pick list", "packing", "material request", "landed cost", "quality", "shipment")):
                return (
                    "erpnext-stock-fulfillment",
                    "erpnext-supply-chain",
                    "Stock — Fulfillment, Receipts & Landed Cost",
                    "Inbound purchase receipts, outbound delivery notes, pick lists, packing slips, material requests, and landed cost vouchers.",
                )
            return (
                "erpnext-stock-ledger",
                "erpnext-supply-chain",
                "Stock — Inventory Ledger, Items & Warehouses",
                "Stock Ledger Entry valuation, Warehouse trees, Item masters, Batches, Serial Numbers, and Stock Reconciliation.",
            )
        if mod == "Selling":
            return (
                "erpnext-selling-orders",
                "erpnext-supply-chain",
                "Selling — Quotations, Customers & Sales Orders",
                "Customer masters, quotations, sales orders, blanket orders, sales partners, and commission schedules.",
            )
        if mod == "Buying":
            return (
                "erpnext-buying-procurement",
                "erpnext-supply-chain",
                "Buying — Suppliers, RFQs & Purchase Orders",
                "Supplier masters, requests for quotation, supplier scorecards, and purchase order workflows.",
            )
        if mod == "Quality Management":
            return (
                "erpnext-quality-mgmt",
                "erpnext-supply-chain",
                "Quality Management — Inspections, Goals & Non-Conformance",
                "Quality goals, procedures, reviews, action plans, and non-conformance tracking.",
            )
        if mod == "Manufacturing":
            if any(k in oname for k in ("bom", "routing", "operation", "workstation", "blanket")):
                return (
                    "erpnext-mfg-bom",
                    "erpnext-manufacturing-ops",
                    "Manufacturing — BOM, Routing & Workstations",
                    "Multi-level Bills of Materials, operations, routings, and plant workstation capacities.",
                )
            return (
                "erpnext-mfg-production",
                "erpnext-manufacturing-ops",
                "Manufacturing — Work Orders, Job Cards & MRP",
                "Production plans, shop-floor work orders, time-tracked job cards, and downtime logs.",
            )
        if mod == "Assets":
            return (
                "erpnext-fixed-assets",
                "erpnext-manufacturing-ops",
                "ERPNext — Fixed Assets, Depreciation & Maintenance",
                "Asset capitalization, depreciation schedules, asset movements, value adjustments, and preventive maintenance.",
            )
        if mod == "Projects":
            return (
                "erpnext-projects",
                "erpnext-manufacturing-ops",
                "ERPNext — Projects, Tasks & Timesheets",
                "Project costing, milestones, tasks, activity types, and billable employee timesheets.",
            )
        return (
            f"erpnext-{slugify(mod, 36)}",
            "erpnext-manufacturing-ops",
            f"ERPNext — {mod}",
            f"ERPNext {mod} module tables and linked master data in Firebird 5.0.",
        )

    # 4. Frappe Framework modules
    if app == "frappe":
        if mod == "Core":
            return (
                "frappe-core-engine",
                "suite-frappe-framework",
                "Frappe — Core Metadata, Auth & Runtime",
                "Core DocType metadata, authentication, series counters, singles store, users, roles, and permissions.",
            )
        return (
            f"frappe-{slugify(mod, 40)}",
            "suite-frappe-framework",
            f"Frappe Framework — {mod}",
            f"Frappe framework {mod} sub-system tables and linked core entities.",
        )

    # 5. HRMS sub-sections
    if app in ("hrms", "india-payroll", "india_payroll"):
        if mod == "Payroll" or "payroll" in app:
            return (
                "hrms-payroll-tax",
                "suite-hrms",
                "HRMS — Payroll Ledger, Salary Slips & Tax",
                "Salary structures, payroll entries, salary slips, employee tax exemptions, and benefit claims.",
            )
        if any(k in oname for k in ("attendance", "shift", "leave", "holiday", "compensatory")):
            return (
                "hrms-attendance-leave",
                "suite-hrms",
                "HRMS — Attendance, Shifts & Leave Ledger",
                "Biometric check-ins, shift rosters, holiday lists, leave allocations, and leave ledger entries.",
            )
        if any(k in oname for k in ("job ", "applicant", "interview", "offer", "onboarding", "separation", "promotion", "transfer")):
            return (
                "hrms-recruitment-lifecycle",
                "suite-hrms",
                "HRMS — Recruitment, Onboarding & Lifecycle",
                "Job requisitions, applicants, interviews, offers, onboarding activities, transfers, and exits.",
            )
        if any(k in oname for k in ("appraisal", "goal", "kra", "training", "expense", "travel", "vehicle", "advance")):
            return (
                "hrms-performance-expense",
                "suite-hrms",
                "HRMS — Performance, Training, Fleet & Expenses",
                "Employee appraisals, KRAs, training events, employee advances, travel requests, and expense claims.",
            )
        return (
            "hrms-employee-org",
            "suite-hrms",
            "HRMS — Core Employee, Organization & Grievance",
            "Employee master records, departments, designations, grades, health insurance, and grievances.",
        )

    # 6. Lending sub-sections
    if app == "lending":
        if mod == "Loan Origination" or any(k in oname for k in ("application", "product", "sanction", "credit", "co-applicant")):
            return (
                "lending-origination",
                "suite-financial-services",
                "Lending — Loan Products & Origination",
                "Loan products, interest models, credit origination applications, and collateral pledges.",
            )
        return (
            "lending-servicing-ledger",
            "suite-financial-services",
            "Lending — Loan Servicing, Disbursements & Repayments",
            "Active loan ledgers, disbursements, repayment schedules, interest accruals, and write-offs.",
        )

    # 7. Education, Schools & LMS sub-sections
    if app in ("education", "schools", "school_automations"):
        if any(k in oname for k in ("fee", "admission", "applicant", "student", "guardian", "attendance")):
            return (
                "education-admissions-fees",
                "suite-education-lms",
                "Education — Admissions, Students & Fee Ledger",
                "Student applicants, enrollments, guardians, attendance, fee structures, and fee schedules.",
            )
        if any(k in oname for k in ("assessment", "grading", "quiz", "result", "scorecard")):
            return (
                "education-assessments",
                "suite-education-lms",
                "Education — Assessments, Quizzes & Grading",
                "Assessment plans, grading scales, exam results, and academic scorecards.",
            )
        return (
            "education-curriculum",
            "suite-education-lms",
            "Education — Programs, Courses & Timetables",
            "Academic years, terms, degree programs, courses, topics, rooms, and course schedules.",
        )
    if app in ("lms", "academy"):
        return (
            "frappe-lms-courses",
            "suite-education-lms",
            "Frappe LMS — Online Courses, Cohorts & Certifications",
            "Self-paced LMS courses, lessons, live batches, quizzes, assignments, and certificates.",
        )

    # 8. Press / Cloud Infrastructure sub-sections
    if app in ("press", "press-agent-manager", "press-compute-orchestrator", "press-compute-agent"):
        if "agent" in app or "compute" in app:
            return (
                f"cloud-{slugify(app, 42)}",
                "press-cloud-platform",
                f"Press Cloud — {app.replace('-', ' ').title()}",
                f"Compute orchestration and host agent tables for {app}.",
            )
        if mod in ("Billing", "Marketplace", "SaaS", "Partner") or any(k in oname for k in ("invoice", "plan", "subscription", "stripe", "razorpay", "balance", "marketplace")):
            return (
                "press-billing-marketplace",
                "press-cloud-platform",
                "Press Cloud — Billing, Subscriptions, SaaS & Marketplace",
                "Cloud tenant subscriptions, usage metering, invoices, partner credits, and marketplace apps.",
            )
        if any(k in oname for k in ("server", "proxy", "database server", "cluster", "region", "orchestrat", "virtual machine")):
            return (
                "press-servers-clusters",
                "press-cloud-platform",
                "Press Cloud — Servers, Proxies & DB Clusters",
                "Managed MariaDB/Proxy/App servers, Kubernetes/region topology, and cluster provisioning.",
            )
        if any(k in oname for k in ("tls", "certificate", "backup", "monitor", "log", "analytics", "incident")):
            return (
                "press-monitoring-tls",
                "press-cloud-platform",
                "Press Cloud — Backups, TLS & Site Telemetry",
                "Automated offsite backups, Let's Encrypt TLS certificates, uptime checks, and error logs.",
            )
        return (
            "press-sites-benches",
            "press-cloud-platform",
            "Press Cloud — Sites, Benches & App Releases",
            "Multi-tenant Frappe sites, isolated bench groups, deploy candidates, domains, and release pipelines.",
        )

    # 9. CRM, Helpdesk & Omnichannel
    if app == "crm":
        return (
            "frappe-crm",
            "suite-crm-support",
            "Frappe CRM — Leads, Deals, Contacts & Call Logs",
            "Modern sales pipeline deals, lead qualification, organizations, SLAs, and call logs.",
        )
    if app in ("helpdesk", "helpdesk_sentry"):
        return (
            "frappe-helpdesk",
            "suite-crm-support",
            "Frappe Helpdesk — Tickets, SLAs & Knowledge Base",
            "Customer support ticket queues, agent teams, SLA policies, canned responses, and KB articles.",
        )
    if app in ("whatsapp", "telephony", "chat", "twilio-integration", "exotel_integration"):
        return (
            f"omnichannel-{slugify(app, 40)}",
            "suite-crm-support",
            f"Omnichannel — {app.replace('_', ' ').replace('-', ' ').title()}",
            f"Customer messaging and telephony integration tables for {app}.",
        )

    # 10. Financial / E-commerce / Books apps
    if app in ("frappe-books", "accounting-archive"):
        return (
            "frappe-books-cloud",
            "suite-financial-services",
            "Frappe Books (Frappe App Edition)",
            "Frappe-based bookkeeping ledgers, invoices, parties, and accounting rules.",
        )
    if app in (
        "payments", "webshop", "ecommerce_integrations", "shop",
        "taxjar_integration", "paypal_integration", "razorpay_integration",
        "erpnext_shopify", "erpnext_shopify_broker", "erpnext-shipping",
    ):
        return (
            f"commerce-{slugify(app, 42)}",
            "suite-financial-services",
            f"Payments & Commerce — {app.replace('_', ' ').replace('-', ' ').title()}",
            f"Payment gateway, shipping, tax, and e-commerce storefront tables for {app}.",
        )

    # 11. Workplace Collaboration, BI & Content apps
    if app in (
        "insights", "raven", "raven_integration", "gameplan", "gameplan-old",
        "drive", "wiki", "builder", "builder_hub", "mail", "mail_migrator",
        "slides", "sheets", "draw", "print_designer", "studio", "frappe-forms",
        "newsletter", "meet",
    ):
        clean_app = "gameplan" if app == "gameplan-old" else app
        key = f"collab-{slugify(clean_app, 30)}-{slugify(mod, 24)}" if clean_app in ("mail", "central", "suite") else f"collab-{slugify(clean_app, 42)}"
        title_suffix = f" ({mod})" if clean_app == "mail" else ""
        return (
            key,
            "suite-collaboration-bi",
            f"Collaboration — {clean_app.replace('_', ' ').replace('-', ' ').title()}{title_suffix}",
            f"Tables and linked resources for {clean_app} ({mod}).",
        )

    # 12. Cloud / Central / Suite / Security / Fleet apps
    if app in (
        "central", "suite", "suite_cloud", "atlas", "guard", "panoptic",
        "pulse", "bench_manager", "release", "release_manager",
        "offsite_backups", "storage_integration", "event_streaming", "flow_client",
    ):
        key = f"cloud-{slugify(app, 28)}-{slugify(mod, 24)}" if app in ("central", "suite", "suite_cloud") else f"cloud-{slugify(app, 42)}"
        extra = f" ({mod})" if app in ("central", "suite", "suite_cloud") else ""
        return (
            key,
            "suite-cloud-infra",
            f"Cloud & Ops — {app.replace('_', ' ').replace('-', ' ').title()}{extra}",
            f"Cloud operations, billing, security, and orchestration tables for {app} ({mod}).",
        )

    # 13. All remaining Industry Verticals & Specialized Frappe Apps -> each app gets its own child project!
    return (
        f"app-{slugify(app, 48)}",
        "suite-industry-verticals",
        f"Vertical App — {app.replace('_', ' ').replace('-', ' ').title()}",
        f"Application tables and foreign-key master table bindings for Frappe project '{app}' (module: {mod}).",
    )


def verify_acyclic_hierarchy(parent_by_key: dict[str, str | None]) -> None:
    """Assert strict DAG acyclicity across every project before writing anything."""
    for pkey in parent_by_key:
        visited: set[str] = set()
        cur: str | None = pkey
        while cur is not None:
            if cur in visited:
                raise RuntimeError(f"Circular project hierarchy detected at {cur}!")
            visited.add(cur)
            cur = parent_by_key.get(cur)


def upgrade_and_prepare_config_db(
    config_db: Path, db_path: str
) -> tuple[int, str, str]:
    """Backup cdeadmin.db, apply cde_project.parent_project_id if needed, and return (user_id, endpoint_id, target_id)."""
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    bak = config_db.with_name(f"{config_db.name}.projects-seed-{ts}.bak")
    with sqlite3.connect(config_db) as src, sqlite3.connect(bak) as dst:
        src.backup(dst)

    reg = suite_gen.register_in_scratchrobin_config(config_db, db_path)
    if not reg.get("registered"):
        raise RuntimeError(f"Failed to register {db_path}: {reg}")

    with sqlite3.connect(config_db) as conn:
        cur = conn.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(cde_project)").fetchall()}
        if "parent_project_id" not in cols:
            cur.execute(
                "ALTER TABLE cde_project ADD COLUMN parent_project_id VARCHAR(36) "
                "REFERENCES cde_project(id) ON DELETE SET NULL"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS ix_cde_project_parent "
                "ON cde_project (parent_project_id)"
            )
        cur.execute("UPDATE version SET value = 61 WHERE name = 'ConfigDB' AND value < 61")
        cur.execute("UPDATE alembic_version SET version_num = 'cde_project_hierarchy_v1'")
        user_row = cur.execute("SELECT id FROM user ORDER BY id LIMIT 1").fetchone()
        if not user_row:
            raise RuntimeError("No user found in cdeadmin.db")
        user_id = int(user_row[0])
        conn.commit()

    return user_id, str(reg["endpoint_id"]), str(reg["target_id"])


def build_resource_ref(
    endpoint_id: str,
    target_id: str,
    object_name: str,
    role: str = "owned",
    kind: str = "table",
) -> dict[str, str]:
    return {
        "schema": "cdeadmin.resource-ref.v1",
        "provider": "firebird",
        "endpointId": endpoint_id,
        "databaseTargetId": target_id,
        "scope": "/var/lib/firebird/data/frappe_suite.fdb",
        "kind": kind,
        "nativeIdentity": object_name,
        "resource_id": f"{kind}:{object_name}",
        "bindingRole": role,
        "canonical": f"cde-resource://firebird/{endpoint_id}/{target_id}/{kind}/{object_name}",
    }


PROJECT_EXTRA_DB_OBJECTS: dict[str, list[tuple[str, str]]] = {
    "frappe-enterprise-suite": [
        ("view", "VW_SUITE_PROJECT_SUMMARY"),
        ("view", "VW_ERP_GL_TRIAL_BALANCE"),
        ("procedure", "SP_COMPANY_FINANCIAL_SNAPSHOT"),
        ("package", "PKG_FRAPPE_SUITE"),
        ("function", "FN_DOCSTATUS_LABEL"),
        ("function", "FN_FISCAL_QUARTER"),
    ],
    "erpnext-accounting": [
        ("view", "VW_ERP_GL_TRIAL_BALANCE"),
        ("view", "VW_ERP_AR_AGING"),
        ("view", "VW_ERP_AP_AGING"),
        ("procedure", "SP_COMPANY_FINANCIAL_SNAPSHOT"),
        ("package", "PKG_FRAPPE_SUITE"),
        ("function", "FN_FISCAL_QUARTER"),
    ],
    "erpnext-acc-general-ledger": [
        ("view", "VW_ERP_GL_TRIAL_BALANCE"),
        ("procedure", "SP_COMPANY_FINANCIAL_SNAPSHOT"),
        ("package", "PKG_FRAPPE_SUITE"),
        ("function", "FN_DOCSTATUS_LABEL"),
        ("function", "FN_FISCAL_QUARTER"),
        ("sequence", "SEQ_GL_ENTRY"),
    ],
    "erpnext-acc-receivables": [
        ("view", "VW_ERP_AR_AGING"),
        ("package", "PKG_FRAPPE_SUITE"),
        ("function", "FN_DOCSTATUS_LABEL"),
        ("sequence", "SEQ_SALES_INVOICE"),
    ],
    "erpnext-acc-payables": [
        ("view", "VW_ERP_AP_AGING"),
        ("function", "FN_DOCSTATUS_LABEL"),
        ("sequence", "SEQ_PURCHASE_INVOICE"),
    ],
    "erpnext-acc-banking-payments": [
        ("package", "PKG_FRAPPE_SUITE"),
        ("sequence", "SEQ_PAYMENT_ENTRY"),
    ],
    "erpnext-selling-orders": [
        ("view", "VW_ERP_AR_AGING"),
        ("sequence", "SEQ_SALES_ORDER"),
    ],
    "erpnext-buying-procurement": [
        ("view", "VW_ERP_AP_AGING"),
        ("sequence", "SEQ_PURCHASE_ORDER"),
    ],
    "erpnext-stock-ledger": [
        ("view", "VW_ERP_STOCK_VALUATION"),
        ("sequence", "SEQ_STOCK_LEDGER"),
    ],
    "hrms-payroll-tax": [
        ("view", "VW_HRMS_PAYROLL_SUMMARY"),
        ("sequence", "SEQ_EMPLOYEE"),
    ],
    "hrms-employee-org": [
        ("procedure", "SP_COMPANY_FINANCIAL_SNAPSHOT"),
        ("sequence", "SEQ_EMPLOYEE"),
    ],
    "frappe-crm": [
        ("sequence", "SEQ_CRM_DEAL"),
    ],
    "frappe-helpdesk": [
        ("view", "VW_HELPDESK_SLA_BOARD"),
        ("sequence", "SEQ_HD_TICKET"),
    ],
    "lending-servicing-ledger": [
        ("view", "VW_LENDING_PORTFOLIO"),
    ],
    "frappe-lms-courses": [
        ("view", "VW_LMS_CATALOG_METRICS"),
        ("sequence", "SEQ_LMS_ENROLLMENT"),
    ],
    "datum-cargo-telemetry": [
        ("view", "VW_DATUM_DAILY_INGESTION_STATS"),
        ("view", "VW_DATUM_DAILY_LOG_STATS"),
        ("view", "VW_CARGO_OVERVIEW"),
        ("view", "VW_CARGO_DB_QUERIES"),
    ],
    "boat-hypervisor": [
        ("view", "VW_CLOUD_INFRA_FLEET"),
    ],
    "press-sites-benches": [
        ("sequence", "SEQ_PRESS_DEPLOY"),
    ],
}

FULL_SHOWCASE_PROJECTS = set(PROJECT_EXTRA_DB_OBJECTS.keys()) | {
    p[0] for p in STRUCTURAL_PARENTS
} | {
    "frappe-core-engine",
    "erpnext-acc-costing-budgets",
    "erpnext-acc-taxes-pricing",
    "erpnext-acc-pos-subscriptions",
    "erpnext-mfg-bom",
    "erpnext-mfg-production",
    "stalwart-mail-store",
    "books-desktop-ledger",
    "mobile-accounting-app",
}


def build_sql_notebook_payload(
    project_name: str,
    description: str,
    owned_tables: list[str],
    shared_tables: list[str],
    fks_in_scope: list[suite_gen.ForeignKeySpec],
) -> dict[str, object]:
    cells: list[dict[str, object]] = [
        {
            "id": "overview",
            "kind": "note",
            "source": (
                f"# {project_name}\n\n"
                f"{description}\n\n"
                f"- **Owned Tables**: `{len(owned_tables)}`\n"
                f"- **Linked Master Tables (FKs)**: `{len(shared_tables)}`\n"
                f"- **Target Database**: `/var/lib/firebird/data/frappe_suite.fdb` (Firebird 5.0)"
            ),
        }
    ]
    sample_tables = (owned_tables or shared_tables)[:4]
    for idx, tname in enumerate(sample_tables, start=1):
        cells.append({
            "id": f"preview-{idx}",
            "kind": "sql",
            "source": f"SELECT FIRST 25 *\nFROM {tname};",
            "snapshot": None,
        })
    if fks_in_scope:
        fk = fks_in_scope[0]
        cells.append({
            "id": "fk-join-check",
            "kind": "sql",
            "source": (
                f"SELECT FIRST 25\n"
                f"  c.DOC_NAME AS SOURCE_ID,\n"
                f"  c.{fk.source_col} AS LINKED_KEY,\n"
                f"  p.{fk.target_col} AS TARGET_ID\n"
                f"FROM {fk.source_table} c\n"
                f"JOIN {fk.target_table} p ON p.{fk.target_col} = c.{fk.source_col};"
            ),
            "snapshot": None,
        })
    if owned_tables:
        in_list = ", ".join(f"'{t}'" for t in owned_tables[:25])
        cells.append({
            "id": "catalog-audit",
            "kind": "sql",
            "source": (
                "SELECT\n"
                "  TRIM(r.RDB$RELATION_NAME) AS TABLE_NAME,\n"
                "  r.RDB$DESCRIPTION AS PROVENANCE\n"
                "FROM RDB$RELATIONS r\n"
                f"WHERE TRIM(r.RDB$RELATION_NAME) IN ({in_list})\n"
                "ORDER BY 1;"
            ),
            "snapshot": None,
        })
    return {
        "format": "scratchrobin.sql-notebook@1",
        "scope": None,
        "cells": cells,
    }


def seed_projects_and_bindings(
    *,
    donor_root: Path,
    dialect_json: Path,
    config_db: Path,
    designs_db: Path,
    db_path: str,
) -> dict[str, object]:
    reserved = suite_gen.load_reserved_words(dialect_json)
    _cat, tables_by_name, _dt_map, fks = suite_gen.discover_and_compile_schemas(
        donor_root, reserved
    )
    user_id, endpoint_id, target_id = upgrade_and_prepare_config_db(
        config_db, db_path
    )

    if designs_db.is_file():
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        dbak = designs_db.with_name(f"{designs_db.name}.projects-seed-{ts}.bak")
        with sqlite3.connect(designs_db) as src, sqlite3.connect(dbak) as dst:
            src.backup(dst)

    # Outgoing FK map: source_table -> list of ForeignKeySpec
    fks_by_source: dict[str, list[suite_gen.ForeignKeySpec]] = defaultdict(list)
    for fk in fks:
        fks_by_source[fk.source_table].append(fk)

    # Partition all 2,939 tables into leaf projects
    project_defs: dict[str, dict[str, object]] = {}
    parent_by_key: dict[str, str | None] = {}

    for pkey, parent_key, pname, pdesc in STRUCTURAL_PARENTS:
        project_defs[pkey] = {
            "key": pkey,
            "parent_key": parent_key,
            "name": pname[:128],
            "description": pdesc,
            "owned_tables": [],
        }
        parent_by_key[pkey] = parent_key

    for tname, spec in sorted(tables_by_name.items()):
        pkey, parent_key, pname, pdesc = classify_table_to_project(spec)
        if pkey not in project_defs:
            project_defs[pkey] = {
                "key": pkey,
                "parent_key": parent_key,
                "name": pname[:128],
                "description": pdesc,
                "owned_tables": [],
            }
            parent_by_key[pkey] = parent_key
        project_defs[pkey]["owned_tables"].append(tname)

    # Verify strict DAG acyclicity across all projects!
    verify_acyclic_hierarchy(parent_by_key)

    # Compute children map so umbrella parent projects also summarize representative anchor tables
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for pkey, pparent in parent_by_key.items():
        if pparent:
            children_by_parent[pparent].append(pkey)

    def collect_representative_tables(pkey: str) -> list[str]:
        own = list(project_defs[pkey]["owned_tables"])
        if own:
            return own
        rep: list[str] = []
        for child_key in sorted(children_by_parent.get(pkey, [])):
            child_tables = collect_representative_tables(child_key)
            rep.extend(child_tables[:3])
        return sorted(set(rep))[:24]

    # Topologically order projects (parents before children)
    ordered_keys: list[str] = []
    visited_order: set[str] = set()

    def visit(k: str) -> None:
        if k in visited_order:
            return
        p = parent_by_key.get(k)
        if p:
            visit(p)
        visited_order.add(k)
        ordered_keys.append(k)

    for k in sorted(project_defs.keys()):
        visit(k)

    now_iso = datetime.now(timezone.utc).isoformat()
    now_sql = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Open both SQLite stores and populate atomically
    dconn = sqlite3.connect(designs_db, timeout=30.0)
    dconn.execute("PRAGMA foreign_keys = ON")
    apply_schema(dconn, is_sqlite=True)

    cconn = sqlite3.connect(config_db, timeout=30.0)
    cconn.execute("PRAGMA foreign_keys = ON")

    total_bindings = 0
    total_assets = 0

    try:
        # 1. Upsert all 2,939 tables in designs.db resource_identity
        for tname in sorted(tables_by_name.keys()):
            res_ref = f"table:{tname}"
            existing_ri = dconn.execute(
                """
                SELECT id FROM resource_identity
                WHERE engine = 'firebird' AND endpoint_id = ?
                  AND database_target_id = ? AND resource_id = ?
                """,
                (endpoint_id, target_id, res_ref),
            ).fetchone()
            if not existing_ri:
                dconn.execute(
                    """
                    INSERT INTO resource_identity (
                      id, engine, endpoint_id, database_target_id,
                      resource_kind, resource_id, previous_ids, last_seen_at
                    ) VALUES (?, 'firebird', ?, ?, 'table', ?, '[]', ?)
                    """,
                    (uuid7(), endpoint_id, target_id, res_ref, now_iso),
                )
        dconn.commit()

        project_uuid_by_key: dict[str, str] = {}

        # 2. Upsert cde_project rows in topological parent->child order
        for pkey in ordered_keys:
            pdef = project_defs[pkey]
            parent_key = pdef["parent_key"]
            parent_uuid = project_uuid_by_key.get(parent_key) if parent_key else None
            row = cconn.execute(
                "SELECT id, revision FROM cde_project WHERE project_key = ?",
                (pkey,),
            ).fetchone()
            if row:
                puuid = row[0]
                cconn.execute(
                    """
                    UPDATE cde_project
                    SET parent_project_id = ?, name = ?, description = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (parent_uuid, pdef["name"], pdef["description"], now_sql, puuid),
                )
            else:
                # Ensure unique (user_id, name) constraint safety
                puuid = str(uuid.uuid4())
                cconn.execute(
                    """
                    INSERT INTO cde_project (
                      id, user_id, parent_project_id, project_key, name,
                      description, classification_reference, permission_reference,
                      source_control_eligible, revision, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'internal', NULL, 1, 0, ?, ?)
                    """,
                    (
                        puuid,
                        user_id,
                        parent_uuid,
                        pkey,
                        pdef["name"],
                        pdef["description"],
                        now_sql,
                        now_sql,
                    ),
                )
            project_uuid_by_key[pkey] = puuid
        cconn.commit()

        # 3. For each project, compute owned + FK-referenced tables, create DesignStore ERD + bindings,
        #    and create matching cde_project_asset rows (ERD + SQL Notebook) with full resource_bindings!
        for pkey in ordered_keys:
            pdef = project_defs[pkey]
            puuid = project_uuid_by_key[pkey]
            owned_tables = sorted(set(pdef["owned_tables"]))
            anchor_tables = owned_tables if owned_tables else collect_representative_tables(pkey)

            referenced_tables: set[str] = set()
            scope_fks: list[suite_gen.ForeignKeySpec] = []
            for tname in anchor_tables:
                for fk in fks_by_source.get(tname, []):
                    referenced_tables.add(fk.target_table)
                    scope_fks.append(fk)
            shared_master_tables = sorted(referenced_tables - set(anchor_tables))
            all_project_tables = anchor_tables + shared_master_tables

            # Build 4-level (conceptual, logical, physical, deployment) server-laid-out ERD diagram(s)!
            diagram_tables = all_project_tables[:140]
            elem_id_by_table: dict[str, str] = {}
            conceptual_entities: list[dict[str, object]] = []
            logical_entities: list[dict[str, object]] = []
            phys_entities: list[dict[str, object]] = []

            for c_idx, tname in enumerate(diagram_tables[:8]):
                tspec = tables_by_name[tname]
                conceptual_entities.append({
                    "id": uuid7(),
                    "name": tspec.orig_name[:80],
                    "role": "table",
                })
                logical_entities.append({
                    "id": uuid7(),
                    "name": tspec.orig_name[:80],
                    "role": "table",
                    "fields": [
                        {
                            "id": uuid7(),
                            "name": c.orig_fieldname or c.col_name.lower(),
                            "datatype": c.fieldtype.lower() or "string",
                            "nullable": not c.not_null,
                        }
                        for c in tspec.columns[:10]
                    ],
                })

            for tname in diagram_tables:
                tspec = tables_by_name[tname]
                eid = uuid7()
                elem_id_by_table[tname] = eid
                phys_entities.append({
                    "id": eid,
                    "name": tname,
                    "role": "table",
                    "engine": "firebird",
                    "resource_id": f"table:{tname}",
                    "fields": [
                        {
                            "id": uuid7(),
                            "name": c.col_name,
                            "datatype": c.fb_type,
                            "nullable": not c.not_null,
                        }
                        for c in tspec.columns[:14]
                    ],
                })

            deployment_nodes = [{
                "id": uuid7(),
                "name": "Firebird 5.0.4 — frappe_suite.fdb",
                "role": "table",
                "engine": "firebird",
                "host": "127.0.0.1:53050",
                "instance_type": "ODS 13.1 (32KB UTF8)",
            }]

            erd_links: list[dict[str, str]] = []
            for fk in scope_fks:
                if fk.source_table in elem_id_by_table and fk.target_table in elem_id_by_table:
                    if fk.source_table != fk.target_table and len(erd_links) < 220:
                        erd_links.append({
                            "id": uuid7(),
                            "source": elem_id_by_table[fk.source_table],
                            "target": elem_id_by_table[fk.target_table],
                            "title": fk.source_col,
                            "kind": "fk",
                        })

            model_title = f"{pdef['name']} — Schema Model"[:120]
            raw_ddn_text = build_four_level_erd_ddn(
                title=model_title,
                conceptual_entities=conceptual_entities,
                logical_entities=logical_entities,
                physical_tables=phys_entities,
                deployment_nodes=deployment_nodes,
                level_links=erd_links,
                extensions={
                    "frappe_project_key": pkey,
                    "owned_table_count": len(owned_tables),
                    "linked_master_table_count": len(shared_master_tables),
                    "total_bound_tables": len(all_project_tables),
                },
            )
            erd_layout = compute_server_layout(raw_ddn_text)
            ddn_text = apply_layout_to_ddn_text(raw_ddn_text, erd_layout)
            ddn_sha = hashlib.sha256(ddn_text.encode("utf-8")).hexdigest()
            dkey = f"{pkey}-erd"

            existing_design = dconn.execute(
                "SELECT id FROM design WHERE project_id = ? AND key = ?",
                (pkey, dkey),
            ).fetchone()
            if existing_design:
                design_id = existing_design[0]
                dconn.execute("DELETE FROM binding WHERE design_id = ?", (design_id,))
                dconn.execute("DELETE FROM element WHERE design_id = ?", (design_id,))
                dconn.execute("DELETE FROM design_version WHERE design_id = ?", (design_id,))
                dconn.execute(
                    """
                    UPDATE design
                    SET title = ?, head_version = 1, active_version = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (model_title, now_iso, design_id),
                )
            else:
                design_id = uuid7()
                dconn.execute(
                    """
                    INSERT INTO design (
                      id, kind, project_id, key, title,
                      active_version, head_version,
                      created_by, created_at, updated_by, updated_at
                    ) VALUES (?, 'erd', ?, ?, ?, 1, 1, ?, ?, ?, ?)
                    """,
                    (design_id, pkey, dkey, model_title, user_id, now_iso, user_id, now_iso),
                )

            dconn.execute(
                """
                INSERT INTO design_version (
                  design_id, version, base_version, status,
                  ddn_text, ddn_sha256, dialect_version, note,
                  actor_id, saved_at, origin, loss_report
                ) VALUES (?, 1, NULL, 'accepted', ?, ?, 'ddn-next-1', ?, ?, ?, 'local', NULL)
                """,
                (
                    design_id,
                    ddn_text,
                    ddn_sha,
                    f"Seeded Firebird 5.0 schema bindings ({len(all_project_tables)} tables)",
                    user_id,
                    now_iso,
                ),
            )

            # Bind EVERY table used by this project (both diagrammed & overflow tables!) in designs.db
            for tname in all_project_tables:
                eid = elem_id_by_table.get(tname) or uuid7()
                dconn.execute(
                    """
                    INSERT INTO element (id, design_id, role, name, first_version, removed_version)
                    VALUES (?, ?, 'table', ?, 1, NULL)
                    """,
                    (eid, design_id, tname),
                )
                dconn.execute(
                    """
                    INSERT INTO binding (
                      id, design_id, element_id, target_kind, target_ref,
                      target_engine, target_endpoint_id, target_database_target_id,
                      state, state_reason, confirmed_by, confirmed_at
                    ) VALUES (?, ?, ?, 'resource', ?, 'firebird', ?, ?, 'valid', NULL, ?, ?)
                    """,
                    (
                        uuid7(),
                        design_id,
                        eid,
                        f"table:{tname}",
                        endpoint_id,
                        target_id,
                        user_id,
                        now_iso,
                    ),
                )
                total_bindings += 1

            # Build canonical resource_bindings JSON for cde_project_asset
            owned_set = set(owned_tables)
            extra_db_objs = PROJECT_EXTRA_DB_OBJECTS.get(pkey, [
                ("function", "FN_DOCSTATUS_LABEL"),
            ])
            resource_bindings = [
                build_resource_ref(
                    endpoint_id,
                    target_id,
                    tname,
                    role="owned" if tname in owned_set else "referenced_fk",
                    kind="table",
                )
                for tname in all_project_tables
            ] + [
                build_resource_ref(
                    endpoint_id,
                    target_id,
                    obj_name,
                    role="owned",
                    kind=obj_kind,
                )
                for obj_kind, obj_name in extra_db_objs
            ]
            rb_json = json.dumps(resource_bindings)

            # Upsert Asset 1: ERD Data Model (asset_key == design_id so clicking in ProjectExplorer opens ERDDesignerSurface!)
            _upsert_project_asset(
                cconn,
                project_uuid=puuid,
                user_id=user_id,
                asset_key=design_id,
                asset_type="cdeadmin.design.erd",
                schema_name="cdeadmin.design.erd",
                name=f"{pdef['name']} — ERD & Table Bindings ({len(all_project_tables)} tables)"[:250],
                path=f"models/{pkey}.erd.ddn",
                content_obj={
                    "design_id": design_id,
                    "project_id": pkey,
                    "database": db_path,
                    "owned_tables": owned_tables,
                    "referenced_master_tables": shared_master_tables,
                },
                metadata_obj={
                    "owned_table_count": len(owned_tables),
                    "referenced_table_count": len(shared_master_tables),
                    "total_bound_tables": len(all_project_tables),
                },
                rb_json=rb_json,
                now_sql=now_sql,
            )
            total_assets += 1

            # Partitioned Sub-Domain ERD Diagrams only for mega-projects with >140 owned tables (with all 4 levels + element rows)!
            if len(owned_tables) > 140:
                for chunk_idx, start_i in enumerate(range(140, len(owned_tables), 140), start=2):
                    chunk_tables = owned_tables[start_i:start_i + 140]
                    chunk_eids: dict[str, str] = {}
                    chunk_phys: list[dict[str, object]] = []
                    chunk_c: list[dict[str, object]] = []
                    chunk_l: list[dict[str, object]] = []
                    for ct in chunk_tables[:8]:
                        ct_spec = tables_by_name[ct]
                        chunk_c.append({"id": uuid7(), "name": ct_spec.orig_name[:72], "role": "table"})
                        chunk_l.append({
                            "id": uuid7(),
                            "name": ct_spec.orig_name[:72],
                            "role": "table",
                            "fields": [
                                {"id": uuid7(), "name": c.col_name.lower(), "datatype": c.fb_type.lower(), "nullable": not c.not_null}
                                for c in ct_spec.columns[:8]
                            ],
                        })
                    for ct in chunk_tables:
                        ct_spec = tables_by_name[ct]
                        ceid = uuid7()
                        chunk_eids[ct] = ceid
                        chunk_phys.append({
                            "id": ceid,
                            "name": ct,
                            "role": "table",
                            "engine": "firebird",
                            "resource_id": f"table:{ct}",
                            "fields": [
                                {
                                    "id": uuid7(),
                                    "name": c.col_name,
                                    "datatype": c.fb_type,
                                    "nullable": not c.not_null,
                                }
                                for c in ct_spec.columns[:12]
                            ],
                        })
                    chunk_links: list[dict[str, str]] = []
                    for fk in scope_fks:
                        if fk.source_table in chunk_eids and fk.target_table in chunk_eids and fk.source_table != fk.target_table:
                            chunk_links.append({
                                "id": uuid7(),
                                "source": chunk_eids[fk.source_table],
                                "target": chunk_eids[fk.target_table],
                                "title": fk.source_col,
                                "kind": "fk",
                            })
                    part_title = f"{pdef['name']} — Extended Schema Model (Part {chunk_idx})"[:120]
                    part_raw = build_four_level_erd_ddn(
                        title=part_title,
                        conceptual_entities=chunk_c,
                        logical_entities=chunk_l,
                        physical_tables=chunk_phys,
                        deployment_nodes=deployment_nodes,
                        level_links=chunk_links[:160],
                    )
                    part_ddn = apply_layout_to_ddn_text(part_raw, compute_server_layout(part_raw, view_id="erd_physical"))
                    part_did = _upsert_simple_design(
                        dconn,
                        project_key=pkey,
                        design_key=f"{pkey}-erd-extended-{chunk_idx}",
                        kind="erd",
                        title=part_title,
                        ddn_text=part_ddn,
                        user_id=user_id,
                        now_iso=now_iso,
                    )
                    for ct, ceid in chunk_eids.items():
                        dconn.execute(
                            "INSERT INTO element (id, design_id, role, name, first_version, removed_version) VALUES (?, ?, 'table', ?, 1, NULL)",
                            (ceid, part_did, ct),
                        )
                    part_rb = json.dumps([
                        build_resource_ref(endpoint_id, target_id, ct, role="owned", kind="table")
                        for ct in chunk_tables
                    ])
                    _upsert_project_asset(
                        cconn,
                        project_uuid=puuid,
                        user_id=user_id,
                        asset_key=part_did,
                        asset_type="cdeadmin.design.erd",
                        schema_name="cdeadmin.design.erd",
                        name=f"{part_title} ({len(chunk_tables)} tables)"[:240],
                        path=f"models/{pkey}-part-{chunk_idx}.erd.ddn",
                        content_obj={"design_id": part_did, "project_id": pkey, "owned_tables": chunk_tables},
                        metadata_obj={"owned_table_count": len(chunk_tables)},
                        rb_json=part_rb,
                        now_sql=now_sql,
                    )
                    total_assets += 1

            # Upsert Multi-Screen Wireframe Screen Mesh(es) for EVERY SINGLE PROJECT (all 184 projects!)
            mesh_created, mesh_bindings = _seed_project_screen_meshes(
                dconn=dconn,
                cconn=cconn,
                pkey=pkey,
                puuid=puuid,
                pname=str(pdef["name"]),
                anchor_tables=anchor_tables,
                tables_by_name=tables_by_name,
                endpoint_id=endpoint_id,
                target_id=target_id,
                user_id=user_id,
                now_iso=now_iso,
                now_sql=now_sql,
            )
            total_assets += mesh_created
            total_bindings += mesh_bindings

            # Upsert Ready-to-run SQL Notebook for this project's tables
            nb_content = build_sql_notebook_payload(
                str(pdef["name"]),
                str(pdef["description"]),
                anchor_tables,
                shared_master_tables,
                scope_fks,
            )
            _upsert_project_asset(
                cconn,
                project_uuid=puuid,
                user_id=user_id,
                asset_key=f"{pkey}-sql-workbench",
                asset_type="cdeadmin.sql-notebook.v1",
                schema_name="cdeadmin.sql-notebook.v1",
                name=f"{pdef['name']} — SQL Workbench"[:250],
                path=f"notebooks/{pkey}-sql-workbench.json",
                content_obj=nb_content,
                metadata_obj={"total_bound_tables": len(all_project_tables)},
                rb_json=rb_json,
                now_sql=now_sql,
                source_control_eligible=False,
            )
            total_assets += 1

            # Seed additional Reports (Print/Graphs/PDF), Tasks, Calendars, Channels, Members & Transcripts
            if pkey in FULL_SHOWCASE_PROJECTS:
                total_assets += _seed_showcase_virtual_items(
                    dconn=dconn,
                    cconn=cconn,
                    pkey=pkey,
                    puuid=puuid,
                    pname=str(pdef["name"]),
                    primary_table=(anchor_tables[0] if anchor_tables else "COMPANY"),
                    endpoint_id=endpoint_id,
                    user_id=user_id,
                    now_iso=now_iso,
                    now_sql=now_sql,
                )

        dconn.commit()
        cconn.commit()
    finally:
        dconn.close()
        cconn.close()

    return {
        "total_projects_seeded": len(ordered_keys),
        "structural_parent_projects": len(STRUCTURAL_PARENTS),
        "leaf_application_and_subsection_projects": len(ordered_keys) - len(STRUCTURAL_PARENTS),
        "total_tables_partitioned": len(tables_by_name),
        "total_design_store_table_bindings": total_bindings,
        "total_project_assets_seeded": total_assets,
        "acyclic_dag_verified": True,
        "firebird_database_target_id": target_id,
    }


def _upsert_simple_design(
    dconn: sqlite3.Connection,
    *,
    project_key: str,
    design_key: str,
    kind: str,
    title: str,
    ddn_text: str,
    user_id: int,
    now_iso: str,
) -> str:
    if isinstance(ddn_text, tuple):
        ddn_text = ddn_text[0]
    sha = hashlib.sha256(ddn_text.encode("utf-8")).hexdigest()
    existing = dconn.execute(
        "SELECT id FROM design WHERE project_id = ? AND key = ?",
        (project_key, design_key),
    ).fetchone()
    if existing:
        did = existing[0]
        dconn.execute("DELETE FROM binding WHERE design_id = ?", (did,))
        dconn.execute("DELETE FROM element WHERE design_id = ?", (did,))
        dconn.execute("DELETE FROM design_version WHERE design_id = ?", (did,))
        dconn.execute(
            "UPDATE design SET title = ?, active_version = 1, head_version = 1, updated_at = ? WHERE id = ?",
            (title[:120], now_iso, did),
        )
    else:
        did = uuid7()
        dconn.execute(
            """
            INSERT INTO design (
              id, kind, project_id, key, title,
              active_version, head_version,
              created_by, created_at, updated_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?)
            """,
            (did, kind, project_key, design_key, title[:120], user_id, now_iso, user_id, now_iso),
        )
    dconn.execute(
        """
        INSERT INTO design_version (
          design_id, version, base_version, status,
          ddn_text, ddn_sha256, dialect_version, note,
          actor_id, saved_at, origin, loss_report
        ) VALUES (?, 1, NULL, 'accepted', ?, ?, 'ddn-next-1', 'Seeded showcase design', ?, ?, 'local', NULL)
        """,
        (did, ddn_text, sha, user_id, now_iso),
    )
    return did


def _build_single_screen_mesh_bundle(
    *,
    mesh_title: str,
    primary_spec: suite_gen.TableSpec,
    secondary_spec: suite_gen.TableSpec | None,
    child_spec: suite_gen.TableSpec | None,
    endpoint_id: str,
    target_id: str,
) -> tuple[dict[str, object], list[tuple[str, str, str]], list[tuple[str, str]]]:
    """Build a multi-screen wireframe.ui@1 model + (elem_id, role, name) + (elem_id, target_ref) bindings."""
    list_scr_id = uuid7()
    form_scr_id = uuid7()
    screens = [
        {
            "id": list_scr_id,
            "name": f"{primary_spec.orig_name[:48]} — List & Filter View",
            "width": 980,
            "height": 640,
            "form_reference": "",
            "screenshot_path": "",
            "screenshot_sha256": "",
            "notes": f"List console bound to Firebird table {primary_spec.table_name}",
        },
        {
            "id": form_scr_id,
            "name": f"{primary_spec.orig_name[:48]} — Entry & Edit Form",
            "width": 980,
            "height": 700,
            "form_reference": "",
            "screenshot_path": "",
            "screenshot_sha256": "",
            "notes": f"Detail form bound to columns of {primary_spec.table_name}",
        },
    ]

    sec_scr_id = None
    if secondary_spec is not None and secondary_spec.table_name != primary_spec.table_name:
        sec_scr_id = uuid7()
        screens.append({
            "id": sec_scr_id,
            "name": f"{secondary_spec.orig_name[:48]} — Related Inspector",
            "width": 920,
            "height": 600,
            "form_reference": "",
            "screenshot_path": "",
            "screenshot_sha256": "",
            "notes": f"Related entity screen bound to {secondary_spec.table_name}",
        })

    controls: list[dict[str, object]] = []
    bindings: list[dict[str, object]] = []
    navigations: list[dict[str, object]] = []
    store_elements: list[tuple[str, str, str]] = [
        (s["id"], "ui.frame", str(s["name"])) for s in screens
    ]
    store_bindings: list[tuple[str, str]] = []

    # --- Screen 1: List & Filter Console ---
    lbl_id = uuid7()
    search_id = uuid7()
    status_dd_id = uuid7()
    new_btn_id = uuid7()
    grid_id = uuid7()

    grid_cols = []
    for cidx, col in enumerate(primary_spec.columns[:5], start=1):
        grid_cols.append({
            "id": f"col_{cidx}",
            "name": col.col_name,
            "width": 168,
            "datatype": col.fb_type.lower(),
        })

    controls.extend([
        {
            "id": lbl_id,
            "screen_id": list_scr_id,
            "role": "ui.label",
            "name": f"{primary_spec.orig_name} — Workspace Console",
            "bounds": {"x": 24, "y": 18, "width": 520, "height": 34},
        },
        {
            "id": search_id,
            "screen_id": list_scr_id,
            "role": "ui.input",
            "name": "Filter by ID / Title",
            "placeholder": f"Search {primary_spec.table_name}…",
            "bounds": {"x": 24, "y": 64, "width": 320, "height": 36},
        },
        {
            "id": status_dd_id,
            "screen_id": list_scr_id,
            "role": "ui.dropdown",
            "name": "Document Status",
            "options": ["All", "Draft", "Submitted", "Active", "Cancelled"],
            "bounds": {"x": 360, "y": 64, "width": 220, "height": 36},
        },
        {
            "id": new_btn_id,
            "screen_id": list_scr_id,
            "role": "ui.button",
            "name": f"+ New {primary_spec.orig_name[:28]}",
            "bounds": {"x": 740, "y": 64, "width": 210, "height": 36},
        },
        {
            "id": grid_id,
            "screen_id": list_scr_id,
            "role": "ui.grid",
            "name": f"{primary_spec.table_name} Grid",
            "columns": grid_cols,
            "bounds": {"x": 24, "y": 116, "width": 926, "height": 480},
        },
    ])
    bindings.append({
        "id": uuid7(),
        "source_id": grid_id,
        "target_kind": "table",
        "target_ref": f"table:{primary_spec.table_name}",
        "access_mode": "read",
        "target_engine": "firebird",
        "target_endpoint_id": endpoint_id,
        "target_database_target_id": target_id,
    })
    store_elements.append((grid_id, "ui.grid", f"{primary_spec.table_name} Grid"))
    store_bindings.append((grid_id, f"table:{primary_spec.table_name}"))

    navigations.extend([
        {
            "id": uuid7(),
            "from_id": new_btn_id,
            "to_screen_id": form_scr_id,
            "trigger": "click",
            "action": "navigate",
        },
        {
            "id": uuid7(),
            "from_id": grid_id,
            "to_screen_id": form_scr_id,
            "trigger": "click",
            "action": "navigate",
        },
    ])

    # --- Screen 2: Detail Entry & Edit Form ---
    form_hdr_id = uuid7()
    back_btn_id = uuid7()
    save_btn_id = uuid7()
    tabs_id = uuid7()
    controls.extend([
        {
            "id": form_hdr_id,
            "screen_id": form_scr_id,
            "role": "ui.label",
            "name": f"{primary_spec.orig_name} — Record Detail",
            "bounds": {"x": 24, "y": 18, "width": 480, "height": 34},
        },
        {
            "id": back_btn_id,
            "screen_id": form_scr_id,
            "role": "ui.button",
            "name": "← Back to List",
            "bounds": {"x": 620, "y": 18, "width": 150, "height": 34},
        },
        {
            "id": save_btn_id,
            "screen_id": form_scr_id,
            "role": "ui.button",
            "name": "Save & Validate",
            "bounds": {"x": 784, "y": 18, "width": 166, "height": 34},
        },
        {
            "id": tabs_id,
            "screen_id": form_scr_id,
            "role": "ui.tabs",
            "name": "Form Sections",
            "options": ["Details", "Links & Accounting", "Audit Metadata"],
            "bounds": {"x": 24, "y": 64, "width": 926, "height": 38},
        },
    ])
    navigations.append({
        "id": uuid7(),
        "from_id": back_btn_id,
        "to_screen_id": list_scr_id,
        "trigger": "click",
        "action": "back",
    })

    # Place up to 8 real columns from primary_spec in a clean 2-column form grid
    editable_cols = [
        c for c in primary_spec.columns
        if c.col_name not in ("CREATION_TS", "MODIFIED_TS", "MODIFIED_BY", "IDX_NO", "LFT_NODE", "RGT_NODE", "OLD_PARENT")
    ][:8]
    for f_idx, col in enumerate(editable_cols):
        cid = uuid7()
        col_slot = f_idx % 2
        row_slot = f_idx // 2
        cx = 24 if col_slot == 0 else 500
        cy = 120 + row_slot * 64
        if col.fb_type == "D_BOOL":
            role = "ui.checkbox"
            opts: list[str] = []
        elif col.fb_type == "D_STATUS" or col.link_target_doctype:
            role = "ui.dropdown"
            opts = [
                line.strip()[:40]
                for line in (col.options or "").splitlines()
                if line.strip() and not line.strip().startswith("{")
            ][:6] or ["Default", "Selected"]
        else:
            role = "ui.input"
            opts = []
        ctrl_label = (col.label or col.col_name)[:60]
        controls.append({
            "id": cid,
            "screen_id": form_scr_id,
            "role": role,
            "name": ctrl_label,
            "field_id": col.col_name.lower(),
            "tab": "Details" if f_idx < 6 else "Links & Accounting",
            "options": opts,
            "bounds": {"x": cx, "y": cy, "width": 450, "height": 46},
        })
        bindings.append({
            "id": uuid7(),
            "source_id": cid,
            "target_kind": "column",
            "target_ref": f"column:{primary_spec.table_name}.{col.col_name}",
            "access_mode": "read_write",
            "target_engine": "firebird",
            "target_endpoint_id": endpoint_id,
            "target_database_target_id": target_id,
        })
        store_elements.append((cid, role, ctrl_label))
        store_bindings.append((cid, f"table:{primary_spec.table_name}"))

    # Child line-items grid on Screen 2 if available
    if child_spec is not None:
        cgrid_id = uuid7()
        cgrid_cols = [
            {
                "id": f"ccol_{i}",
                "name": cc.col_name,
                "width": 160,
                "datatype": cc.fb_type.lower(),
            }
            for i, cc in enumerate(child_spec.columns[:5], start=1)
        ]
        controls.append({
            "id": cgrid_id,
            "screen_id": form_scr_id,
            "role": "ui.grid",
            "name": f"{child_spec.orig_name[:45]} Line Items",
            "columns": cgrid_cols,
            "bounds": {"x": 24, "y": 400, "width": 926, "height": 260},
        })
        bindings.append({
            "id": uuid7(),
            "source_id": cgrid_id,
            "target_kind": "table",
            "target_ref": f"table:{child_spec.table_name}",
            "access_mode": "read_write",
            "target_engine": "firebird",
            "target_endpoint_id": endpoint_id,
            "target_database_target_id": target_id,
        })
        store_elements.append((cgrid_id, "ui.grid", f"{child_spec.table_name} Items"))
        store_bindings.append((cgrid_id, f"table:{child_spec.table_name}"))

    # --- Screen 3: Related Entity Inspector (if secondary_spec present) ---
    if sec_scr_id and secondary_spec is not None:
        rel_btn_id = uuid7()
        controls.append({
            "id": rel_btn_id,
            "screen_id": form_scr_id,
            "role": "ui.button",
            "name": f"Open {secondary_spec.orig_name[:26]} →",
            "bounds": {"x": 380, "y": 18, "width": 225, "height": 34},
        })
        sec_back_id = uuid7()
        sec_grid_id = uuid7()
        controls.extend([
            {
                "id": uuid7(),
                "screen_id": sec_scr_id,
                "role": "ui.label",
                "name": f"{secondary_spec.orig_name} — Linked Records",
                "bounds": {"x": 24, "y": 20, "width": 520, "height": 34},
            },
            {
                "id": sec_back_id,
                "screen_id": sec_scr_id,
                "role": "ui.button",
                "name": "← Return to Form",
                "bounds": {"x": 720, "y": 20, "width": 170, "height": 34},
            },
            {
                "id": sec_grid_id,
                "screen_id": sec_scr_id,
                "role": "ui.grid",
                "name": f"{secondary_spec.table_name} Records",
                "columns": [
                    {
                        "id": f"scol_{i}",
                        "name": sc.col_name,
                        "width": 165,
                        "datatype": sc.fb_type.lower(),
                    }
                    for i, sc in enumerate(secondary_spec.columns[:5], start=1)
                ],
                "bounds": {"x": 24, "y": 74, "width": 866, "height": 480},
            },
        ])
        bindings.append({
            "id": uuid7(),
            "source_id": sec_grid_id,
            "target_kind": "table",
            "target_ref": f"table:{secondary_spec.table_name}",
            "access_mode": "read",
            "target_engine": "firebird",
            "target_endpoint_id": endpoint_id,
            "target_database_target_id": target_id,
        })
        store_elements.append((sec_grid_id, "ui.grid", f"{secondary_spec.table_name} Records"))
        store_bindings.append((sec_grid_id, f"table:{secondary_spec.table_name}"))
        navigations.extend([
            {
                "id": uuid7(),
                "from_id": rel_btn_id,
                "to_screen_id": sec_scr_id,
                "trigger": "click",
                "action": "navigate",
            },
            {
                "id": uuid7(),
                "from_id": sec_back_id,
                "to_screen_id": form_scr_id,
                "trigger": "click",
                "action": "back",
            },
        ])

    sm_model = default_screen_mesh_model(
        mesh_title[:110],
        screens=screens,
        controls=controls,
        bindings=bindings,
        navigations=navigations,
        notes=f"Multi-screen wireframe mesh for {mesh_title}",
    )
    return sm_model, store_elements, store_bindings


def _seed_project_screen_meshes(
    *,
    dconn: sqlite3.Connection,
    cconn: sqlite3.Connection,
    pkey: str,
    puuid: str,
    pname: str,
    anchor_tables: list[str],
    tables_by_name: dict[str, suite_gen.TableSpec],
    endpoint_id: str,
    target_id: str,
    user_id: int,
    now_iso: str,
    now_sql: str,
) -> tuple[int, int]:
    """Generate multi-screen wireframe.ui@1 Screen Meshes for EVERY project."""
    non_child = [t for t in anchor_tables if tables_by_name[t].kind != "child"]
    children = [t for t in anchor_tables if tables_by_name[t].kind == "child"]
    ordered_candidates = non_child + children
    if not ordered_candidates:
        ordered_candidates = ["COMPANY"]

    primary_t = ordered_candidates[0]
    secondary_t = ordered_candidates[1] if len(ordered_candidates) > 1 else None
    child_t = children[0] if children else None

    mesh_specs = [
        (
            f"{pkey}-screen-mesh",
            f"{pname} — Workspace & Entry Screen Mesh",
            f"screens/{pkey}-desk.screen.ddn",
            tables_by_name[primary_t],
            tables_by_name[secondary_t] if secondary_t else None,
            tables_by_name[child_t] if child_t else None,
        )
    ]
    # Add a second dedicated Screen Mesh for projects with >=4 tables!
    if len(non_child) >= 3:
        alt_primary = non_child[2]
        alt_secondary = non_child[3] if len(non_child) > 3 else non_child[0]
        alt_child = children[1] if len(children) > 1 else None
        mesh_specs.append((
            f"{pkey}-ops-screen-mesh",
            f"{pname} — {tables_by_name[alt_primary].orig_name[:44]} Screen Mesh",
            f"screens/{pkey}-operations.screen.ddn",
            tables_by_name[alt_primary],
            tables_by_name[alt_secondary],
            tables_by_name[alt_child] if alt_child else None,
        ))

    assets_created = 0
    bindings_created = 0

    for dkey, mtitle, mpath, pspec, sspec, cspec in mesh_specs:
        sm_model, store_elems, store_binds = _build_single_screen_mesh_bundle(
            mesh_title=mtitle,
            primary_spec=pspec,
            secondary_spec=sspec,
            child_spec=cspec,
            endpoint_id=endpoint_id,
            target_id=target_id,
        )
        sm_ddn = screen_mesh_to_ddn(sm_model)
        sm_did = _upsert_simple_design(
            dconn,
            project_key=pkey,
            design_key=dkey,
            kind="screen",
            title=mtitle,
            ddn_text=sm_ddn,
            user_id=user_id,
            now_iso=now_iso,
        )
        seen_eids: set[str] = set()
        for eid, erole, ename in store_elems:
            if eid in seen_eids:
                continue
            seen_eids.add(eid)
            dconn.execute(
                "INSERT INTO element (id, design_id, role, name, first_version, removed_version) VALUES (?, ?, ?, ?, 1, NULL)",
                (eid, sm_did, erole, ename[:120]),
            )
        for eid, tref in store_binds:
            dconn.execute(
                """
                INSERT INTO binding (
                  id, design_id, element_id, target_kind, target_ref,
                  target_engine, target_endpoint_id, target_database_target_id,
                  state, state_reason, confirmed_by, confirmed_at
                ) VALUES (?, ?, ?, 'resource', ?, 'firebird', ?, ?, 'valid', NULL, ?, ?)
                """,
                (uuid7(), sm_did, eid, tref, endpoint_id, target_id, user_id, now_iso),
            )
            bindings_created += 1

        bound_tnames = sorted({
            pspec.table_name,
            *([sspec.table_name] if sspec else []),
            *([cspec.table_name] if cspec else []),
        })
        mesh_rb = json.dumps([
            build_resource_ref(endpoint_id, target_id, tn, role="owned", kind="table")
            for tn in bound_tnames
        ])
        _upsert_project_asset(
            cconn,
            project_uuid=puuid,
            user_id=user_id,
            asset_key=sm_did,
            asset_type="cdeadmin.design.screen",
            schema_name="cdeadmin.design.screen",
            name=mtitle[:240],
            path=mpath,
            content_obj={
                "design_id": sm_did,
                "project_id": pkey,
                "primary_table": pspec.table_name,
                "screen_count": len(sm_model["screens"]),
            },
            metadata_obj={
                "primary_table": pspec.table_name,
                "screen_count": len(sm_model["screens"]),
            },
            rb_json=mesh_rb,
            now_sql=now_sql,
        )
        assets_created += 1

    return assets_created, bindings_created


def _seed_showcase_virtual_items(
    *,
    dconn: sqlite3.Connection,
    cconn: sqlite3.Connection,
    pkey: str,
    puuid: str,
    pname: str,
    primary_table: str,
    endpoint_id: str,
    user_id: int,
    now_iso: str,
    now_sql: str,
) -> int:
    """Populate Reports (Print/Graphs/PDF), Tasks, Calendars, Channels, Members & Transcripts."""
    created = 0
    empty_rb = "[]"

    # 1. BI Graph Question (Reports > Graphs)
    q_model = default_question_model(
        f"{pname} — Activity Breakdown"[:110],
        endpoint_id=endpoint_id,
        raw_sql=f"SELECT FIRST 25 * FROM {primary_table}",
        visualization={"type": "bar"},
        preview_rows=[["Sample-01", 12], ["Sample-02", 8]],
    )
    q_ddn = question_to_ddn(q_model)
    q_design_id = _upsert_simple_design(
        dconn,
        project_key=pkey,
        design_key=f"{pkey}-bi-graph",
        kind="question",
        title=f"{pname} — Volume & Status Graph",
        ddn_text=q_ddn,
        user_id=user_id,
        now_iso=now_iso,
    )
    _upsert_project_asset(
        cconn,
        project_uuid=puuid,
        user_id=user_id,
        asset_key=q_design_id,
        asset_type="cdeadmin.design.question",
        schema_name="cdeadmin.design.question",
        name=f"{pname} — Volume & Status Chart"[:240],
        path=f"reports/graphs/{pkey}-chart.bi.ddn",
        content_obj={"design_id": q_design_id, "primary_table": primary_table},
        metadata_obj={"report_category": "graphs"},
        rb_json=empty_rb,
        now_sql=now_sql,
    )
    created += 1

    # 3. Print Report & PDF Report (Reports > Print, Reports > PDF)
    _upsert_project_asset(
        cconn,
        project_uuid=puuid,
        user_id=user_id,
        asset_key=f"{pkey}-print-voucher",
        asset_type="cdeadmin.project.report.print.v1",
        schema_name="cdeadmin.project.report.print.v1",
        name=f"{pname} — Standard Voucher Print Format"[:240],
        path=f"reports/print/{pkey}-voucher.json",
        content_obj={
            "paper": "A4 Portrait",
            "source_table": primary_table,
            "sql": f"SELECT FIRST 50 * FROM {primary_table};",
        },
        metadata_obj={"report_category": "print"},
        rb_json=empty_rb,
        now_sql=now_sql,
    )
    _upsert_project_asset(
        cconn,
        project_uuid=puuid,
        user_id=user_id,
        asset_key=f"{pkey}-pdf-pack",
        asset_type="cdeadmin.project.report.pdf.v1",
        schema_name="cdeadmin.project.report.pdf.v1",
        name=f"{pname} — Monthly Executive Audit PDF"[:240],
        path=f"reports/pdf/{pkey}-executive-audit.json",
        content_obj={
            "paper": "A4 Landscape",
            "source_table": primary_table,
            "sql": f"SELECT COUNT(*) AS TOTAL_RECORDS FROM {primary_table};",
        },
        metadata_obj={"report_category": "pdf"},
        rb_json=empty_rb,
        now_sql=now_sql,
    )
    created += 2

    # 4. Tasks: Pending, In Process, Completed
    for t_slug, t_status, t_title, assignee, prio, due in (
        ("verify-indexes", "pending", f"Review Firebird 5.0 selectivity indexes on {primary_table}", "Grace Hopper", "Medium", "2026-12-05"),
        ("reconcile-fk", "in_process", f"Validate cross-ledger foreign key rules for {pname}", "Ada Lovelace", "High", "2026-11-22"),
        ("baseline-ddn", "completed", f"Publish baseline DDN physical model for {pname}", "Katherine Johnson", "High", "2026-11-10"),
    ):
        _upsert_project_asset(
            cconn,
            project_uuid=puuid,
            user_id=user_id,
            asset_key=f"{pkey}-task-{t_slug}",
            asset_type="cdeadmin.project.task.v1",
            schema_name="cdeadmin.project.task.v1",
            name=t_title[:240],
            path=f"tasks/{t_slug}.json",
            content_obj={
                "status": t_status,
                "assignee": assignee,
                "priority": prio,
                "due_date": due,
                "description": f"{t_title} against /var/lib/firebird/data/frappe_suite.fdb.",
            },
            metadata_obj={"task_status": t_status},
            rb_json=empty_rb,
            now_sql=now_sql,
        )
        created += 1

    # 5. Calendars: Shared & Personal Calendar + Gantt Chart
    _upsert_project_asset(
        cconn,
        project_uuid=puuid,
        user_id=user_id,
        asset_key=f"{pkey}-shared-calendar",
        asset_type="cdeadmin.project.calendar.v1",
        schema_name="cdeadmin.project.calendar.v1",
        name=f"{pname} — Release & Close Calendar"[:240],
        path=f"calendars/{pkey}-shared.json",
        content_obj={
            "summary": f"Shared milestone & personal review calendar for {pname}",
            "entries": [
                {"id": "ev-1", "title": "Schema & FK Sign-off", "start": "2026-11-18", "end": "2026-11-18", "owner": "Ada Lovelace"},
                {"id": "ev-2", "title": "Period Close Dry-Run", "start": "2026-11-28", "end": "2026-11-29", "owner": "Katherine Johnson"},
            ],
        },
        metadata_obj={"calendar_kind": "shared"},
        rb_json=empty_rb,
        now_sql=now_sql,
    )
    _upsert_project_asset(
        cconn,
        project_uuid=puuid,
        user_id=user_id,
        asset_key=f"{pkey}-gantt-roadmap",
        asset_type="cdeadmin.project.calendar.v1",
        schema_name="cdeadmin.project.calendar.v1",
        name=f"{pname} — Delivery Gantt Roadmap"[:240],
        path=f"calendars/{pkey}-gantt.json",
        content_obj={
            "summary": f"Gantt phase schedule for {pname}",
            "entries": [
                {"id": "g-1", "title": "Phase 1 — Firebird Metadata Adaptation", "start": "2026-11-01", "end": "2026-11-10", "owner": "Ada Lovelace", "progress": 100},
                {"id": "g-2", "title": "Phase 2 — DDN Designer & BI Verification", "start": "2026-11-11", "end": "2026-11-22", "owner": "Grace Hopper", "progress": 70},
                {"id": "g-3", "title": "Phase 3 — Production Cutover Readiness", "start": "2026-11-23", "end": "2026-12-05", "owner": "Margaret Hamilton", "progress": 25},
            ],
        },
        metadata_obj={"calendar_kind": "gantt"},
        rb_json=empty_rb,
        now_sql=now_sql,
    )
    created += 2

    # 6. Chat Channel
    _upsert_project_asset(
        cconn,
        project_uuid=puuid,
        user_id=user_id,
        asset_key=f"{pkey}-chan-general",
        asset_type="cdeadmin.project.channel.v1",
        schema_name="cdeadmin.project.channel.v1",
        name=f"#{pkey[:32]} — Engineering & Ops"[:240],
        path=f"channels/{pkey}-general.json",
        content_obj={
            "topic": f"Coordination channel for {pname} ({primary_table})",
            "messages": [
                {"id": "m1", "author": "Ada Lovelace", "timestamp": "2026-11-15 09:15", "text": f"Bound {primary_table} and verified Firebird 5.0 foreign keys."},
                {"id": "m2", "author": "Grace Hopper", "timestamp": "2026-11-15 10:05", "text": "ERD, Screen Mesh, and BI chart assets are live in the Project Navigator."},
            ],
        },
        metadata_obj={"channel_kind": "project"},
        rb_json=empty_rb,
        now_sql=now_sql,
    )
    created += 1

    # 7. Notes, Architecture Docs, Design Review Transcript + Team Roster (Groups & Individuals)
    _upsert_project_asset(
        cconn,
        project_uuid=puuid,
        user_id=user_id,
        asset_key=f"{pkey}-design-transcript",
        asset_type="cdeadmin.project.document.v1",
        schema_name="cdeadmin.project.document.v1",
        name=f"{pname} — Architecture Notes & Review Transcript"[:240],
        path=f"documents/{pkey}-architecture-transcript.json",
        content_obj={
            "body": (
                f"# {pname} — Architecture & Review Transcript\n\n"
                f"- **Primary Anchor Table**: `{primary_table}`\n"
                f"- **Database**: `/var/lib/firebird/data/frappe_suite.fdb` (ODS 13.1, 32 KB pages, UTF8)\n\n"
                f"## Design Review Transcript (2026-11-15)\n"
                f"- **Ada Lovelace**: Confirmed unquoted SNAKE_CASE Firebird identifiers and enforced FK constraints.\n"
                f"- **Katherine Johnson**: Verified ledger balance views and PSQL package routines."
            )
        },
        metadata_obj={
            "document_kind": "team_roster",
            "lead": "Ada Lovelace (Owner)",
            "groups": [
                {"name": "Database Architects", "access": "manager"},
                {"name": "Domain Analysts", "access": "editor"},
                {"name": "Audit Reviewers", "access": "viewer"},
            ],
            "individuals": [
                {"name": "Grace Hopper", "role": "Systems Architect", "access": "manager"},
                {"name": "Katherine Johnson", "role": "Ledger Specialist", "access": "editor"},
                {"name": "Alan Turing", "role": "Platform Reliability", "access": "editor"},
            ],
        },
        rb_json=empty_rb,
        now_sql=now_sql,
    )
    created += 1
    return created


def _upsert_project_asset(
    cconn: sqlite3.Connection,
    *,
    project_uuid: str,
    user_id: int,
    asset_key: str,
    asset_type: str,
    schema_name: str,
    name: str,
    path: str,
    content_obj: dict[str, object],
    metadata_obj: dict[str, object],
    rb_json: str,
    now_sql: str,
    source_control_eligible: bool = True,
) -> None:
    content_json = json.dumps(content_obj)
    meta_json = json.dumps(metadata_obj)
    # Remove any prior asset at the same path with a different asset_key (idempotent re-seed)
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
            SET asset_type = ?, name = ?, path = ?, schema_name = ?,
                version = 1, content = ?, asset_metadata = ?,
                resource_bindings = ?, validation_state = 'valid', updated_at = ?
            WHERE id = ?
            """,
            (asset_type, name, path, schema_name, content_json, meta_json, rb_json, now_sql, aid),
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, '[]', ?, NULL, 'internal', ?, 1, 1, 'valid', '[]', ?, ?)
            """,
            (
                aid,
                project_uuid,
                user_id,
                asset_key,
                asset_type,
                name,
                path,
                schema_name,
                content_json,
                meta_json,
                rb_json,
                1 if source_control_eligible else 0,
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
        ) VALUES (?, ?, ?, 1, ?, 1, ?, ?, '[]', ?, 'valid', '[]', ?)
        """,
        (str(uuid.uuid4()), aid, user_id, schema_name, content_json, meta_json, rb_json, now_sql),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-root", type=Path, default=suite_gen.DEFAULT_DONOR_ROOT)
    parser.add_argument("--dialect-json", type=Path, default=suite_gen.DEFAULT_DIALECT_JSON)
    parser.add_argument("--config-db", type=Path, default=DEFAULT_CONFIG_DB)
    parser.add_argument("--designs-db", type=Path, default=DEFAULT_DESIGNS_DB)
    parser.add_argument("--database-path", default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    result = seed_projects_and_bindings(
        donor_root=args.donor_root,
        dialect_json=args.dialect_json,
        config_db=args.config_db,
        designs_db=args.designs_db,
        db_path=args.database_path,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
