#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Expand Firebird frappe_suite.fdb with 55,000+ 24-month time-series rows and
verified international Chart of Accounts records, build companion SQLite Edge
(frappe_books_edge.sqlite) and DuckDB Analytical Lakehouse
(frappe_lakehouse.duckdb) databases from Frappe + data-gov-in CSV sources, and
idempotently register the polyglot 3-engine estate in CDEadmin.

Clean-room PostgreSQL-licensed generator: reads external donor metadata/CSVs
at runtime and writes generated database binaries only to gitignored runtime
data directories.
"""

from __future__ import annotations

import argparse
import builtins
import csv
from datetime import date, timedelta
import glob
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid

import duckdb
import firebird.driver as fbd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
WEB_DIR = REPO_ROOT / "web"
DATA_DIR = SCRIPT_DIR / "data"

DEFAULT_DONOR_ROOT = Path("/home/dcalford/Sandbox/donor_release_acquisition/frappe")
DEFAULT_FB_HOST = "127.0.0.1"
DEFAULT_FB_PORT = 53050
DEFAULT_FB_DB = "/var/lib/firebird/data/frappe_suite.fdb"
DEFAULT_FB_USER = "SYSDBA"
DEFAULT_FB_PASSWORD = os.environ.get(
    "CDEADMIN_FIREBIRD_DEMO_PASSWORD", "CDEadminDemo-2026!"
)
DEFAULT_CONTAINER = "cdeadmin-demo-firebird"
DEFAULT_SQLITE_EDGE = DATA_DIR / "frappe_books_edge.sqlite"
DEFAULT_DUCKDB_LAKEHOUSE = DATA_DIR / "frappe_lakehouse.duckdb"


def sql_lit(val: object) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return f"{val:.2f}"
    s = str(val).replace("'", "''")
    return f"'{s}'"


def extract_coa_leaf_accounts(
    donor_root: Path, max_per_file: int = 12
) -> list[tuple[str, str, str, str]]:
    """Extract representative leaf accounts from verified international CoA JSONs.

    Returns tuples of ``(country_code, account_name, root_type, account_type)``.
    """
    coa_dir = (
        donor_root
        / "erpnext/erpnext/accounts/doctype/account/chart_of_accounts/verified"
    )
    results: list[tuple[str, str, str, str]] = []
    if not coa_dir.is_dir():
        return results

    preferred_prefixes = ("ca_", "us_", "de_", "gb_", "fr_", "in_", "au_", "jp_")
    files = sorted(coa_dir.glob("*.json"))
    selected = [f for f in files if f.name.startswith(preferred_prefixes)]
    if len(selected) < 6:
        selected = files[:8]

    def walk(
        node: dict, country_code: str, inherited_root: str, bucket: list
    ) -> None:
        if len(bucket) >= max_per_file or not isinstance(node, dict):
            return
        root_type = str(node.get("root_type") or inherited_root or "Asset")
        if root_type not in ("Asset", "Liability", "Equity", "Income", "Expense"):
            root_type = inherited_root or "Asset"
        acct_type = str(node.get("account_type") or "")
        is_group = bool(node.get("is_group", False))
        child_dicts = {
            k: v
            for k, v in node.items()
            if isinstance(v, dict)
            and k not in ("account_type", "root_type", "is_group", "tax_rate", "account_number")
        }
        for k, child in child_dicts.items():
            c_is_group = bool(child.get("is_group", False)) or any(
                isinstance(cv, dict) for cv in child.values()
            )
            c_root = str(child.get("root_type") or root_type)
            c_type = str(child.get("account_type") or acct_type or "Expense Account")
            clean_name = re.sub(r"\s+", " ", k).strip()[:72]
            if not c_is_group and clean_name and clean_name.isascii():
                bucket.append((country_code.upper(), clean_name, c_root, c_type[:40]))
                if len(bucket) >= max_per_file:
                    return
            walk(child, country_code, c_root, bucket)

    for fpath in selected[:8]:
        try:
            doc = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        cc = str(doc.get("country_code") or fpath.stem[:2]).upper()
        tree = doc.get("tree") or {}
        bucket: list[tuple[str, str, str, str]] = []
        walk(tree, cc, "Asset", bucket)
        results.extend(bucket)
    return results


def expand_firebird_timeseries(
    donor_root: Path,
    *,
    fb_host: str,
    fb_port: int,
    fb_db: str,
    fb_user: str,
    fb_password: str,
    container: str,
) -> dict[str, int]:
    """Load 55,000+ 24-month seasonal ERP, HR, CRM, Helpdesk & Datum rows into Firebird."""
    dsn = f"{fb_host}/{fb_port}:{fb_db}"
    conn = fbd.connect(dsn, user=fb_user, password=fb_password, charset="UTF8")
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM "GL_ENTRY" WHERE DOC_NAME STARTING WITH \'GLE-TS-\'')
    existing_ts = cur.fetchone()[0]
    conn.close()

    if existing_ts >= 10000:
        conn = fbd.connect(dsn, user=fb_user, password=fb_password, charset="UTF8")
        cur = conn.cursor()
        counts = {}
        for t in (
            "ACCOUNT", "CUSTOMER", "SUPPLIER", "ITEM", "EMPLOYEE",
            "SALES_ORDER", "SALES_ORDER_ITEM", "SALES_INVOICE", "SALES_INVOICE_ITEM",
            "PURCHASE_ORDER", "PURCHASE_INVOICE", "PURCHASE_INVOICE_ITEM",
            "PAYMENT_ENTRY", "GL_ENTRY", "STOCK_LEDGER_ENTRY",
            "ATTENDANCE", "SALARY_SLIP", "HD_TICKET", "CRM_LEAD", "CRM_DEAL",
            "DATUM_SAMPLES", "DATUM_LOGS", "DATUM_TRACES",
        ):
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            counts[t] = cur.fetchone()[0]
        conn.close()
        return counts

    stmts: list[str] = []

    def upsert(table: str, row: dict[str, object], pk_cols: tuple[str, ...] = ("DOC_NAME",)) -> None:
        cols = list(row.keys())
        col_sql = ", ".join(f'"{c}"' for c in cols)
        val_sql = ", ".join(sql_lit(row[c]) for c in cols)
        match_sql = ", ".join(f'"{p}"' for p in pk_cols)
        stmts.append(
            f'UPDATE OR INSERT INTO "{table}" ({col_sql}) VALUES ({val_sql}) MATCHING ({match_sql});'
        )

    # 1. Lookup DocTypes & Statuses so FKs carry real business names
    for dt_name, mod_name in [
        ("Customer", "Selling"),
        ("Supplier", "Buying"),
        ("Employee", "HR"),
        ("Sales Invoice", "Accounts"),
        ("Purchase Invoice", "Accounts"),
        ("Payment Entry", "Accounts"),
        ("Journal Entry", "Accounts"),
        ("Sales Order", "Selling"),
        ("Purchase Order", "Buying"),
        ("Purchase Receipt", "Stock"),
        ("Delivery Note", "Stock"),
        ("Stock Entry", "Stock"),
    ]:
        upsert("DOC_TYPE", {
            "DOC_NAME": dt_name,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": 1,
            "MODULE": mod_name,
        })

    for idx, st in enumerate(["Open", "Replied", "Resolved", "Closed"], start=1):
        upsert("HD_TICKET_STATUS", {
            "DOC_NAME": st,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
        })
    for idx, pr in enumerate(["Low", "Medium", "High", "Urgent"], start=1):
        upsert("HD_TICKET_PRIORITY", {
            "DOC_NAME": pr,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
        })
    for idx, ls in enumerate(["New", "Contacted", "Qualified", "Converted", "Lost"], start=1):
        upsert("CRM_LEAD_STATUS", {
            "DOC_NAME": ls,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
        })
    for idx, ds in enumerate(["Qualification", "Proposal", "Negotiation", "Won", "Lost"], start=1):
        upsert("CRM_DEAL_STATUS", {
            "DOC_NAME": ds,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
        })

    # 2. Company-specific core accounts for NCS & HAC + verified international CoA accounts
    company_core_accounts = [
        ("Operating Bank - NCS", "Operating Bank USD", "Northstar Cloud Services", "Asset", "Balance Sheet", "Bank", "USD", False),
        ("Debtors - NCS", "Accounts Receivable USD", "Northstar Cloud Services", "Asset", "Balance Sheet", "Receivable", "USD", False),
        ("Creditors - NCS", "Accounts Payable USD", "Northstar Cloud Services", "Liability", "Balance Sheet", "Payable", "USD", False),
        ("Sales Tax Payable - NCS", "Sales Tax Payable USD", "Northstar Cloud Services", "Liability", "Balance Sheet", "Tax", "USD", False),
        ("Payroll Expense - NCS", "Cloud Engineering Payroll", "Northstar Cloud Services", "Expense", "Profit and Loss", "Expense Account", "USD", False),
        ("Operating Bank - HAC", "Cooperative Treasury Bank", "Horizon Agritech Cooperative", "Asset", "Balance Sheet", "Bank", "CAD", False),
        ("Debtors - HAC", "Member Receivables", "Horizon Agritech Cooperative", "Asset", "Balance Sheet", "Receivable", "CAD", False),
        ("Stock In Hand - HAC", "Agritech Inventory", "Horizon Agritech Cooperative", "Asset", "Balance Sheet", "Stock", "CAD", False),
        ("Creditors - HAC", "Supplier Payables", "Horizon Agritech Cooperative", "Liability", "Balance Sheet", "Payable", "CAD", False),
        ("GST Payable - HAC", "GST Payable", "Horizon Agritech Cooperative", "Liability", "Balance Sheet", "Tax", "CAD", False),
        ("Agri Supply Revenue - HAC", "Agritech Equipment & Probe Revenue", "Horizon Agritech Cooperative", "Income", "Profit and Loss", "Income Account", "CAD", False),
        ("Cost of Goods Sold - HAC", "Agritech Cost of Goods Sold", "Horizon Agritech Cooperative", "Expense", "Profit and Loss", "Cost of Goods Sold", "CAD", False),
        ("Payroll Expense - HAC", "Agronomy Payroll Expense", "Horizon Agritech Cooperative", "Expense", "Profit and Loss", "Expense Account", "CAD", False),
        ("Withholding Tax Payable - MTM", "Cross-Border Withholding Tax Payable", "Maple Tech Manufacturing", "Liability", "Balance Sheet", "Tax", "CAD", False),
        ("FX Gain Loss - MTM", "Foreign Exchange Realized Gain/Loss", "Maple Tech Manufacturing", "Expense", "Profit and Loss", "Round Off", "CAD", False),
    ]
    for idx, (doc_name, acc_name, comp, root_t, rep_t, acc_t, curr, is_grp) in enumerate(
        company_core_accounts, start=20
    ):
        upsert("ACCOUNT", {
            "DOC_NAME": doc_name,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
            "ACCOUNT_NAME": acc_name,
            "COMPANY": comp,
            "ROOT_TYPE": root_t,
            "REPORT_TYPE": rep_t,
            "ACCOUNT_TYPE": acc_t,
            "ACCOUNT_CURRENCY": curr,
            "IS_GROUP": is_grp,
        })

    coa_leaves = extract_coa_leaf_accounts(donor_root, max_per_file=10)
    comp_cycle = [
        ("Maple Tech Manufacturing", "MTM", "CAD"),
        ("Northstar Cloud Services", "NCS", "USD"),
        ("Horizon Agritech Cooperative", "HAC", "CAD"),
    ]
    for idx, (cc, acct_label, root_t, acct_t) in enumerate(coa_leaves, start=100):
        comp_name, abbr, curr = comp_cycle[idx % len(comp_cycle)]
        doc_id = f"COA-{cc}-{idx:03d} - {abbr}"[:76]
        rep_t = "Balance Sheet" if root_t in ("Asset", "Liability", "Equity") else "Profit and Loss"
        upsert("ACCOUNT", {
            "DOC_NAME": doc_id,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
            "ACCOUNT_NAME": f"[{cc}] {acct_label}"[:120],
            "ACCOUNT_NUMBER": f"{idx + 1000}",
            "COMPANY": comp_name,
            "ROOT_TYPE": root_t,
            "REPORT_TYPE": rep_t,
            "ACCOUNT_TYPE": acct_t[:40] if acct_t else "Expense Account",
            "ACCOUNT_CURRENCY": curr,
            "IS_GROUP": False,
        })

    # 3. Expand Customers (24 total), Suppliers (12 total), Items (18 total), Employees (24 total)
    extra_customers = [
        ("CUST-0009", "Great Lakes Turbine Corp", "Enterprise Industrial", "North America", "CAD"),
        ("CUST-0010", "Cascadia Timber Automation", "Enterprise Industrial", "North America", "CAD"),
        ("CUST-0011", "Bavaria Precision CNC AG", "Enterprise Industrial", "Europe", "EUR"),
        ("CUST-0012", "Thames Water Telemetry PLC", "Enterprise Industrial", "Europe", "GBP"),
        ("CUST-0013", "Apex Fintech Cloud Inc", "SaaS Subscribers", "North America", "USD"),
        ("CUST-0014", "Veridian Health Systems", "SaaS Subscribers", "North America", "USD"),
        ("CUST-0015", "Kansai Smart Factory KK", "Enterprise Industrial", "Asia Pacific", "USD"),
        ("CUST-0016", "Deccan Agro Processing Ltd", "Agricultural Cooperatives", "Asia Pacific", "INR"),
        ("CUST-0017", "Manitoba Pulse & Grain Co-op", "Agricultural Cooperatives", "North America", "CAD"),
        ("CUST-0018", "Okanagan Orchard Sensors", "Agricultural Cooperatives", "North America", "CAD"),
        ("CUST-0019", "Nordic Wind Grid AS", "Enterprise Industrial", "Europe", "EUR"),
        ("CUST-0020", " Sunbelt Cold Storage LLC", "SaaS Subscribers", "North America", "USD"),
        ("CUST-0021", "Maritime Autonomous Vessels", "Enterprise Industrial", "North America", "CAD"),
        ("CUST-0022", "Rhine Chemical Logistics GmbH", "Enterprise Industrial", "Europe", "EUR"),
        ("CUST-0023", "Aurora Satellite Ground Ops", "SaaS Subscribers", "North America", "USD"),
        ("CUST-0024", "Saskatchewan Potash Telemetry", "Agricultural Cooperatives", "North America", "CAD"),
    ]
    all_customers = [
        ("CUST-0001", "Northwind Field Lab", "Enterprise Industrial", "North America", "CAD"),
        ("CUST-0002", "Contoso Water Systems", "Enterprise Industrial", "North America", "CAD"),
        ("CUST-0003", "Adventure Works Mining", "Enterprise Industrial", "North America", "CAD"),
        ("CUST-0004", "Alpine Robotics GmbH", "Enterprise Industrial", "Europe", "EUR"),
        ("CUST-0005", "Bluewater Maritime Logistics", "SaaS Subscribers", "North America", "USD"),
        ("CUST-0006", "Prairie Grain Growers", "Agricultural Cooperatives", "North America", "CAD"),
        ("CUST-0007", "Helios Solar Analytics", "SaaS Subscribers", "North America", "USD"),
        ("CUST-0008", "Pacific Biotech Labs", "SaaS Subscribers", "Asia Pacific", "USD"),
    ] + extra_customers

    for idx, (cid, cname, cgrp, terr, curr) in enumerate(extra_customers, start=9):
        upsert("CUSTOMER", {
            "DOC_NAME": cid,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
            "CUSTOMER_NAME": cname.strip(),
            "CUSTOMER_TYPE": "Company",
            "CUSTOMER_GROUP": cgrp,
            "TERRITORY": terr,
            "DEFAULT_CURRENCY": curr,
        })

    extra_suppliers = [
        ("SUPP-0006", "Ontario Castings & Forgings", "Precision Components", "Canada", "CAD"),
        ("SUPP-0007", "Silicon Valley FPGA Foundry", "Precision Components", "United States", "USD"),
        ("SUPP-0008", "Montreal Fiber & Transit Co", "Cloud & Datacenter Vendors", "Canada", "CAD"),
        ("SUPP-0009", "Frankfurt IX Colocation GmbH", "Cloud & Datacenter Vendors", "Germany", "EUR"),
        ("SUPP-0010", "Pune Precision Seals Pvt Ltd", "Precision Components", "India", "INR"),
        ("SUPP-0011", "Alberta Bio-Fertilizer Supply", "Raw Materials & Seeds", "Canada", "CAD"),
        ("SUPP-0012", "Midwest Sensor Enclosures Inc", "Raw Materials & Seeds", "United States", "USD"),
    ]
    all_suppliers = [
        ("SUPP-0001", "St. Lawrence Alloys Ltd.", "Precision Components", "Canada", "CAD"),
        ("SUPP-0002", "Boreal Semiconductor Corp.", "Precision Components", "United States", "USD"),
        ("SUPP-0003", "Northern Rack & Baremetal Inc.", "Cloud & Datacenter Vendors", "Canada", "CAD"),
        ("SUPP-0004", "Rheinland Hydraulics AG", "Precision Components", "Germany", "EUR"),
        ("SUPP-0005", "Heartland Organic Inputs", "Raw Materials & Seeds", "Canada", "CAD"),
    ] + extra_suppliers

    for idx, (sid, sname, sgrp, country, curr) in enumerate(extra_suppliers, start=6):
        upsert("SUPPLIER", {
            "DOC_NAME": sid,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
            "SUPPLIER_NAME": sname,
            "SUPPLIER_GROUP": sgrp,
            "COUNTRY": country,
            "DEFAULT_CURRENCY": curr,
        })

    extra_items = [
        ("ITM-FLOW-900", "Ultrasonic Flow Meter DN100", "Industrial Assemblies", "Nos", True, 2190.00, 1340.00),
        ("ITM-HEAT-EX4", "Brazed Plate Heat Exchanger", "Industrial Assemblies", "Nos", True, 3480.00, 2210.00),
        ("ITM-SEAL-KIT", "High-Pressure Mechanical Seal Kit", "Industrial Assemblies", "Box", True, 410.00, 225.00),
        ("ITM-MODBUS-IO", "Industrial Modbus TCP I/O Rack", "Electronic Subsystems", "Nos", True, 760.00, 430.00),
        ("ITM-UPS-3KVA", "Rackmount Industrial UPS 3kVA", "Electronic Subsystems", "Nos", True, 1490.00, 960.00),
        ("ITM-VIB-PROBE", "Tri-Axial Piezo Vibration Sensor", "Electronic Subsystems", "Nos", True, 540.00, 295.00),
        ("ITM-CLOUD-PRO", "Managed Frappe Cloud Pro Site", "Cloud Subscriptions", "License", False, 290.00, 0.00),
        ("ITM-CLOUD-DR", "Cross-Region Standby Replica Add-on", "Cloud Subscriptions", "License", False, 450.00, 0.00),
        ("ITM-CLOUD-OBS", "Datum OpenTelemetry Retention Pack", "Cloud Subscriptions", "License", False, 195.00, 0.00),
        ("ITM-WEATHER-ST", "Solar Micro-Climate Weather Station", "Agricultural Inputs", "Nos", True, 1280.00, 780.00),
        ("ITM-DRIP-CTRL", "Automated Fertigation Valve Controller", "Agricultural Inputs", "Nos", True, 690.00, 415.00),
        ("ITM-GRAIN-MON", "Silo Temperature & CO2 Spear", "Agricultural Inputs", "Nos", True, 480.00, 275.00),
    ]
    all_items = [
        ("ITM-PUMP-500", "Centrifugal Process Pump 500L", "Industrial Assemblies", "Nos", True, 4250.00, 2850.00),
        ("ITM-VALVE-210", "Actuated Control Valve DN80", "Industrial Assemblies", "Nos", True, 1380.00, 890.00),
        ("ITM-PLC-EDGE", "Edge Telemetry Gateway v4", "Electronic Subsystems", "Nos", True, 980.00, 540.00),
        ("ITM-MOTOR-15KW", "Brushless Induction Motor 15kW", "Electronic Subsystems", "Nos", True, 1650.00, 1050.00),
        ("ITM-CLOUD-ENT", "Managed Frappe Cloud Dedicated Bench", "Cloud Subscriptions", "License", False, 850.00, 0.00),
        ("ITM-SOIL-SENS", "LoRaWAN Soil Moisture Probe", "Agricultural Inputs", "Nos", True, 320.00, 175.00),
    ] + extra_items

    for idx, (icode, iname, igrp, uom, is_stock, srate, vrate) in enumerate(extra_items, start=7):
        upsert("ITEM", {
            "DOC_NAME": icode,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
            "ITEM_CODE": icode,
            "ITEM_NAME": iname,
            "ITEM_GROUP": igrp,
            "STOCK_UOM": uom,
            "IS_STOCK_ITEM": is_stock,
            "STANDARD_RATE": srate,
            "VALUATION_RATE": vrate,
        })

    extra_employees = [
        ("HR-EMP-0007", "Edsger", "Dijkstra", "Maple Tech Manufacturing", "Engineering - MTM", "Principal Systems Engineer", "CAD", 13900.00),
        ("HR-EMP-0008", "Leslie", "Lamport", "Northstar Cloud Services", "Cloud Platform - NCS", "Site Reliability Engineer", "USD", 14600.00),
        ("HR-EMP-0009", "Radia", "Perlman", "Northstar Cloud Services", "Cloud Platform - NCS", "Principal Systems Engineer", "USD", 15100.00),
        ("HR-EMP-0010", "Donald", "Knuth", "Maple Tech Manufacturing", "Engineering - MTM", "Principal Systems Engineer", "CAD", 14800.00),
        ("HR-EMP-0011", "Frances", "Allen", "Maple Tech Manufacturing", "Manufacturing - MTM", "Plant Operations Lead", "CAD", 12400.00),
        ("HR-EMP-0012", "Ken", "Thompson", "Northstar Cloud Services", "Cloud Platform - NCS", "Site Reliability Engineer", "USD", 14400.00),
        ("HR-EMP-0013", "Dennis", "Ritchie", "Northstar Cloud Services", "Cloud Platform - NCS", "Principal Systems Engineer", "USD", 14900.00),
        ("HR-EMP-0014", "Adele", "Goldberg", "Maple Tech Manufacturing", "Finance & Operations - MTM", "Senior Financial Analyst", "CAD", 11800.00),
        ("HR-EMP-0015", "John", "Cocke", "Maple Tech Manufacturing", "Manufacturing - MTM", "Plant Operations Lead", "CAD", 12100.00),
        ("HR-EMP-0016", "lynne", "Conway", "Maple Tech Manufacturing", "Engineering - MTM", "Principal Systems Engineer", "CAD", 13600.00),
        ("HR-EMP-0017", "Shafi", "Goldwasser", "Northstar Cloud Services", "Cloud Platform - NCS", "Site Reliability Engineer", "USD", 14100.00),
        ("HR-EMP-0018", "Silvio", "Micali", "Northstar Cloud Services", "Cloud Platform - NCS", "Site Reliability Engineer", "USD", 14000.00),
        ("HR-EMP-0019", " Judea", "Pearl", "Horizon Agritech Cooperative", "Agronomy Research - HAC", "Agronomy Data Scientist", "CAD", 12600.00),
        ("HR-EMP-0020", "Norman", "Borlaug", "Horizon Agritech Cooperative", "Agronomy Research - HAC", "Agronomy Data Scientist", "CAD", 12900.00),
        ("HR-EMP-0021", "Evelyn", "Boyd", "Maple Tech Manufacturing", "Finance & Operations - MTM", "Senior Financial Analyst", "CAD", 11400.00),
        ("HR-EMP-0022", "Mary", "Jackson", "Maple Tech Manufacturing", "Manufacturing - MTM", "Plant Operations Lead", "CAD", 12200.00),
        ("HR-EMP-0023", "Dorothy", "Vaughan", "Maple Tech Manufacturing", "Engineering - MTM", "Principal Systems Engineer", "CAD", 13400.00),
        ("HR-EMP-0024", "lara", "Chen", "Horizon Agritech Cooperative", "Agronomy Research - HAC", "Agronomy Data Scientist", "CAD", 11900.00),
    ]
    all_employees = [
        ("HR-EMP-0001", "Ada", "Lovelace", "Maple Tech Manufacturing", "Engineering - MTM", "Chief Technology Officer", "CAD", 16500.00),
        ("HR-EMP-0002", "Grace", "Hopper", "Maple Tech Manufacturing", "Engineering - MTM", "Principal Systems Engineer", "CAD", 13800.00),
        ("HR-EMP-0003", "Katherine", "Johnson", "Maple Tech Manufacturing", "Finance & Operations - MTM", "Senior Financial Analyst", "CAD", 11500.00),
        ("HR-EMP-0004", "Alan", "Turing", "Northstar Cloud Services", "Cloud Platform - NCS", "Site Reliability Engineer", "USD", 14200.00),
        ("HR-EMP-0005", "Margaret", "Hamilton", "Maple Tech Manufacturing", "Manufacturing - MTM", "Plant Operations Lead", "CAD", 12600.00),
        ("HR-EMP-0006", "Barbara", "Liskov", "Horizon Agritech Cooperative", "Agronomy Research - HAC", "Agronomy Data Scientist", "CAD", 12500.00),
    ] + extra_employees

    for idx, (eid, fname, lname, comp, dept, desig, curr, _) in enumerate(extra_employees, start=7):
        f_clean = fname.strip().capitalize()
        l_clean = lname.strip()
        upsert("EMPLOYEE", {
            "DOC_NAME": eid,
            "OWNER_USER": "Administrator",
            "MODIFIED_BY": "Administrator",
            "DOCSTATUS": 0,
            "IDX_NO": idx,
            "EMPLOYEE": eid,
            "FIRST_NAME": f_clean,
            "LAST_NAME": l_clean,
            "EMPLOYEE_NAME": f"{f_clean} {l_clean}",
            "STATUS": "Active",
            "COMPANY": comp,
            "DEPARTMENT": dept,
            "DESIGNATION": desig,
            "SALARY_CURRENCY": curr,
            "REPORTS_TO": "HR-EMP-0001",
        })

    # 4. Generate 24 Months (2025-01 .. 2026-12) of Seasonal Enterprise Volume!
    company_profiles = {
        "Maple Tech Manufacturing": {
            "currency": "CAD",
            "debtors": "Debtors - MTM",
            "creditors": "Creditors - MTM",
            "bank": "Operating Bank - MTM",
            "income": "Product Sales - MTM",
            "cogs": "Cost of Goods Sold - MTM",
            "tax": "HST Payable - MTM",
            "payroll": "Payroll Expense - MTM",
            "cost_center": "Operations - MTM",
            "warehouse": "Toronto Main Stores - MTM",
            "tax_rate": 0.13,
            "customers": [c for c in all_customers if c[2] == "Enterprise Industrial"],
            "items": [i for i in all_items if i[2] in ("Industrial Assemblies", "Electronic Subsystems")],
            "suppliers": [s for s in all_suppliers if s[2] == "Precision Components"],
        },
        "Northstar Cloud Services": {
            "currency": "USD",
            "debtors": "Debtors - NCS",
            "creditors": "Creditors - NCS",
            "bank": "Operating Bank - NCS",
            "income": "Service Revenue - NCS",
            "cogs": "Cloud Hosting Expense - NCS",
            "tax": "Sales Tax Payable - NCS",
            "payroll": "Payroll Expense - NCS",
            "cost_center": "Cloud Ops - NCS",
            "warehouse": None,
            "tax_rate": 0.08,
            "customers": [c for c in all_customers if c[2] == "SaaS Subscribers"],
            "items": [i for i in all_items if i[2] == "Cloud Subscriptions"],
            "suppliers": [s for s in all_suppliers if s[2] == "Cloud & Datacenter Vendors"],
        },
        "Horizon Agritech Cooperative": {
            "currency": "CAD",
            "debtors": "Debtors - HAC",
            "creditors": "Creditors - HAC",
            "bank": "Operating Bank - HAC",
            "income": "Agri Supply Revenue - HAC",
            "cogs": "Cost of Goods Sold - HAC",
            "tax": "GST Payable - HAC",
            "payroll": "Payroll Expense - HAC",
            "cost_center": "Field Farms - HAC",
            "warehouse": "Saskatoon Agro Depot - HAC",
            "tax_rate": 0.05,
            "customers": [c for c in all_customers if c[2] == "Agricultural Cooperatives"],
            "items": [i for i in all_items if i[2] == "Agricultural Inputs"],
            "suppliers": [s for s in all_suppliers if s[2] == "Raw Materials & Seeds"],
        },
    }

    so_seq = 0
    soi_seq = 0
    sinv_seq = 0
    sii_seq = 0
    po_seq = 0
    pinv_seq = 0
    pii_seq = 0
    pay_seq = 0
    gle_seq = 0
    sle_seq = 0

    company_names = list(company_profiles.keys())

    # 24 months: 100 Sales Orders + 100 Sales Invoices + 50 Purchase Orders + 50 Purchase Invoices per month
    for month_idx in range(24):
        yr = 2025 + (month_idx // 12)
        mo = (month_idx % 12) + 1
        fy = f"FY-{yr}"
        # Seasonal curve: Q2/Q4 peaks + steady YoY growth (~18%)
        seasonal = 1.0 + 0.18 * math.sin((mo - 3) * math.pi / 6.0) + (0.16 if yr == 2026 else 0.0)

        # Sales Orders & Sales Invoices (100 per month -> 2,400 each + ~6,000 line items each + 7,200 GL entries + 3,200 SLE)
        for slot in range(100):
            comp = company_names[(slot + month_idx) % 3]
            prof = company_profiles[comp]
            cust = prof["customers"][(slot * 3 + month_idx) % len(prof["customers"])]
            day = ((slot * 7 + month_idx * 3) % 27) + 1
            tx_date = date(yr, mo, day)
            post_date = tx_date + timedelta(days=2)
            due_date = post_date + timedelta(days=30)
            if post_date.year > 2026:
                post_date = date(2026, 12, 29)
            post_fy = f"FY-{post_date.year}"

            so_seq += 1
            sinv_seq += 1
            so_id = f"SO-TS-{yr}{mo:02d}-{so_seq:05d}"
            sinv_id = f"SINV-TS-{yr}{mo:02d}-{sinv_seq:05d}"

            line_count = 2 if (slot % 2 == 0) else 3
            net_total = 0.0
            line_specs = []
            for l_i in range(line_count):
                itm = prof["items"][(slot + l_i + month_idx) % len(prof["items"])]
                qty = float(((slot + l_i * 2) % 8) + 1) * (1.5 if seasonal > 1.15 else 1.0)
                qty = round(qty, 0)
                rate = round(itm[5] * (0.96 + 0.02 * (slot % 5)), 2)
                amt = round(qty * rate, 2)
                net_total = round(net_total + amt, 2)
                line_specs.append((itm, qty, rate, amt))

            tax_amt = round(net_total * prof["tax_rate"], 2)
            grand_total = round(net_total + tax_amt, 2)
            is_paid = (slot % 5) != 0
            is_partial = (slot % 5) == 0 and (slot % 10 != 0)
            paid_amt = grand_total if is_paid else (round(grand_total * 0.5, 2) if is_partial else 0.0)
            outstanding = round(grand_total - paid_amt, 2)
            inv_status = "Paid" if is_paid else ("Partly Paid" if is_partial else "Unpaid")

            upsert("SALES_ORDER", {
                "DOC_NAME": so_id,
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "CREATION_TS": f"{tx_date.isoformat()} 09:15:00",
                "MODIFIED_TS": f"{post_date.isoformat()} 14:20:00",
                "DOCSTATUS": 1,
                "IDX_NO": so_seq,
                "CUSTOMER": cust[0],
                "CUSTOMER_NAME": cust[1],
                "CUSTOMER_GROUP": cust[2],
                "TERRITORY": cust[3],
                "COMPANY": comp,
                "COST_CENTER": prof["cost_center"],
                "TRANSACTION_DATE": tx_date.isoformat(),
                "DELIVERY_DATE": post_date.isoformat(),
                "CURRENCY": prof["currency"],
                "CONVERSION_RATE": 1.0,
                "NET_TOTAL": net_total,
                "GRAND_TOTAL": grand_total,
                "STATUS": "Completed" if is_paid else "To Bill",
                "PER_DELIVERED": 100.0,
                "PER_BILLED": 100.0,
            })

            upsert("SALES_INVOICE", {
                "DOC_NAME": sinv_id,
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "CREATION_TS": f"{post_date.isoformat()} 10:00:00",
                "MODIFIED_TS": f"{post_date.isoformat()} 15:45:00",
                "DOCSTATUS": 1,
                "IDX_NO": sinv_seq,
                "CUSTOMER": cust[0],
                "CUSTOMER_NAME": cust[1],
                "CUSTOMER_GROUP": cust[2],
                "COMPANY": comp,
                "COST_CENTER": prof["cost_center"],
                "POSTING_DATE": post_date.isoformat(),
                "DUE_DATE": due_date.isoformat(),
                "CURRENCY": prof["currency"],
                "CONVERSION_RATE": 1.0,
                "DEBIT_TO": prof["debtors"],
                "NET_TOTAL": net_total,
                "GRAND_TOTAL": grand_total,
                "OUTSTANDING_AMOUNT": outstanding,
                "STATUS": inv_status,
            })

            for l_idx, (itm, qty, rate, amt) in enumerate(line_specs, start=1):
                soi_seq += 1
                sii_seq += 1
                wh = prof["warehouse"] if itm[4] else None
                upsert("SALES_ORDER_ITEM", {
                    "DOC_NAME": f"SOI-TS-{soi_seq:06d}",
                    "OWNER_USER": "Administrator",
                    "MODIFIED_BY": "Administrator",
                    "DOCSTATUS": 1,
                    "IDX_NO": l_idx,
                    "PARENT_ID": so_id,
                    "PARENT_TYPE": "Sales Order",
                    "PARENT_FIELD": "items",
                    "ITEM_CODE": itm[0],
                    "ITEM_NAME": itm[1],
                    "ITEM_GROUP": itm[2],
                    "QTY": qty,
                    "UOM": itm[3],
                    "STOCK_UOM": itm[3],
                    "RATE": rate,
                    "AMOUNT": amt,
                    "WAREHOUSE": wh,
                    "DELIVERY_DATE": post_date.isoformat(),
                })
                upsert("SALES_INVOICE_ITEM", {
                    "DOC_NAME": f"SII-TS-{sii_seq:06d}",
                    "OWNER_USER": "Administrator",
                    "MODIFIED_BY": "Administrator",
                    "DOCSTATUS": 1,
                    "IDX_NO": l_idx,
                    "PARENT_ID": sinv_id,
                    "PARENT_TYPE": "Sales Invoice",
                    "PARENT_FIELD": "items",
                    "ITEM_CODE": itm[0],
                    "ITEM_NAME": itm[1],
                    "ITEM_GROUP": itm[2],
                    "QTY": qty,
                    "UOM": itm[3],
                    "STOCK_UOM": itm[3],
                    "RATE": rate,
                    "AMOUNT": amt,
                    "INCOME_ACCOUNT": prof["income"],
                    "EXPENSE_ACCOUNT": prof["cogs"],
                    "COST_CENTER": prof["cost_center"],
                    "SALES_ORDER": so_id,
                    "WAREHOUSE": wh,
                })
                if itm[4] and wh:
                    sle_seq += 1
                    upsert("STOCK_LEDGER_ENTRY", {
                        "DOC_NAME": f"SLE-TS-{sle_seq:06d}",
                        "OWNER_USER": "Administrator",
                        "MODIFIED_BY": "Administrator",
                        "DOCSTATUS": 1,
                        "IDX_NO": sle_seq,
                        "ITEM_CODE": itm[0],
                        "WAREHOUSE": wh,
                        "POSTING_DATE": post_date.isoformat(),
                        "POSTING_TIME": "11:30:00",
                        "VOUCHER_TYPE": "Sales Invoice",
                        "VOUCHER_NO": sinv_id,
                        "ACTUAL_QTY": -qty,
                        "OUTGOING_RATE": itm[6],
                        "VALUATION_RATE": itm[6],
                        "STOCK_VALUE_DIFFERENCE": round(-qty * itm[6], 2),
                        "STOCK_UOM": itm[3],
                        "COMPANY": comp,
                    })

            # Balanced Double-Entry GL for Sales Invoice (Debit AR = Credit Revenue + Credit Tax)
            gle_seq += 1
            upsert("GL_ENTRY", {
                "DOC_NAME": f"GLE-TS-{gle_seq:06d}",
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "DOCSTATUS": 1,
                "IDX_NO": 1,
                "POSTING_DATE": post_date.isoformat(),
                "TRANSACTION_DATE": tx_date.isoformat(),
                "ACCOUNT": prof["debtors"],
                "PARTY_TYPE": "Customer",
                "PARTY": cust[0],
                "COST_CENTER": prof["cost_center"],
                "DEBIT": grand_total,
                "CREDIT": 0.0,
                "ACCOUNT_CURRENCY": prof["currency"],
                "DEBIT_IN_ACCOUNT_CURRENCY": grand_total,
                "CREDIT_IN_ACCOUNT_CURRENCY": 0.0,
                "VOUCHER_TYPE": "Sales Invoice",
                "VOUCHER_NO": sinv_id,
                "COMPANY": comp,
                "FISCAL_YEAR": post_fy,
            })
            gle_seq += 1
            upsert("GL_ENTRY", {
                "DOC_NAME": f"GLE-TS-{gle_seq:06d}",
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "DOCSTATUS": 1,
                "IDX_NO": 2,
                "POSTING_DATE": post_date.isoformat(),
                "TRANSACTION_DATE": tx_date.isoformat(),
                "ACCOUNT": prof["income"],
                "COST_CENTER": prof["cost_center"],
                "DEBIT": 0.0,
                "CREDIT": net_total,
                "ACCOUNT_CURRENCY": prof["currency"],
                "DEBIT_IN_ACCOUNT_CURRENCY": 0.0,
                "CREDIT_IN_ACCOUNT_CURRENCY": net_total,
                "VOUCHER_TYPE": "Sales Invoice",
                "VOUCHER_NO": sinv_id,
                "COMPANY": comp,
                "FISCAL_YEAR": post_fy,
            })
            gle_seq += 1
            upsert("GL_ENTRY", {
                "DOC_NAME": f"GLE-TS-{gle_seq:06d}",
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "DOCSTATUS": 1,
                "IDX_NO": 3,
                "POSTING_DATE": post_date.isoformat(),
                "TRANSACTION_DATE": tx_date.isoformat(),
                "ACCOUNT": prof["tax"],
                "COST_CENTER": prof["cost_center"],
                "DEBIT": 0.0,
                "CREDIT": tax_amt,
                "ACCOUNT_CURRENCY": prof["currency"],
                "DEBIT_IN_ACCOUNT_CURRENCY": 0.0,
                "CREDIT_IN_ACCOUNT_CURRENCY": tax_amt,
                "VOUCHER_TYPE": "Sales Invoice",
                "VOUCHER_NO": sinv_id,
                "COMPANY": comp,
                "FISCAL_YEAR": post_fy,
            })

            # Payment Entry + balanced GL when paid/partly paid (~80 per month -> ~1,920 Payment Entries)
            if paid_amt > 0:
                pay_seq += 1
                pay_id = f"PAY-TS-{yr}{mo:02d}-{pay_seq:05d}"
                pay_date = min(date(2026, 12, 30), post_date + timedelta(days=9))
                pay_fy = f"FY-{pay_date.year}"
                upsert("PAYMENT_ENTRY", {
                    "DOC_NAME": pay_id,
                    "OWNER_USER": "Administrator",
                    "MODIFIED_BY": "Administrator",
                    "DOCSTATUS": 1,
                    "IDX_NO": pay_seq,
                    "PAYMENT_TYPE": "Receive",
                    "POSTING_DATE": pay_date.isoformat(),
                    "COMPANY": comp,
                    "COST_CENTER": prof["cost_center"],
                    "PARTY_TYPE": "Customer",
                    "PARTY": cust[0],
                    "PARTY_NAME": cust[1],
                    "PAID_FROM": prof["debtors"],
                    "PAID_FROM_ACCOUNT_CURRENCY": prof["currency"],
                    "PAID_TO": prof["bank"],
                    "PAID_TO_ACCOUNT_CURRENCY": prof["currency"],
                    "PAID_AMOUNT": paid_amt,
                    "RECEIVED_AMOUNT": paid_amt,
                    "STATUS": "Submitted",
                })
                gle_seq += 1
                upsert("GL_ENTRY", {
                    "DOC_NAME": f"GLE-TS-{gle_seq:06d}",
                    "OWNER_USER": "Administrator",
                    "MODIFIED_BY": "Administrator",
                    "DOCSTATUS": 1,
                    "IDX_NO": 1,
                    "POSTING_DATE": pay_date.isoformat(),
                    "TRANSACTION_DATE": pay_date.isoformat(),
                    "ACCOUNT": prof["bank"],
                    "COST_CENTER": prof["cost_center"],
                    "DEBIT": paid_amt,
                    "CREDIT": 0.0,
                    "ACCOUNT_CURRENCY": prof["currency"],
                    "DEBIT_IN_ACCOUNT_CURRENCY": paid_amt,
                    "CREDIT_IN_ACCOUNT_CURRENCY": 0.0,
                    "VOUCHER_TYPE": "Payment Entry",
                    "VOUCHER_NO": pay_id,
                    "COMPANY": comp,
                    "FISCAL_YEAR": pay_fy,
                })
                gle_seq += 1
                upsert("GL_ENTRY", {
                    "DOC_NAME": f"GLE-TS-{gle_seq:06d}",
                    "OWNER_USER": "Administrator",
                    "MODIFIED_BY": "Administrator",
                    "DOCSTATUS": 1,
                    "IDX_NO": 2,
                    "POSTING_DATE": pay_date.isoformat(),
                    "TRANSACTION_DATE": pay_date.isoformat(),
                    "ACCOUNT": prof["debtors"],
                    "PARTY_TYPE": "Customer",
                    "PARTY": cust[0],
                    "COST_CENTER": prof["cost_center"],
                    "DEBIT": 0.0,
                    "CREDIT": paid_amt,
                    "ACCOUNT_CURRENCY": prof["currency"],
                    "DEBIT_IN_ACCOUNT_CURRENCY": 0.0,
                    "CREDIT_IN_ACCOUNT_CURRENCY": paid_amt,
                    "VOUCHER_TYPE": "Payment Entry",
                    "VOUCHER_NO": pay_id,
                    "COMPANY": comp,
                    "FISCAL_YEAR": pay_fy,
                })

        # Purchase Orders & Purchase Invoices (50 per month -> 1,200 PO + 1,200 PINV + 2,400 items + 2,400 GL + ~1,800 SLE)
        for pslot in range(50):
            comp = company_names[(pslot + month_idx) % 3]
            prof = company_profiles[comp]
            supp = prof["suppliers"][(pslot + month_idx) % len(prof["suppliers"])]
            day = ((pslot * 5 + 2) % 26) + 1
            p_date = date(yr, mo, day)
            p_due = min(date(2026, 12, 30), p_date + timedelta(days=30))
            po_seq += 1
            pinv_seq += 1
            po_id = f"PO-TS-{yr}{mo:02d}-{po_seq:05d}"
            pinv_id = f"PINV-TS-{yr}{mo:02d}-{pinv_seq:05d}"

            p_net = 0.0
            p_lines = []
            for l_i in range(2):
                itm = prof["items"][(pslot + l_i) % len(prof["items"])]
                qty = float(((pslot + l_i * 3) % 10) + 4)
                cost_rate = round((itm[6] if itm[6] > 0 else itm[5] * 0.35), 2)
                amt = round(qty * cost_rate, 2)
                p_net = round(p_net + amt, 2)
                p_lines.append((itm, qty, cost_rate, amt))

            upsert("PURCHASE_ORDER", {
                "DOC_NAME": po_id,
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "DOCSTATUS": 1,
                "IDX_NO": po_seq,
                "SUPPLIER": supp[0],
                "SUPPLIER_NAME": supp[1],
                "SUPPLIER_GROUP": supp[2],
                "COMPANY": comp,
                "COST_CENTER": prof["cost_center"],
                "TRANSACTION_DATE": p_date.isoformat(),
                "SCHEDULE_DATE": p_date.isoformat(),
                "CURRENCY": prof["currency"],
                "CONVERSION_RATE": 1.0,
                "NET_TOTAL": p_net,
                "GRAND_TOTAL": p_net,
                "STATUS": "Completed",
            })
            upsert("PURCHASE_INVOICE", {
                "DOC_NAME": pinv_id,
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "DOCSTATUS": 1,
                "IDX_NO": pinv_seq,
                "SUPPLIER": supp[0],
                "SUPPLIER_NAME": supp[1],
                "COMPANY": comp,
                "COST_CENTER": prof["cost_center"],
                "POSTING_DATE": p_date.isoformat(),
                "DUE_DATE": p_due.isoformat(),
                "CURRENCY": prof["currency"],
                "CONVERSION_RATE": 1.0,
                "CREDIT_TO": prof["creditors"],
                "NET_TOTAL": p_net,
                "GRAND_TOTAL": p_net,
                "OUTSTANDING_AMOUNT": 0.0 if (pslot % 4 != 0) else p_net,
                "STATUS": "Paid" if (pslot % 4 != 0) else "Unpaid",
            })
            for l_idx, (itm, qty, cost_rate, amt) in enumerate(p_lines, start=1):
                pii_seq += 1
                wh = prof["warehouse"] if itm[4] else None
                upsert("PURCHASE_INVOICE_ITEM", {
                    "DOC_NAME": f"PII-TS-{pii_seq:06d}",
                    "OWNER_USER": "Administrator",
                    "MODIFIED_BY": "Administrator",
                    "DOCSTATUS": 1,
                    "IDX_NO": l_idx,
                    "PARENT_ID": pinv_id,
                    "PARENT_TYPE": "Purchase Invoice",
                    "PARENT_FIELD": "items",
                    "ITEM_CODE": itm[0],
                    "ITEM_NAME": itm[1],
                    "ITEM_GROUP": itm[2],
                    "QTY": qty,
                    "RECEIVED_QTY": qty,
                    "UOM": itm[3],
                    "STOCK_UOM": itm[3],
                    "RATE": cost_rate,
                    "AMOUNT": amt,
                    "EXPENSE_ACCOUNT": prof["cogs"],
                    "COST_CENTER": prof["cost_center"],
                    "PURCHASE_ORDER": po_id,
                    "WAREHOUSE": wh,
                })
                if itm[4] and wh:
                    sle_seq += 1
                    upsert("STOCK_LEDGER_ENTRY", {
                        "DOC_NAME": f"SLE-TS-{sle_seq:06d}",
                        "OWNER_USER": "Administrator",
                        "MODIFIED_BY": "Administrator",
                        "DOCSTATUS": 1,
                        "IDX_NO": sle_seq,
                        "ITEM_CODE": itm[0],
                        "WAREHOUSE": wh,
                        "POSTING_DATE": p_date.isoformat(),
                        "POSTING_TIME": "08:45:00",
                        "VOUCHER_TYPE": "Purchase Invoice",
                        "VOUCHER_NO": pinv_id,
                        "ACTUAL_QTY": qty,
                        "INCOMING_RATE": cost_rate,
                        "VALUATION_RATE": cost_rate,
                        "STOCK_VALUE_DIFFERENCE": amt,
                        "STOCK_UOM": itm[3],
                        "COMPANY": comp,
                    })

            gle_seq += 1
            upsert("GL_ENTRY", {
                "DOC_NAME": f"GLE-TS-{gle_seq:06d}",
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "DOCSTATUS": 1,
                "IDX_NO": 1,
                "POSTING_DATE": p_date.isoformat(),
                "TRANSACTION_DATE": p_date.isoformat(),
                "ACCOUNT": prof["cogs"],
                "COST_CENTER": prof["cost_center"],
                "DEBIT": p_net,
                "CREDIT": 0.0,
                "ACCOUNT_CURRENCY": prof["currency"],
                "DEBIT_IN_ACCOUNT_CURRENCY": p_net,
                "CREDIT_IN_ACCOUNT_CURRENCY": 0.0,
                "VOUCHER_TYPE": "Purchase Invoice",
                "VOUCHER_NO": pinv_id,
                "COMPANY": comp,
                "FISCAL_YEAR": fy,
            })
            gle_seq += 1
            upsert("GL_ENTRY", {
                "DOC_NAME": f"GLE-TS-{gle_seq:06d}",
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "DOCSTATUS": 1,
                "IDX_NO": 2,
                "POSTING_DATE": p_date.isoformat(),
                "TRANSACTION_DATE": p_date.isoformat(),
                "ACCOUNT": prof["creditors"],
                "PARTY_TYPE": "Supplier",
                "PARTY": supp[0],
                "COST_CENTER": prof["cost_center"],
                "DEBIT": 0.0,
                "CREDIT": p_net,
                "ACCOUNT_CURRENCY": prof["currency"],
                "DEBIT_IN_ACCOUNT_CURRENCY": 0.0,
                "CREDIT_IN_ACCOUNT_CURRENCY": p_net,
                "VOUCHER_TYPE": "Purchase Invoice",
                "VOUCHER_NO": pinv_id,
                "COMPANY": comp,
                "FISCAL_YEAR": fy,
            })

        # HR Monthly Salary Slips (24 employees * 24 months = 576) & Attendance (24 employees * 10 sampled workdays = 5,760)
        m_end_day = 28 if mo == 2 else (30 if mo in (4, 6, 9, 11) else 31)
        for e_idx, (eid, fname, lname, comp, dept, desig, curr, base_gross) in enumerate(
            all_employees, start=1
        ):
            ename = f"{fname.strip().capitalize()} {lname.strip()}"
            gross = round(base_gross * (1.04 if yr == 2026 else 1.0), 2)
            ded = round(gross * 0.24, 2)
            net_pay = round(gross - ded, 2)
            upsert("SALARY_SLIP", {
                "DOC_NAME": f"SS-TS-{yr}{mo:02d}-{eid}",
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "DOCSTATUS": 1,
                "IDX_NO": e_idx,
                "EMPLOYEE": eid,
                "EMPLOYEE_NAME": ename,
                "COMPANY": comp,
                "DEPARTMENT": dept,
                "DESIGNATION": desig,
                "POSTING_DATE": f"{yr}-{mo:02d}-{m_end_day:02d}",
                "START_DATE": f"{yr}-{mo:02d}-01",
                "END_DATE": f"{yr}-{mo:02d}-{m_end_day:02d}",
                "CURRENCY": curr,
                "GROSS_PAY": gross,
                "TOTAL_DEDUCTION": ded,
                "NET_PAY": net_pay,
                "STATUS": "Submitted",
            })
            for wday in range(2, 22, 2):
                att_status = "Present" if ((wday + e_idx + mo) % 14 != 0) else "Work From Home"
                hrs = 8.0 + ((e_idx + wday) % 3) * 0.5
                upsert("ATTENDANCE", {
                    "DOC_NAME": f"ATT-TS-{yr}{mo:02d}{wday:02d}-{eid}",
                    "OWNER_USER": "Administrator",
                    "MODIFIED_BY": "Administrator",
                    "DOCSTATUS": 1,
                    "IDX_NO": wday,
                    "EMPLOYEE": eid,
                    "EMPLOYEE_NAME": ename,
                    "WORKING_HOURS": hrs,
                    "STATUS": att_status,
                    "ATTENDANCE_DATE": f"{yr}-{mo:02d}-{wday:02d}",
                    "COMPANY": comp,
                    "DEPARTMENT": dept,
                })

        # Helpdesk Tickets (50/month = 1,200), CRM Leads (25/month = 600), CRM Deals (18/month = 432)
        hd_statuses = ["Resolved", "Closed", "Replied", "Open"]
        hd_priorities = ["Low", "Medium", "High", "Urgent"]
        hd_topics = [
            "Modbus gateway packet loss check",
            "Dedicated cloud bench memory tuning",
            "LoRaWAN soil moisture calibration",
            "Quarterly GST/HST reconciliation inquiry",
            "Automated backup snapshot verification",
            "Pump bearing vibration threshold alert",
        ]
        for t_i in range(50):
            seq_num = month_idx * 50 + t_i + 1
            t_day = ((t_i * 3) % 27) + 1
            upsert("HD_TICKET", {
                "DOC_NAME": f"HD-TS-{seq_num:05d}",
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "CREATION_TS": f"{yr}-{mo:02d}-{t_day:02d} 11:00:00",
                "MODIFIED_TS": f"{yr}-{mo:02d}-{t_day:02d} 16:30:00",
                "DOCSTATUS": 0,
                "IDX_NO": seq_num,
                "SUBJECT": f"{hd_topics[seq_num % len(hd_topics)]} (#{seq_num})",
                "RAISED_BY": f"ops{seq_num % 24 + 1}@customer-telemetry.example",
                "STATUS": hd_statuses[seq_num % len(hd_statuses)],
                "PRIORITY": hd_priorities[(seq_num + month_idx) % len(hd_priorities)],
                "AGREEMENT_STATUS": "Fulfilled" if (seq_num % 7 != 0) else "Failed",
            })

        lead_statuses = ["Qualified", "Converted", "Contacted", "New", "Lost"]
        deal_statuses = ["Won", "Negotiation", "Proposal", "Qualification", "Lost"]
        owners = [
            "ada.lovelace@scratchbird-demo.example",
            "grace.hopper@scratchbird-demo.example",
            "katherine.johnson@scratchbird-demo.example",
            "alan.turing@scratchbird-demo.example",
        ]
        for l_i in range(25):
            l_seq = month_idx * 25 + l_i + 1
            lead_id = f"LEAD-TS-{l_seq:05d}"
            ann_rev = round(250000.0 + (l_seq % 19) * 185000.0, 2)
            upsert("CRM_LEAD", {
                "DOC_NAME": lead_id,
                "OWNER_USER": "Administrator",
                "MODIFIED_BY": "Administrator",
                "CREATION_TS": f"{yr}-{mo:02d}-{(l_i % 27) + 1:02d} 09:30:00",
                "DOCSTATUS": 0,
                "IDX_NO": l_seq,
                "FIRST_NAME": f"Prospect{l_seq}",
                "LAST_NAME": "Enterprise",
                "LEAD_OWNER": owners[l_seq % len(owners)],
                "STATUS": lead_statuses[l_seq % len(lead_statuses)],
                "EMAIL": f"prospect{l_seq}@enterprise-demo.example",
                "NO_OF_EMPLOYEES": str(((l_seq % 8) + 1) * 50),
                "ANNUAL_REVENUE": ann_rev,
            })
            if l_i < 18:
                d_seq = month_idx * 18 + l_i + 1
                prob = [95.0, 75.0, 55.0, 35.0, 0.0][d_seq % 5]
                upsert("CRM_DEAL", {
                    "DOC_NAME": f"DEAL-TS-{d_seq:05d}",
                    "OWNER_USER": "Administrator",
                    "MODIFIED_BY": "Administrator",
                    "CREATION_TS": f"{yr}-{mo:02d}-{(l_i % 27) + 1:02d} 13:00:00",
                    "DOCSTATUS": 0,
                    "IDX_NO": d_seq,
                    "LEAD": lead_id,
                    "DEAL_OWNER": owners[d_seq % len(owners)],
                    "STATUS": deal_statuses[d_seq % 5],
                    "PROBABILITY": prob,
                    "ANNUAL_REVENUE": round(ann_rev * 0.12, 2),
                    "CURRENCY": "CAD" if (d_seq % 2 == 0) else "USD",
                })

    # 5. Datum + Cargo Cloud Observability Samples (3,600), Logs (1,200), Traces (900)
    benches = [
        ("cargo:prod-bench-01", "web", "erp.mapletech.cloud"),
        ("cargo:prod-bench-02", "worker", "portal.northstarcloud.io"),
        ("cargo:prod-bench-03", "firebird-db", "coop.horizonagritech.ca"),
    ]
    metrics = [
        ("system_cpu_usage_percent", "cpu", 38.0),
        ("system_memory_usage_percent", "mem", 62.0),
        ("firebird_page_reads_per_sec", "io", 420.0),
        ("http_request_duration_p95_ms", "latency", 44.0),
    ]
    base_day = date(2026, 8, 1)
    for s_i in range(1, 3601):
        res_id, svc, site_host = benches[s_i % len(benches)]
        m_name, s_kind, base_val = metrics[s_i % len(metrics)]
        d_off = (s_i - 1) // 34
        hr = (s_i * 3) % 24
        mn = (s_i * 7) % 60
        ts_day = base_day + timedelta(days=min(105, d_off))
        val = round(base_val * (0.75 + 0.5 * math.sin(s_i * 0.17) ** 2), 2)
        upsert("DATUM_SAMPLES", {
            "SAMPLE_ID": 1000 + s_i,
            "TS": f"{ts_day.isoformat()} {hr:02d}:{mn:02d}:00+00:00",
            "METRIC": m_name,
            "RESOURCE_ID": res_id,
            "SERVICE_NAME": svc,
            "SERIES_KIND": s_kind,
            "LABELS_JSON": json.dumps({"service": svc, "site": site_host}),
            "SAMPLE_VALUE": val,
        }, pk_cols=("SAMPLE_ID",))

    log_levels = ["INFO", "INFO", "INFO", "WARN", "ERROR"]
    for lg_i in range(1, 1201):
        res_id, svc, site_host = benches[lg_i % len(benches)]
        lvl = log_levels[lg_i % len(log_levels)]
        http_code = 200 if lvl == "INFO" else (429 if lvl == "WARN" else 502)
        d_off = (lg_i - 1) // 12
        ts_day = base_day + timedelta(days=min(105, d_off))
        upsert("DATUM_LOGS", {
            "LOG_ID": 1000 + lg_i,
            "TS": f"{ts_day.isoformat()} {(lg_i * 5) % 24:02d}:{(lg_i * 11) % 60:02d}:15+00:00",
            "RESOURCE_ID": res_id,
            "PRODUCT": "frappe-cloud",
            "SERVICE_NAME": svc,
            "LOG_LEVEL": lvl,
            "LOG_SOURCE": f"{svc}.log",
            "HTTP_STATUS": http_code,
            "MESSAGE_TEXT": f"{lvl} [{site_host}] request completed status={http_code}",
            "ATTRIBUTES_JSON": json.dumps({"site": site_host, "status": http_code}),
        }, pk_cols=("LOG_ID",))

    for tr_i in range(1, 451):
        trace_id = f"{tr_i:032x}"
        root_span = f"{(tr_i * 2 - 1):016x}"
        db_span = f"{(tr_i * 2):016x}"
        res_id, _, site_host = benches[tr_i % len(benches)]
        ts_day = base_day + timedelta(days=min(105, tr_i // 5))
        ts_str = f"{ts_day.isoformat()} {(tr_i * 2) % 24:02d}:{(tr_i * 13) % 60:02d}:05+00:00"
        is_err = (tr_i % 19 == 0)
        upsert("DATUM_TRACES", {
            "TRACE_ID": trace_id,
            "SPAN_ID": root_span,
            "PARENT_SPAN_ID": None,
            "TS": ts_str,
            "RESOURCE_ID": res_id,
            "SERVICE_NAME": "frappe-web",
            "SPAN_NAME": "POST /api/resource/Sales Invoice",
            "SPAN_KIND": "SERVER",
            "DURATION_NS": 38000000 + (tr_i % 15) * 4200000,
            "STATUS_CODE": "ERROR" if is_err else "OK",
            "STATUS_MESSAGE": "Deadlock retry" if is_err else "",
            "ATTRIBUTES_JSON": json.dumps({"site": site_host, "http.method": "POST"}),
        }, pk_cols=("TRACE_ID", "SPAN_ID"))
        upsert("DATUM_TRACES", {
            "TRACE_ID": trace_id,
            "SPAN_ID": db_span,
            "PARENT_SPAN_ID": root_span,
            "TS": ts_str,
            "RESOURCE_ID": res_id,
            "SERVICE_NAME": "firebird-db",
            "SPAN_NAME": "INSERT INTO GL_ENTRY",
            "SPAN_KIND": "CLIENT",
            "DURATION_NS": 5400000 + (tr_i % 9) * 900000,
            "STATUS_CODE": "ERROR" if is_err else "OK",
            "STATUS_MESSAGE": "Lock conflict on record" if is_err else "",
            "ATTRIBUTES_JSON": json.dumps({"db.system": "firebird", "db.name": "frappe_suite.fdb"}),
        }, pk_cols=("TRACE_ID", "SPAN_ID"))

    # Execute in crisp 4,000-statement COMMIT batches with async write -> SET STATISTICS -> sync write
    script_lines: list[str] = ["SET NAMES UTF8;", "SET AUTODDL OFF;"]
    for idx, stmt in enumerate(stmts, start=1):
        script_lines.append(stmt)
        if idx % 4000 == 0:
            script_lines.append("COMMIT;")
    script_lines.append("COMMIT;")
    # Refresh selectivity statistics across primary & composite analytical indexes
    script_lines.extend([
        "SET TERM ^ ;",
        """EXECUTE BLOCK AS
DECLARE VARIABLE idx_name VARCHAR(63);
BEGIN
  FOR SELECT TRIM(RDB$INDEX_NAME)
      FROM RDB$INDICES
      WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0
        AND TRIM(RDB$RELATION_NAME) IN (
          'ACCOUNT', 'CUSTOMER', 'SUPPLIER', 'ITEM', 'EMPLOYEE',
          'GL_ENTRY', 'SALES_ORDER', 'SALES_ORDER_ITEM',
          'SALES_INVOICE', 'SALES_INVOICE_ITEM',
          'PURCHASE_ORDER', 'PURCHASE_INVOICE', 'PURCHASE_INVOICE_ITEM',
          'PAYMENT_ENTRY', 'STOCK_LEDGER_ENTRY',
          'ATTENDANCE', 'SALARY_SLIP', 'HD_TICKET',
          'CRM_LEAD', 'CRM_DEAL',
          'DATUM_SAMPLES', 'DATUM_LOGS', 'DATUM_TRACES'
        )
      INTO :idx_name
  DO
  BEGIN
    EXECUTE STATEMENT 'SET STATISTICS INDEX "' || :idx_name || '"';
  END
END^""",
        "SET TERM ; ^",
        "COMMIT;",
    ])
    sql_payload = "\n".join(script_lines) + "\n"

    subprocess.run(
        [
            "docker", "exec", container,
            "/opt/firebird/bin/gfix", "-write", "async",
            "-user", fb_user, "-password", fb_password, fb_db,
        ],
        check=True,
    )
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".sql", encoding="utf-8", delete=False) as tf:
            tf.write(sql_payload)
            host_sql_path = Path(tf.name)
        container_sql_path = "/tmp/frappe_timeseries_seed.sql"
        try:
            subprocess.run(
                ["docker", "cp", str(host_sql_path), f"{container}:{container_sql_path}"],
                check=True,
            )
            subprocess.run(
                [
                    "docker", "exec", container,
                    "/opt/firebird/bin/isql", "-q", "-bail", "-ch", "UTF8",
                    "-u", fb_user, "-p", fb_password,
                    "-i", container_sql_path, fb_db,
                ],
                check=True,
            )
        finally:
            host_sql_path.unlink(missing_ok=True)
            subprocess.run(
                ["docker", "exec", container, "rm", "-f", container_sql_path],
                check=False,
            )
    finally:
        subprocess.run(
            [
                "docker", "exec", container,
                "/opt/firebird/bin/gfix", "-write", "sync",
                "-user", fb_user, "-password", fb_password, fb_db,
            ],
            check=True,
        )

    conn = fbd.connect(dsn, user=fb_user, password=fb_password, charset="UTF8")
    cur = conn.cursor()
    counts = {}
    for t in (
        "ACCOUNT", "CUSTOMER", "SUPPLIER", "ITEM", "EMPLOYEE",
        "SALES_ORDER", "SALES_ORDER_ITEM", "SALES_INVOICE", "SALES_INVOICE_ITEM",
        "PURCHASE_ORDER", "PURCHASE_INVOICE", "PURCHASE_INVOICE_ITEM",
        "PAYMENT_ENTRY", "GL_ENTRY", "STOCK_LEDGER_ENTRY",
        "ATTENDANCE", "SALARY_SLIP", "HD_TICKET", "CRM_LEAD", "CRM_DEAL",
        "DATUM_SAMPLES", "DATUM_LOGS", "DATUM_TRACES",
    ):
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        counts[t] = cur.fetchone()[0]
    conn.close()
    return counts


def build_sqlite_edge_database(sqlite_path: Path) -> dict[str, int]:
    """Create Frappe Books & Retail POS SQLite Edge database for polyglot compare/ETL."""
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if sqlite_path.exists():
        sqlite_path.unlink()

    conn = sqlite3.connect(sqlite_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    conn.executescript(
        """
        CREATE TABLE COMPANY (
            DOC_NAME TEXT PRIMARY KEY NOT NULL,
            COMPANY_NAME TEXT NOT NULL,
            ABBR TEXT NOT NULL,
            DEFAULT_CURRENCY TEXT NOT NULL DEFAULT 'CAD',
            COUNTRY TEXT NOT NULL DEFAULT 'Canada',
            EDGE_STORE_CODE TEXT NOT NULL
        );

        CREATE TABLE ACCOUNT (
            DOC_NAME TEXT PRIMARY KEY NOT NULL,
            ACCOUNT_NAME TEXT NOT NULL,
            COMPANY TEXT NOT NULL REFERENCES COMPANY(DOC_NAME),
            ROOT_TYPE TEXT NOT NULL,
            ACCOUNT_TYPE TEXT NOT NULL,
            ACCOUNT_CURRENCY TEXT NOT NULL DEFAULT 'CAD',
            IS_GROUP INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE CUSTOMER (
            DOC_NAME TEXT PRIMARY KEY NOT NULL,
            CUSTOMER_NAME TEXT NOT NULL,
            CUSTOMER_GROUP TEXT NOT NULL,
            TERRITORY TEXT NOT NULL,
            DEFAULT_CURRENCY TEXT NOT NULL DEFAULT 'CAD',
            LOYALTY_TIER TEXT DEFAULT 'Standard'
        );

        CREATE TABLE ITEM (
            DOC_NAME TEXT PRIMARY KEY NOT NULL,
            ITEM_CODE TEXT NOT NULL UNIQUE,
            ITEM_NAME TEXT NOT NULL,
            ITEM_GROUP TEXT NOT NULL,
            STOCK_UOM TEXT NOT NULL DEFAULT 'Nos',
            STANDARD_RATE REAL NOT NULL,
            VALUATION_RATE REAL NOT NULL,
            BARCODE_EAN13 TEXT
        );

        CREATE TABLE SALES_INVOICE (
            DOC_NAME TEXT PRIMARY KEY NOT NULL,
            CUSTOMER TEXT NOT NULL REFERENCES CUSTOMER(DOC_NAME),
            CUSTOMER_NAME TEXT NOT NULL,
            COMPANY TEXT NOT NULL REFERENCES COMPANY(DOC_NAME),
            POSTING_DATE TEXT NOT NULL,
            CURRENCY TEXT NOT NULL DEFAULT 'CAD',
            NET_TOTAL REAL NOT NULL,
            GRAND_TOTAL REAL NOT NULL,
            OUTSTANDING_AMOUNT REAL NOT NULL DEFAULT 0.0,
            STATUS TEXT NOT NULL,
            EDGE_TERMINAL_ID TEXT NOT NULL,
            SYNC_STATE TEXT NOT NULL DEFAULT 'SYNCED'
        );

        CREATE TABLE SALES_INVOICE_ITEM (
            DOC_NAME TEXT PRIMARY KEY NOT NULL,
            PARENT_ID TEXT NOT NULL REFERENCES SALES_INVOICE(DOC_NAME),
            ITEM_CODE TEXT NOT NULL REFERENCES ITEM(DOC_NAME),
            ITEM_NAME TEXT NOT NULL,
            QTY REAL NOT NULL,
            RATE REAL NOT NULL,
            AMOUNT REAL NOT NULL
        );

        CREATE TABLE GL_ENTRY (
            DOC_NAME TEXT PRIMARY KEY NOT NULL,
            POSTING_DATE TEXT NOT NULL,
            ACCOUNT TEXT NOT NULL REFERENCES ACCOUNT(DOC_NAME),
            PARTY_TYPE TEXT,
            PARTY TEXT,
            DEBIT REAL NOT NULL DEFAULT 0.0,
            CREDIT REAL NOT NULL DEFAULT 0.0,
            VOUCHER_TYPE TEXT NOT NULL,
            VOUCHER_NO TEXT NOT NULL,
            COMPANY TEXT NOT NULL REFERENCES COMPANY(DOC_NAME)
        );

        CREATE TABLE POS_SYNC_OUTBOX (
            OUTBOX_ID INTEGER PRIMARY KEY AUTOINCREMENT,
            ENTITY_TYPE TEXT NOT NULL,
            ENTITY_KEY TEXT NOT NULL,
            TERMINAL_ID TEXT NOT NULL,
            CREATED_AT TEXT NOT NULL,
            SYNC_STATUS TEXT NOT NULL,
            PAYLOAD_JSON TEXT NOT NULL
        );

        CREATE INDEX IX_EDGE_SINV_DATE ON SALES_INVOICE(POSTING_DATE, COMPANY);
        CREATE INDEX IX_EDGE_GLE_ACCT_DATE ON GL_ENTRY(ACCOUNT, POSTING_DATE);
        CREATE INDEX IX_EDGE_OUTBOX_STATUS ON POS_SYNC_OUTBOX(SYNC_STATUS, CREATED_AT);

        CREATE VIEW VW_EDGE_POS_DAILY_SALES AS
        SELECT
            POSTING_DATE,
            COMPANY,
            EDGE_TERMINAL_ID,
            SYNC_STATE,
            COUNT(*) AS INVOICE_COUNT,
            ROUND(SUM(NET_TOTAL), 2) AS NET_REVENUE,
            ROUND(SUM(GRAND_TOTAL), 2) AS GROSS_REVENUE
        FROM SALES_INVOICE
        GROUP BY POSTING_DATE, COMPANY, EDGE_TERMINAL_ID, SYNC_STATE;

        CREATE VIEW VW_EDGE_UNSYNCED_OUTBOX AS
        SELECT OUTBOX_ID, ENTITY_TYPE, ENTITY_KEY, TERMINAL_ID, CREATED_AT, SYNC_STATUS
        FROM POS_SYNC_OUTBOX
        WHERE SYNC_STATUS <> 'ACKED';
        """
    )

    conn.executemany(
        "INSERT INTO COMPANY VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("Maple Tech Manufacturing", "Maple Tech Manufacturing", "MTM", "CAD", "Canada", "TOR-POS-01"),
            ("Horizon Agritech Cooperative", "Horizon Agritech Cooperative", "HAC", "CAD", "Canada", "YXE-POS-02"),
        ],
    )
    conn.executemany(
        "INSERT INTO ACCOUNT VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("POS Cash Drawer - MTM", "POS Cash Drawer", "Maple Tech Manufacturing", "Asset", "Cash", "CAD", 0),
            ("Product Sales - MTM", "Product Sales", "Maple Tech Manufacturing", "Income", "Income Account", "CAD", 0),
            ("HST Payable - MTM", "HST Tax Payable", "Maple Tech Manufacturing", "Liability", "Tax", "CAD", 0),
            ("POS Cash Drawer - HAC", "Depot Counter Cash", "Horizon Agritech Cooperative", "Asset", "Cash", "CAD", 0),
            ("Agri Supply Revenue - HAC", "Agri Counter Revenue", "Horizon Agritech Cooperative", "Income", "Income Account", "CAD", 0),
            ("GST Payable - HAC", "GST Payable", "Horizon Agritech Cooperative", "Liability", "Tax", "CAD", 0),
        ],
    )
    edge_customers = [
        ("CUST-0001", "Northwind Field Lab", "Enterprise Industrial", "North America", "CAD", "Gold"),
        ("CUST-0002", "Contoso Water Systems", "Enterprise Industrial", "North America", "CAD", "Platinum"),
        ("CUST-0006", "Prairie Grain Growers", "Agricultural Cooperatives", "North America", "CAD", "Gold"),
        ("CUST-0017", "Manitoba Pulse & Grain Co-op", "Agricultural Cooperatives", "North America", "CAD", "Silver"),
        ("WALK-IN-ONT", "Ontario Counter Walk-In", "Enterprise Industrial", "North America", "CAD", "Standard"),
        ("WALK-IN-SK", "Saskatoon Co-op Walk-In", "Agricultural Cooperatives", "North America", "CAD", "Standard"),
    ]
    conn.executemany("INSERT INTO CUSTOMER VALUES (?, ?, ?, ?, ?, ?)", edge_customers)

    edge_items = [
        ("ITM-SEAL-KIT", "ITM-SEAL-KIT", "High-Pressure Mechanical Seal Kit", "Industrial Assemblies", "Box", 410.0, 225.0, "6291041500213"),
        ("ITM-PLC-EDGE", "ITM-PLC-EDGE", "Edge Telemetry Gateway v4", "Electronic Subsystems", "Nos", 980.0, 540.0, "6291041500220"),
        ("ITM-VIB-PROBE", "ITM-VIB-PROBE", "Tri-Axial Piezo Vibration Sensor", "Electronic Subsystems", "Nos", 540.0, 295.0, "6291041500237"),
        ("ITM-SOIL-SENS", "ITM-SOIL-SENS", "LoRaWAN Soil Moisture Probe", "Agricultural Inputs", "Nos", 320.0, 175.0, "6291041500244"),
        ("ITM-GRAIN-MON", "ITM-GRAIN-MON", "Silo Temperature & CO2 Spear", "Agricultural Inputs", "Nos", 480.0, 275.0, "6291041500251"),
    ]
    conn.executemany("INSERT INTO ITEM VALUES (?, ?, ?, ?, ?, ?, ?, ?)", edge_items)

    sinv_rows = []
    sii_rows = []
    gle_rows = []
    outbox_rows = []
    start_d = date(2026, 1, 1)
    for i in range(1, 901):
        is_mtm = (i % 2 == 0)
        comp = "Maple Tech Manufacturing" if is_mtm else "Horizon Agritech Cooperative"
        cust = edge_customers[(i * 3) % len(edge_customers)]
        itm = edge_items[i % 3] if is_mtm else edge_items[3 + (i % 2)]
        pdate = (start_d + timedelta(days=(i * 11) % 320)).isoformat()
        qty = float((i % 4) + 1)
        net = round(qty * itm[5], 2)
        tax_r = 0.13 if is_mtm else 0.05
        tax = round(net * tax_r, 2)
        gross = round(net + tax, 2)
        inv_id = f"POS-SINV-2026-{i:05d}"
        term_id = f"TERM-{'TOR' if is_mtm else 'YXE'}-{(i % 3) + 1:02d}"
        sync_st = "QUEUED" if i > 875 else "SYNCED"
        sinv_rows.append((inv_id, cust[0], cust[1], comp, pdate, "CAD", net, gross, 0.0, "Paid", term_id, sync_st))
        sii_rows.append((f"POS-SII-{i:05d}", inv_id, itm[0], itm[2], qty, itm[5], net))
        cash_acc = "POS Cash Drawer - MTM" if is_mtm else "POS Cash Drawer - HAC"
        inc_acc = "Product Sales - MTM" if is_mtm else "Agri Supply Revenue - HAC"
        tax_acc = "HST Payable - MTM" if is_mtm else "GST Payable - HAC"
        gle_rows.append((f"POS-GLE-{i:05d}-1", pdate, cash_acc, "Customer", cust[0], gross, 0.0, "Sales Invoice", inv_id, comp))
        gle_rows.append((f"POS-GLE-{i:05d}-2", pdate, inc_acc, None, None, 0.0, net, "Sales Invoice", inv_id, comp))
        gle_rows.append((f"POS-GLE-{i:05d}-3", pdate, tax_acc, None, None, 0.0, tax, "Sales Invoice", inv_id, comp))
        if sync_st == "QUEUED":
            outbox_rows.append((
                "Sales Invoice",
                inv_id,
                term_id,
                f"{pdate}T17:15:00Z",
                "PENDING",
                json.dumps({"invoice": inv_id, "company": comp, "grand_total": gross}),
            ))

    conn.executemany("INSERT INTO SALES_INVOICE VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", sinv_rows)
    conn.executemany("INSERT INTO SALES_INVOICE_ITEM VALUES (?, ?, ?, ?, ?, ?, ?)", sii_rows)
    conn.executemany("INSERT INTO GL_ENTRY VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", gle_rows)
    conn.executemany(
        "INSERT INTO POS_SYNC_OUTBOX (ENTITY_TYPE, ENTITY_KEY, TERMINAL_ID, CREATED_AT, SYNC_STATUS, PAYLOAD_JSON) VALUES (?, ?, ?, ?, ?, ?)",
        outbox_rows,
    )
    conn.commit()
    summary = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("COMPANY", "ACCOUNT", "CUSTOMER", "ITEM", "SALES_INVOICE", "SALES_INVOICE_ITEM", "GL_ENTRY", "POS_SYNC_OUTBOX")
    }
    conn.close()
    return summary


def build_duckdb_lakehouse(
    duckdb_path: Path,
    donor_root: Path,
    *,
    fb_host: str,
    fb_port: int,
    fb_db: str,
    fb_user: str,
    fb_password: str,
) -> dict[str, int]:
    """Create DuckDB Analytical Lakehouse syncing Firebird ERP marts + real data-gov-in CSVs."""
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    if duckdb_path.exists():
        duckdb_path.unlink()

    dsn = f"{fb_host}/{fb_port}:{fb_db}"
    fb_conn = fbd.connect(dsn, user=fb_user, password=fb_password, charset="UTF8")
    fb_cur = fb_conn.cursor()

    dk = duckdb.connect(str(duckdb_path))

    # 1. Replicate conformed Dimension & Fact snapshots from Firebird into DuckDB
    dk.execute(
        """
        CREATE TABLE COMPANY (
            DOC_NAME VARCHAR PRIMARY KEY,
            COMPANY_NAME VARCHAR,
            ABBR VARCHAR,
            DEFAULT_CURRENCY VARCHAR,
            DOMAIN VARCHAR
        );
        CREATE TABLE ACCOUNT (
            DOC_NAME VARCHAR PRIMARY KEY,
            ACCOUNT_NAME VARCHAR,
            COMPANY VARCHAR,
            ROOT_TYPE VARCHAR,
            REPORT_TYPE VARCHAR,
            ACCOUNT_TYPE VARCHAR,
            ACCOUNT_CURRENCY VARCHAR
        );
        CREATE TABLE CUSTOMER (
            DOC_NAME VARCHAR PRIMARY KEY,
            CUSTOMER_NAME VARCHAR,
            CUSTOMER_GROUP VARCHAR,
            TERRITORY VARCHAR,
            DEFAULT_CURRENCY VARCHAR
        );
        CREATE TABLE ITEM (
            DOC_NAME VARCHAR PRIMARY KEY,
            ITEM_CODE VARCHAR,
            ITEM_NAME VARCHAR,
            ITEM_GROUP VARCHAR,
            STOCK_UOM VARCHAR,
            STANDARD_RATE DOUBLE,
            VALUATION_RATE DOUBLE
        );
        CREATE TABLE SALES_INVOICE (
            DOC_NAME VARCHAR PRIMARY KEY,
            CUSTOMER VARCHAR,
            CUSTOMER_NAME VARCHAR,
            COMPANY VARCHAR,
            POSTING_DATE DATE,
            CURRENCY VARCHAR,
            NET_TOTAL DOUBLE,
            GRAND_TOTAL DOUBLE,
            OUTSTANDING_AMOUNT DOUBLE,
            STATUS VARCHAR
        );
        CREATE TABLE GL_ENTRY (
            DOC_NAME VARCHAR PRIMARY KEY,
            POSTING_DATE DATE,
            ACCOUNT VARCHAR,
            PARTY_TYPE VARCHAR,
            PARTY VARCHAR,
            COST_CENTER VARCHAR,
            DEBIT DOUBLE,
            CREDIT DOUBLE,
            VOUCHER_TYPE VARCHAR,
            VOUCHER_NO VARCHAR,
            COMPANY VARCHAR,
            FISCAL_YEAR VARCHAR
        );
        """
    )

    for tbl, cols in [
        ("COMPANY", ("DOC_NAME", "COMPANY_NAME", "ABBR", "DEFAULT_CURRENCY", "DOMAIN")),
        ("ACCOUNT", ("DOC_NAME", "ACCOUNT_NAME", "COMPANY", "ROOT_TYPE", "REPORT_TYPE", "ACCOUNT_TYPE", "ACCOUNT_CURRENCY")),
        ("CUSTOMER", ("DOC_NAME", "CUSTOMER_NAME", "CUSTOMER_GROUP", "TERRITORY", "DEFAULT_CURRENCY")),
        ("ITEM", ("DOC_NAME", "ITEM_CODE", "ITEM_NAME", "ITEM_GROUP", "STOCK_UOM", "STANDARD_RATE", "VALUATION_RATE")),
        ("SALES_INVOICE", ("DOC_NAME", "CUSTOMER", "CUSTOMER_NAME", "COMPANY", "POSTING_DATE", "CURRENCY", "NET_TOTAL", "GRAND_TOTAL", "OUTSTANDING_AMOUNT", "STATUS")),
        ("GL_ENTRY", ("DOC_NAME", "POSTING_DATE", "ACCOUNT", "PARTY_TYPE", "PARTY", "COST_CENTER", "DEBIT", "CREDIT", "VOUCHER_TYPE", "VOUCHER_NO", "COMPANY", "FISCAL_YEAR")),
    ]:
        col_list = ", ".join(f'"{c}"' for c in cols)
        fb_cur.execute(f'SELECT {col_list} FROM "{tbl}"')
        rows = [
            tuple(float(v) if hasattr(v, "as_tuple") else v for v in r)
            for r in fb_cur.fetchall()
        ]
        placeholders = ", ".join(["?"] * len(cols))
        if rows:
            dk.executemany(f"INSERT INTO {tbl} VALUES ({placeholders})", rows)

    fb_conn.close()

    # 2. Build pre-aggregated Star-Schema Analytical Marts in DuckDB
    dk.execute(
        """
        CREATE TABLE MART_GL_MONTHLY AS
        SELECT
            DATE_TRUNC('month', g.POSTING_DATE)::DATE AS MONTH_START,
            g.FISCAL_YEAR,
            g.COMPANY,
            a.ROOT_TYPE,
            a.REPORT_TYPE,
            a.ACCOUNT_TYPE,
            g.ACCOUNT,
            g.COST_CENTER,
            COUNT(*) AS ENTRY_COUNT,
            ROUND(SUM(g.DEBIT), 2) AS TOTAL_DEBIT,
            ROUND(SUM(g.CREDIT), 2) AS TOTAL_CREDIT,
            ROUND(SUM(g.DEBIT - g.CREDIT), 2) AS NET_MOVEMENT
        FROM GL_ENTRY g
        LEFT JOIN ACCOUNT a ON a.DOC_NAME = g.ACCOUNT
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8;

        CREATE TABLE MART_REVENUE_COHORTS AS
        SELECT
            DATE_TRUNC('month', s.POSTING_DATE)::DATE AS INVOICE_MONTH,
            s.COMPANY,
            c.CUSTOMER_GROUP,
            c.TERRITORY,
            s.CURRENCY,
            COUNT(*) AS INVOICE_COUNT,
            COUNT(DISTINCT s.CUSTOMER) AS ACTIVE_CUSTOMERS,
            ROUND(SUM(s.NET_TOTAL), 2) AS NET_REVENUE,
            ROUND(SUM(s.GRAND_TOTAL), 2) AS GROSS_BILLED,
            ROUND(SUM(s.OUTSTANDING_AMOUNT), 2) AS OPEN_RECEIVABLES
        FROM SALES_INVOICE s
        LEFT JOIN CUSTOMER c ON c.DOC_NAME = s.CUSTOMER
        GROUP BY 1, 2, 3, 4, 5;
        """
    )

    # 3. Ingest 16 clean public macroeconomic/agriculture/budget CSV datasets from data-gov-in!
    dk.execute(
        """
        CREATE TABLE GOV_IN_DATASET_CATALOG (
            TABLE_NAME VARCHAR PRIMARY KEY,
            SOURCE_FILE VARCHAR,
            COLUMN_COUNT INTEGER,
            ROW_COUNT INTEGER
        );
        """
    )
    csv_dir = donor_root / "data-gov-in"
    ingested_gov_tables = 0
    if csv_dir.is_dir():
        csv_files = sorted(glob.glob(str(csv_dir / "**/*.csv"), recursive=True))
        used_names: set[str] = set()
        for cpath in csv_files:
            if ingested_gov_tables >= 16:
                break
            try:
                with open(cpath, "r", encoding="utf-8", errors="replace") as f:
                    reader = csv.reader(f)
                    header = next(reader, [])
                    if len(header) < 4 or len(header) > 20:
                        continue
                    if any("---" in h or not h.strip() for h in header[:3]):
                        continue
                    data_rows = []
                    for r in reader:
                        if len(r) == len(header) and any(cell.strip() for cell in r):
                            data_rows.append(r)
                        if len(data_rows) >= 250:
                            break
                    if len(data_rows) < 12:
                        continue
            except Exception:
                continue

            stem = re.sub(r"[^A-Z0-9]+", "_", Path(cpath).stem.upper()).strip("_")
            tname = f"GOV_IN_{stem[:38]}".rstrip("_")
            if tname in used_names:
                continue
            used_names.add(tname)

            clean_cols: list[str] = []
            seen_cols: set[str] = set()
            for idx, h in enumerate(header, start=1):
                cname = re.sub(r"[^A-Z0-9]+", "_", h.upper()).strip("_")[:40]
                if not cname or cname[0].isdigit():
                    cname = f"COL_{idx}_{cname}"[:40]
                if cname in seen_cols:
                    cname = f"{cname}_{idx}"
                seen_cols.add(cname)
                clean_cols.append(cname)

            col_defs = ", ".join(f'"{c}" VARCHAR' for c in clean_cols)
            dk.execute(f'CREATE TABLE "{tname}" ({col_defs})')
            placeholders = ", ".join(["?"] * len(clean_cols))
            dk.executemany(f'INSERT INTO "{tname}" VALUES ({placeholders})', data_rows)
            dk.execute(
                "INSERT INTO GOV_IN_DATASET_CATALOG VALUES (?, ?, ?, ?)",
                (tname, Path(cpath).name, len(clean_cols), len(data_rows)),
            )
            ingested_gov_tables += 1

    dk.execute(
        """
        CREATE VIEW VW_LAKEHOUSE_EXEC_PNL AS
        SELECT
            MONTH_START,
            COMPANY,
            ROUND(SUM(CASE WHEN ROOT_TYPE = 'Income' THEN TOTAL_CREDIT - TOTAL_DEBIT ELSE 0 END), 2) AS REVENUE,
            ROUND(SUM(CASE WHEN ROOT_TYPE = 'Expense' THEN TOTAL_DEBIT - TOTAL_CREDIT ELSE 0 END), 2) AS EXPENSE,
            ROUND(
                SUM(CASE WHEN ROOT_TYPE = 'Income' THEN TOTAL_CREDIT - TOTAL_DEBIT ELSE 0 END)
                - SUM(CASE WHEN ROOT_TYPE = 'Expense' THEN TOTAL_DEBIT - TOTAL_CREDIT ELSE 0 END),
                2
            ) AS NET_OPERATING_INCOME
        FROM MART_GL_MONTHLY
        GROUP BY MONTH_START, COMPANY
        ORDER BY MONTH_START, COMPANY;
        """
    )

    counts = {
        t: dk.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("COMPANY", "ACCOUNT", "CUSTOMER", "ITEM", "SALES_INVOICE", "GL_ENTRY", "MART_GL_MONTHLY", "MART_REVENUE_COHORTS", "GOV_IN_DATASET_CATALOG")
    }
    counts["INGESTED_GOV_IN_TABLES"] = ingested_gov_tables
    dk.close()
    return counts


def register_polyglot_endpoints(
    sqlite_path: Path, duckdb_path: Path, user_email: str = "cdeadmin@localhost"
) -> dict[str, dict[str, str]]:
    """Idempotently register SQLite Edge and DuckDB Lakehouse endpoints in cdeadmin.db."""
    if str(WEB_DIR) not in sys.path:
        sys.path.insert(0, str(WEB_DIR))
    os.environ.setdefault("PGADMIN_SERVER_MODE", "OFF")
    builtins.SERVER_MODE = os.environ["PGADMIN_SERVER_MODE"] != "OFF"

    import config  # noqa: E402
    from pgadmin import create_app  # noqa: E402

    app = create_app(config.APP_NAME + "-polyglot-registration")
    with app.app_context():
        from pgadmin.cdeadmin.endpoints import (
            provider_route_options,
            registration_profiles,
        )
        from pgadmin.model import (
            EndpointDatabaseTarget,
            EndpointProfile,
            Preferences,
            Server,
            ServerGroup,
            User,
            UserPreference,
            db,
        )

        user = User.query.filter_by(email=user_email).first() or User.query.first()
        if user is None:
            raise RuntimeError("No CDEadmin user found in cdeadmin.db")

        group = (
            ServerGroup.query.filter_by(user_id=user.id)
            .order_by(ServerGroup.id)
            .first()
        )
        if group is None:
            group = ServerGroup(user_id=user.id, name="Servers")
            db.session.add(group)
            db.session.flush()

        registrations = {
            item["profile_id"]: item for item in registration_profiles()
        }

        specs = [
            {
                "key": "sqlite",
                "profile_id": "sqlite-native",
                "name": "SQLite 3.53 — Frappe Books & Retail POS Edge",
                "database": str(sqlite_path.resolve()),
            },
            {
                "key": "duckdb",
                "profile_id": "duckdb-native",
                "name": "DuckDB — Frappe & Public Data Lakehouse",
                "database": str(duckdb_path.resolve()),
            },
        ]

        registered: dict[str, dict[str, str]] = {}
        for spec in specs:
            reg = registrations[spec["profile_id"]]
            db_file = spec["database"]
            route = {
                "database": db_file,
                "filesystem_root": str(Path(db_file).parent),
                "database_create_root": str(Path(db_file).parent),
            }
            route = provider_route_options(reg, {}, route)

            existing = (
                Server.query.join(EndpointProfile)
                .filter(
                    Server.user_id == user.id,
                    Server.name == spec["name"],
                    EndpointProfile.profile_id == reg["profile_id"],
                )
                .first()
            )
            if existing is None:
                server = Server(
                    user_id=user.id,
                    servergroup_id=group.id,
                    name=spec["name"],
                    host=None,
                    port=1,
                    maintenance_db=None,
                    username="embedded-process",
                    save_password=0,
                    shared=False,
                    use_ssh_tunnel=0,
                    tunnel_port=22,
                    tunnel_authentication=0,
                    tunnel_prompt_password=0,
                    tunnel_keep_alive=0,
                    kerberos_conn=False,
                    connection_params={},
                    tags=[{"text": "frappe-polyglot-suite", "color": "#2b6cb0"}],
                    comment="Frappe Enterprise Polyglot Showcase endpoint.",
                )
                server._cde_endpoint_registration = reg
                server._cde_endpoint_route_configuration = route
                db.session.add(server)
                db.session.flush()
            else:
                server = existing

            endpoint = server.endpoint_profile
            target = next(
                (t for t in endpoint.database_targets if t.database == db_file),
                None,
            )
            for t in endpoint.database_targets:
                t.active = False
            if target is None:
                target = EndpointDatabaseTarget(
                    id=str(uuid.uuid4()),
                    endpoint_id=endpoint.id,
                    display_name=Path(db_file).name,
                    database=db_file,
                    configuration="{}",
                    active=True,
                )
                db.session.add(target)
                db.session.flush()
            else:
                target.display_name = Path(db_file).name
                target.active = True

            endpoint.routes[0].configuration = json.dumps(
                route, sort_keys=True, separators=(",", ":")
            )
            endpoint.profile_generation = str(uuid.uuid4())
            registered[spec["key"]] = {
                "server_id": str(server.id),
                "endpoint_id": str(endpoint.id),
                "target_id": str(target.id),
                "database": db_file,
            }

        # Ensure connector preferences are visible in Data Navigator
        for pref in Preferences.query.filter(
            Preferences.name.like("show_connector_%")
        ).all():
            cur_pref = UserPreference.query.filter_by(
                pid=pref.id, uid=user.id
            ).first()
            if cur_pref is None:
                db.session.add(
                    UserPreference(pid=pref.id, uid=user.id, value="True")
                )
            else:
                cur_pref.value = "True"

        db.session.commit()
        return registered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-root", type=Path, default=DEFAULT_DONOR_ROOT)
    parser.add_argument("--fb-host", default=DEFAULT_FB_HOST)
    parser.add_argument("--fb-port", type=int, default=DEFAULT_FB_PORT)
    parser.add_argument("--fb-db", default=DEFAULT_FB_DB)
    parser.add_argument("--fb-user", default=DEFAULT_FB_USER)
    parser.add_argument("--fb-password", default=DEFAULT_FB_PASSWORD)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--sqlite-path", type=Path, default=DEFAULT_SQLITE_EDGE)
    parser.add_argument("--duckdb-path", type=Path, default=DEFAULT_DUCKDB_LAKEHOUSE)
    args = parser.parse_args()

    fb_counts = expand_firebird_timeseries(
        args.donor_root,
        fb_host=args.fb_host,
        fb_port=args.fb_port,
        fb_db=args.fb_db,
        fb_user=args.fb_user,
        fb_password=args.fb_password,
        container=args.container,
    )
    sqlite_counts = build_sqlite_edge_database(args.sqlite_path)
    duckdb_counts = build_duckdb_lakehouse(
        args.duckdb_path,
        args.donor_root,
        fb_host=args.fb_host,
        fb_port=args.fb_port,
        fb_db=args.fb_db,
        fb_user=args.fb_user,
        fb_password=args.fb_password,
    )
    endpoints = register_polyglot_endpoints(args.sqlite_path, args.duckdb_path)

    print(
        json.dumps(
            {
                "firebird_counts": fb_counts,
                "firebird_key_table_total": sum(fb_counts.values()),
                "sqlite_edge_counts": sqlite_counts,
                "duckdb_lakehouse_counts": duckdb_counts,
                "registered_endpoints": endpoints,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
