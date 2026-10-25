#!/usr/bin/env python3
"""Generate the PostgreSQL ui_descriptors forms from the pgAdmin BaseUISchema
field lists (transcribed from the *.ui.js sources; see each form's notes).

PostgreSQL's workflow is legacy_preserved, so its forms cannot be dumped from a
provider contract the way tools/draft_ui_descriptors.py does for the other
engines. This script holds the transcription so it can be regenerated when a
*.ui.js schema changes. Usage: python3 tools/draft_postgresql_descriptors.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'web/pgadmin/cdeadmin/ui_descriptors/postgresql/forms'
SRC = 'web/pgadmin/browser/server_groups/servers/'

TAB_ORDER = ["General", "Definition", "Columns", "Constraints", "Indexes", "Triggers",
             "Parameters", "Partitions", "Options", "Engine", "Security", "Dependencies",
             "Statistics", "Data", "SQL", "Membership", "Privileges", "Connection",
             "Authentication", "SSL/TLS", "Advanced", "Tags"]


def f(field_id, label, control, tab=None, **kw):
    d = {"field_id": field_id, "label": label, "control": control}
    if tab:
        d["tab"] = tab
    for k, v in kw.items():
        if v is None:
            continue
        d[k] = v
    return d


def opts(*pairs):
    return [{"value": v, "label": l} for v, l in pairs]


def vmin(v):
    return {"minimum": v}


def when(field, equals=None, in_=None, truthy=None):
    d = {"field": field}
    if equals is not None:
        d["equals"] = equals
    if in_ is not None:
        d["in"] = in_
    if truthy is not None:
        d["truthy"] = truthy
    return d


ALTER = ["alter"]
CREATE = ["create"]
PROPS_HELP = "Read-only property shown by pgAdmin in properties mode only."


def props(field_id, label, control="text", tab=None, **kw):
    """pgAdmin mode ['properties'] only: read-only, alter only."""
    kw.setdefault("help", PROPS_HELP)
    return f(field_id, label, control, tab, readonly=True, modes=ALTER, **kw)


def seclabels(field_id="seclabels", tab="Security", **kw):
    kw.setdefault("version", vmin("9.2"))
    return f(field_id, "Security labels", "grid", tab, native_keyword="SECURITY LABEL",
             columns=[f("provider", "Provider", "text"),
                      f("label", "Security label", "text", required=True)], **kw)


def privileges(field_id, tab, kind, codes, label="Privileges", **kw):
    kw.setdefault("help", "Privilege codes accepted by the backend: %s. Grantee list comes from the role catalog "
                  "plus PUBLIC; grantor is read-only and defaults to the connected user." % ", ".join(codes))
    return f(field_id, label, "privileges", tab, native_keyword="GRANT",
             columns=[
                 f("grantee", "Grantee", "reference", reference_kind="role", required=True),
                 f("privileges", "Privileges", "multiselect", required=True,
                   option_values_path=["dialect", "privileges", kind]),
                 f("grantor", "Grantor", "reference", reference_kind="role", readonly=True),
             ], **kw)


def variables(field_id, tab, keys, label="Parameters", **kw):
    cols = [f("name", "Name", "select", required=True, option_values_path=["catalog", "configuration_parameters"],
              help="pgAdmin loads the list from the node's vopts endpoint (pg_settings); the value cell type follows "
                   "the parameter's vartype (bool/enum/integer/real/string)."),
            f("value", "Value", "text", required=True)]
    if "database" in keys:
        cols.append(f("database", "Database", "reference", reference_kind="database"))
    if "role" in keys:
        cols.append(f("role", "Role", "reference", reference_kind="role"))
    return f(field_id, label, "grid", tab, native_keyword="ALTER ... SET", columns=cols, **kw)


def write(family, kinds, fields, notes, gaps, omitted=None, variant=None):
    skel = json.loads((OUT.parent.parent / "families" / f"{family}.family.json").read_text())
    order = {t["tab"]: i for i, t in enumerate(skel["tabs"])}
    fields = sorted(fields, key=lambda x: order[x["tab"]])  # stable: keeps source order inside a tab
    doc = {
        "schema": "cdeadmin.ui-form.v1",
        "engine": "postgresql",
        "family": family,
        "resource_kinds": kinds,
    }
    if variant:
        doc["variant"] = variant
    doc.update({
        "status": "draft",
        "engine_tab_title": "PostgreSQL",
        "omitted_tabs": omitted or [],
        "gaps": gaps,
        "fields": fields,
        "notes": notes,
    })
    path = OUT / f"{family}.form.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(family, len(fields), sorted({x['tab'] for x in fields}, key=lambda t: order[t]))


LEGACY = ("Fields map 1:1 onto the legacy pgAdmin dialog (workflow legacy_preserved): field ids are the "
          "BaseUISchema ids and are served by the existing SQL templates. ")

# ---------------------------------------------------------------- server
CONN_PARAMS = [
    ('hostaddr', 'Host address'), ('passfile', 'Password file'), ('channel_binding', 'Channel binding'),
    ('connect_timeout', 'Connection timeout (seconds)'), ('client_encoding', 'Client encoding'),
    ('options', 'Options'), ('application_name', 'Application name'),
    ('fallback_application_name', 'Fallback application name'), ('keepalives', 'Keepalives'),
    ('keepalives_idle', 'Keepalives idle (seconds)'), ('keepalives_interval', 'Keepalives interval (seconds)'),
    ('keepalives_count', 'Keepalives count'), ('tcp_user_timeout', 'TCP user timeout (milliseconds)'),
    ('tty', 'TTY'), ('replication', 'Replication'), ('gssencmode', 'GSS encmode'), ('sslmode', 'SSL mode'),
    ('sslcompression', 'SSL compression?'), ('sslcert', 'Client certificate'),
    ('sslkey', 'Client certificate key'), ('sslpassword', 'SSL password'), ('sslrootcert', 'Root certificate'),
    ('sslcrl', 'Certificate revocation list'), ('sslcrldir', 'Certificate revocation list directory'),
    ('sslsni', 'Server name indication'), ('requirepeer', 'Require peer'),
    ('ssl_min_protocol_version', 'SSL min protocol version'), ('ssl_max_protocol_version', 'SSL max protocol version'),
    ('krbsrvname', 'Kerberos service name'), ('gsslib', 'GSS library'),
    ('target_session_attrs', 'Target session attribute'), ('load_balance_hosts', 'Load balance hosts'),
    ('gssdelegation', 'GSS delegation?'), ('require_auth', 'Require authentication'),
    ('sslnegotiation', 'SSL negotiation'), ('sslkeylogfile', 'SSL Key Logfile'),
    ('min_protocol_version', 'Min protocol version'), ('max_protocol_version', 'Max protocol version'),
    ('oauth_issuer', 'OAuth issuer'), ('oauth_client_id', 'OAuth client id'),
    ('oauth_client_secret', 'OAuth client secret'), ('oauth_scope', 'OAuth scope'),
]
SSH = "SSH tunnel"
server_fields = [
    props("id", "ID", "number", "Connection"),
    f("name", "Name", "text", "Connection", required=True),
    f("gid", "Server group", "select", "Connection", option_values_path=["catalog", "server_groups"],
      help="Options are the pgAdmin server groups; hidden when registering through an engine profile."),
    f("cde_profile_id", "Engine / interface profile", "select", "Connection", required=True,
      option_values_path=["catalog", "endpoint_profiles"], modes=CREATE,
      help="Select the native interface used by this endpoint. Engines with multiple interfaces expose each "
           "interface as a separate protocol-owned profile. Changing it resets port, connect/verify switches and "
           "route defaults (depChange not expressible here)."),
    f("cde_registration_intent", "Registration action", "text", "Connection", modes=CREATE,
      help="Hidden field set by the registration workflow (endpoint / create_database / register_existing)."),
    props("server_owner", "Shared Server Owner", "text", "Connection", group="Sharing"),
    props("server_type", "Server type", "select", "Connection", option_values_path=["catalog", "supported_servers"]),
    props("connected", "Connected?", "boolean", "Connection"),
    props("version", "Version", "text", "Connection"),
    f("bgcolor", "Background", "text", "Connection", group="Colour",
      help="Hex colour (pgAdmin 'color' control; no colour control in the descriptor set, see gaps). "
           "Disabled while connected."),
    f("fgcolor", "Foreground", "text", "Connection", group="Colour",
      help="Hex colour (pgAdmin 'color' control). Disabled while connected."),
    f("connect_now", "Connect now?", "boolean", "Connection", modes=CREATE, default=True,
      help="Shown for legacy_preserved profiles; provider_endpoint profiles show 'Verify endpoint now?' instead."),
    f("cde_verify_now", "Verify endpoint now?", "boolean", "Connection", modes=CREATE,
      help="Shown for provider_endpoint profiles only (visibility depends on the profile workflow, not on a field)."),
    f("shared", "Shared?", "boolean", "Connection", group="Sharing",
      help="Visible only to admins in pgAdmin server mode; read-only when the server is owned by another user."),
    f("shared_username", "Shared Username", "text", "Connection", group="Sharing",
      help="Visible only to admins in server mode; defaults to the username when sharing is switched on."),
    f("comment", "Comments", "text", "Connection"),
    props("connection_string", "Connection String", "text", "Connection"),
    f("host", "Host name/address", "text", "Connection", required=True,
      help="Hidden for embedded-file profiles. Either host or service must be given. Changing it on a connected "
           "server requires disconnect/reconnect."),
    f("port", "Port", "number", "Connection", required=True, min=1, max=65535, default=5432,
      help="Hidden for embedded-file profiles."),
    f("db", "Database / file", "text", "Connection", default="postgres",
      help="Initial database used to establish the PostgreSQL connection. Use an existing database that this user "
           "can access. Read-only while connected or shared."),
    f("service", "Service", "text", "Connection",
      help="pg_service.conf service name; read-only while connected or shared."),
    f("username", "Username", "text", "Authentication", help="Hidden for embedded-file profiles."),
    f("kerberos_conn", "Kerberos authentication?", "boolean", "Authentication",
      help="When on, the password fields are disabled."),
    props("gss_authenticated", "GSS authenticated?", "boolean", "Authentication"),
    props("gss_encrypted", "GSS encrypted?", "boolean", "Authentication"),
    f("password", "Password", "password", "Authentication",
      help="In edit mode the password field is enabled only if Save Password is set to true. Hidden when the "
           "profile declares typed secret fields."),
    f("save_password", "Save password?", "boolean", "Authentication",
      help="Disabled when the pgAdmin configuration forbids saving passwords or Kerberos is on."),
    f("role", "Role", "text", "Authentication", native_keyword="SET ROLE",
      help="Read-only while connected."),
    f("use_ssh_tunnel", "Use SSH tunneling", "boolean", "Authentication", group=SSH,
      help="Disabled when the pgAdmin build has no SSH tunnel support; read-only while connected."),
    f("tunnel_host", "Tunnel host", "text", "Authentication", group=SSH, visible_when=when("use_ssh_tunnel", truthy=True)),
    f("tunnel_port", "Tunnel port", "number", "Authentication", group=SSH, max=65535, default=22,
      visible_when=when("use_ssh_tunnel", truthy=True)),
    f("tunnel_username", "Username", "text", "Authentication", group=SSH, visible_when=when("use_ssh_tunnel", truthy=True)),
    f("tunnel_authentication", "Authentication", "radio", "Authentication", group=SSH, default=False,
      options=opts((False, "Password"), (True, "Identity file")), visible_when=when("use_ssh_tunnel", truthy=True)),
    f("tunnel_identity_file", "Identity file", "file", "Authentication", group=SSH,
      visible_when=when("tunnel_authentication", equals=True)),
    f("tunnel_password", "Password", "password", "Authentication", group=SSH, modes=CREATE,
      visible_when=when("use_ssh_tunnel", truthy=True)),
    f("tunnel_prompt_password", "Prompt for identity file password?", "boolean", "Authentication", group=SSH,
      visible_when=when("tunnel_authentication", equals=True),
      help="Enable to be prompted for the identity file's passphrase at connection time, if the file is "
           "passphrase-protected. This setting applies only to identity-file authentication. When using password "
           "authentication for the SSH tunnel, leave the SSH password field empty to be prompted on connection."),
    f("save_tunnel_password", "Save password?", "boolean", "Authentication", group=SSH, modes=CREATE,
      visible_when=when("connect_now", truthy=True),
      help="Disabled when the pgAdmin configuration forbids saving tunnel passwords."),
    f("tunnel_keep_alive", "Keep alive (seconds)", "number", "Authentication", group=SSH, min=0, default=0,
      visible_when=when("use_ssh_tunnel", truthy=True)),
    f("db_res_type", "DB restriction type", "radio", "Advanced", default="databases",
      options=opts(("databases", "Databases"), ("sql", "SQL")), help="Read-only while connected or shared."),
    f("db_res", "DB restriction", "text", "Advanced",
      help="pgAdmin switches the control on db_res_type: a creatable multi-select of database names, or an SQL "
           "editor returning names. The descriptor exposes it as text (see gaps)."),
    f("passexec_cmd", "Password exec command", "text", "Advanced",
      help="The server hostname, port, and username can be passed as variables by using the placeholders "
           "%HOSTNAME%, %PORT%, and %USERNAME%, which will be replaced with the corresponding server connection "
           "information. Disabled when the server configuration forbids it."),
    f("passexec_expiration", "Password exec expiration (seconds)", "number", "Advanced",
      visible_when=when("passexec_cmd", truthy=True)),
    f("prepare_threshold", "Prepare threshold", "number", "Advanced",
      help="If it is set to 0, every query is prepared the first time it is executed. If it is set to blank, "
           "prepared statements are disabled on the connection."),
    f("post_connection_sql", "Post Connection SQL", "code", "Advanced", language="sql",
      help="Any query specified in the control below will be executed with autocommit mode enabled for each "
           "connection to any database on this server. Read-only while connected."),
    f("connection_params", "Connection Parameters", "grid", "Engine", group="libpq connection parameters",
      native_keyword="libpq keywords",
      help="libpq keywords (sslmode, connect_timeout, sslcert, ... see options). Defaults: sslmode=prefer, "
           "connect_timeout=10. Rows cannot be added or removed while connected. The value cell type follows the "
           "keyword's vartype (string/file/enum/integer/bool/password); version-gated keywords show a "
           "'Supported version >= N' placeholder.",
      columns=[
          f("name", "Name", "select", required=True, options=opts(*CONN_PARAMS)),
          f("keyword", "Keyword", "text", readonly=True, help="Mirrors name; sent to the backend."),
          f("value", "Value", "text", required=True),
      ]),
    f("tags", "Tags", "grid", "Tags",
      help="Maximum count comes from pgAdmin's max_server_tags_allowed; colour is random on add.",
      columns=[f("text", "Text", "text", required=True), f("color", "Color", "text")]),
]
write("server", ["server"], server_fields,
      LEGACY + "Source: " + SRC + "static/js/server.ui.js (ServerSchema, TagsSchema, getConnectionParameters) and "
      "static/js/variable.ui.js. pgAdmin groups: General->Connection (no General tab on the server family), "
      "Connection->Connection (host/port/db/service) and Authentication (username/password/role/kerberos), "
      "SSH Tunnel->Authentication, Advanced + Post Connection SQL->Advanced, Parameters->Engine (libpq keyword grid), "
      "Tags->Tags. Not a DDL object: no SQL tab.",
      gaps=[
          {"concept": "SSL/TLS tab fields (ssl_mode, ssl_cert, ssl_key, ssl_ca)",
           "reason": "pgAdmin stores sslmode/sslcert/sslkey/sslrootcert/sslcrl as rows of connection_params, not as "
                     "separate fields; splitting them out needs a backend change to how connection_params is saved.",
           "tracking": "ui_unified_design open decisions"},
          {"concept": "Colour picker for bgcolor/fgcolor",
           "reason": "pgAdmin uses a 'color' control; the descriptor control set has none, fields are typed text."},
          {"concept": "db_res dynamic control",
           "reason": "control switches between a creatable multi-select and an SQL editor on db_res_type; typed as text."},
          {"concept": "rolvaliduntil-style dynamic visibility of profile route/secret fields",
           "reason": "providerConnectionFields()/providerSecretFields() generate cde_route_*/cde_secret_* fields from "
                     "endpoint profiles at runtime; they belong to the provider_endpoint profiles, not to this form."},
          {"concept": "Connected-state read-only rules",
           "reason": "readonly/disabled depend on state.connected, isShared and current_user; not expressible as visible_when."},
      ],
      omitted=[{"tab": "SSL/TLS", "reason": "libpq SSL settings are rows of connection_params on the Engine tab (see gaps)."}])

# ---------------------------------------------------------------- database
LOCALE = "Locale"
db_fields = [
    f("name", "Database", "text", "General", required=True),
    props("did", "OID", "text", "General"),
    f("datoid", "OID", "number", "General", modes=CREATE, min=16384, version=vmin("15"), native_keyword="OID"),
    f("datowner", "Owner", "reference", "General", reference_kind="role", native_keyword="OWNER"),
    props("is_sys_obj", "System database?", "boolean", "General"),
    f("comments", "Comment", "text", "General", native_keyword="COMMENT ON DATABASE"),
    f("template", "Template", "select", "General", modes=CREATE, option_values_path=["catalog", "databases"],
      native_keyword="TEMPLATE"),
    f("encoding", "Encoding", "select", "Options", option_values_path=["dialect", "character_sets"],
      native_keyword="ENCODING", default="UTF8", help="Read-only after create."),
    f("spcname", "Tablespace", "select", "Options", option_values_path=["catalog", "tablespaces"], native_keyword="TABLESPACE"),
    f("datcollate", "Collation", "select", "Options", option_values_path=["catalog", "collations"],
      native_keyword="LC_COLLATE", visible_when=when("datlocaleprovider", equals="libc"), help="Read-only after create."),
    f("datctype", "Character type", "select", "Options", option_values_path=["catalog", "ctypes"],
      native_keyword="LC_CTYPE", visible_when=when("datlocaleprovider", equals="libc"), help="Read-only after create."),
    f("datconnlimit", "Connection limit", "number", "Options", min=-1, default=-1, native_keyword="CONNECTION LIMIT"),
    f("is_template", "Template?", "boolean", "Options", native_keyword="IS_TEMPLATE",
      help="Note: When the preferences setting 'show template databases' is set to false, then template databases "
           "won't be displayed in the object explorer. Read-only for system databases."),
    props("datallowconn", "Allow connections?", "boolean", "Options"),
    f("datstrategy", "Strategy", "select", "Engine", modes=CREATE, version=vmin("15"), native_keyword="STRATEGY",
      options=opts(("wal_log", "WAL Log"), ("file_copy", "File Copy"))),
    f("datlocaleprovider", "Locale Provider", "select", "Engine", group=LOCALE, version=vmin("15"),
      native_keyword="LOCALE_PROVIDER", default="libc",
      options=opts(("icu", "icu"), ("libc", "libc"), ("builtin", "builtin")),
      help="'builtin' is offered on PostgreSQL 17+. Read-only after create."),
    f("daticulocale", "ICU Locale", "select", "Engine", group=LOCALE, version=vmin("15"),
      option_values_path=["catalog", "icu_locales"], native_keyword="ICU_LOCALE",
      visible_when=when("datlocaleprovider", equals="icu"), help="Read-only after create."),
    f("daticurules", "ICU Rules", "text", "Engine", group=LOCALE, version=vmin("16"), native_keyword="ICU_RULES",
      visible_when=when("datlocaleprovider", equals="icu"), help="Read-only after create."),
    f("datbuiltinlocale", "Builtin Locale", "select", "Engine", group=LOCALE, version=vmin("17"),
      option_values_path=["catalog", "builtin_locales"], native_keyword="BUILTIN_LOCALE",
      visible_when=when("datlocaleprovider", equals="builtin"), help="Required when the provider is builtin. Read-only after create."),
    props("datcollversion", "Collation Version", "text", "Engine", group=LOCALE, version=vmin("15")),
    f("schema_res", "Schema restriction", "multiselect", "Engine", group="Browser",
      help="pgAdmin-side list of schema names shown in the tree (creatable, free text). Note: Changes to the schema "
           "restriction will require the Schemas node in the browser to be refreshed before they will be shown."),
    props("acl", "Privileges", "text", "Security"),
    props("tblacl", "Default TABLE privileges", "text", "Security", group="Default privileges"),
    props("seqacl", "Default SEQUENCE privileges", "text", "Security", group="Default privileges"),
    props("funcacl", "Default FUNCTION privileges", "text", "Security", group="Default privileges"),
    props("typeacl", "Default TYPE privileges", "text", "Security", group="Default privileges", version=vmin("9.2")),
    privileges("datacl", "Security", "database", ["C", "T", "c"]),
    seclabels(),
    privileges("deftblacl", "Security", "table", ["a", "r", "w", "d", "D", "x", "t", "m"],
               label="Default privileges: tables", group="Default privileges", modes=ALTER),
    privileges("defseqacl", "Security", "sequence", ["r", "w", "U"],
               label="Default privileges: sequences", group="Default privileges", modes=ALTER),
    privileges("deffuncacl", "Security", "function", ["X"],
               label="Default privileges: functions", group="Default privileges", modes=ALTER),
    privileges("deftypeacl", "Security", "type", ["U"],
               label="Default privileges: types", group="Default privileges", modes=ALTER, version=vmin("9.2")),
    variables("variables", "Parameters", ["name", "value", "role"]),
]
write("database", ["database"], db_fields,
      LEGACY + "Source: " + SRC + "databases/static/js/database.ui.js (DatabaseSchema, DefaultPrivSchema), "
      "static/js/variable.ui.js, static/js/sec_label.ui.js, static/js/privilege.ui.js. pgAdmin Definition fields are "
      "mapped by match: encoding/tablespace/collation/ctype/connection limit/template flag->Options, template->General, "
      "strategy and locale provider family->Engine; Default Privileges nested tab->Security group; Advanced "
      "(schema_res)->Engine; Parameters->Parameters.",
      gaps=[
          {"concept": "Privilege grid in table-like privileges for PG17 (code 'm' MAINTAIN)",
           "reason": "deftblacl uses getPrivilegesForTableAndLikeObjects(version): 'm' only on 17+; the descriptor "
                     "cannot version-gate a single option inside a multiselect."},
          {"concept": "Locale fields clear on provider change",
           "reason": "depChange resets datcollate/datctype/daticulocale/daticurules/datbuiltinlocale when "
                     "datlocaleprovider changes; visible_when hides them but does not clear the value."},
      ])

# ---------------------------------------------------------------- role
role_fields = [
    f("rolname", "Name", "text", "General", required=True),
    props("oid", "OID", "text", "General"),
    props("is_sys_obj", "System role?", "boolean", "General"),
    f("description", "Comments", "text", "General", native_keyword="COMMENT ON ROLE"),
    f("rolpassword", "Password", "password", "General", native_keyword="PASSWORD",
      help="pgAdmin asks to retype the password (retype: true)."),
    f("rolvaliduntil", "Account expires", "text", "General", native_keyword="VALID UNTIL",
      placeholder="No Expiry",
      help="Please note that if you leave this field blank, then the password will never expire. pgAdmin uses a "
           "date-time picker (24h); the descriptor set has no datetime control, so it is typed text (ISO timestamp)."),
    f("rolconnlimit", "Connection limit", "number", "General", min=-1, default=-1, native_keyword="CONNECTION LIMIT"),
    f("rolcanlogin", "Can login?", "boolean", "Privileges", native_keyword="LOGIN", default=False),
    f("rolsuper", "Superuser?", "boolean", "Privileges", native_keyword="SUPERUSER", default=False,
      help="Switching it on also sets Create roles, Create databases and Bypass RLS (pgAdmin depChange)."),
    f("rolcreaterole", "Create roles?", "boolean", "Privileges", native_keyword="CREATEROLE", default=False),
    f("rolcreatedb", "Create databases?", "boolean", "Privileges", native_keyword="CREATEDB", default=False),
    f("rolinherit", "Inherit rights from the parent roles?", "boolean", "Privileges", native_keyword="INHERIT", default=True),
    f("rolreplication", "Can initiate streaming replication and backups?", "boolean", "Privileges",
      native_keyword="REPLICATION", default=False, version=vmin("9.1")),
    f("rolbypassrls", "Bypass RLS?", "boolean", "Privileges", native_keyword="BYPASSRLS", default=False),
    f("rolmembership", "Member of", "grid", "Membership", native_keyword="GRANT role TO",
      help="Roles shown with a check mark have the WITH ADMIN OPTION set. In properties mode pgAdmin renders the same "
           "id as formatted text ('role [WITH ADMIN ...]').",
      columns=[
          f("role", "User/Role", "reference", reference_kind="role", required=True),
          f("admin", "WITH ADMIN", "boolean", default=False),
          f("inherit", "WITH INHERIT", "boolean", version=vmin("16"), default=False),
          f("set", "WITH SET", "boolean", version=vmin("16"), default=True),
      ]),
    f("rolmembers", "Members", "grid", "Membership", native_keyword="GRANT this TO",
      help="Roles that are members of this role; same columns and formatting as Member of.",
      columns=[
          f("role", "User/Role", "reference", reference_kind="role", required=True),
          f("admin", "WITH ADMIN", "boolean", default=False),
          f("inherit", "WITH INHERIT", "boolean", version=vmin("16"), default=False),
          f("set", "WITH SET", "boolean", version=vmin("16"), default=True),
      ]),
    variables("variables", "Engine", ["name", "value", "database"], label="Configuration parameters",
              group="Parameters"),
    seclabels(tab="Engine", group="Security"),
]
write("role", ["role", "privilege"], role_fields,
      LEGACY + "Source: " + SRC + "roles/static/js/role.ui.js (RoleSchema), static/js/membership.ui.js, "
      "static/js/variable.ui.js (keys name/value/database), static/js/sec_label.ui.js. pgAdmin groups: "
      "General/Definition->General, Privileges->Privileges, Membership->Membership; Parameters and Security have no "
      "canonical tab on the role family and sit on the Engine tab. Whole-form readOnly (user lacks superuser / "
      "createrole and is not editing itself) is a provider authorisation rule, not a field rule.",
      gaps=[
          {"concept": "Date-time picker for rolvaliduntil",
           "reason": "no datetime control in the descriptor set; typed text."},
          {"concept": "Skeleton Privileges tab grid (object grants) and system_privileges/administrator",
           "reason": "pgAdmin's role dialog has no object-grant grid; the 'privilege' resource_kind (variant grant) "
                     "is handled by the provider's grant wizard, not by role.ui.js. Only the role attribute switches "
                     "are listed here.", "tracking": "ui_unified_design open decisions"},
      ])

# ---------------------------------------------------------------- table
TABLE_PRIVS = ["a", "r", "w", "d", "D", "x", "t", "m"]


def idx_constraint_columns(unique):
    cols = [
        f("name", "Name", "text", help="Required in edit mode."),
        props("oid", "OID", "text"),
        props("is_sys_obj", "System unique constraint?" if unique else "System primary key?", "boolean"),
        f("comment", "Comment", "text", help="Enabled once the constraint has a name."),
        f("columns", "Columns", "multiselect", required=True, option_values_path=["draft", "columns"],
          help="Read-only once the constraint exists; disabled when an existing index is chosen."),
        f("include", "Include columns", "multiselect", version=vmin("11"), option_values_path=["draft", "columns"],
          native_keyword="INCLUDE"),
        f("spcname", "Tablespace", "select", option_values_path=["catalog", "tablespaces"], native_keyword="USING INDEX TABLESPACE"),
        f("index", "Index", "select", modes=CREATE, option_values_path=["catalog", "indexes"],
          native_keyword="USING INDEX", help="Only offered on an existing table (not inside table create)."),
        f("fillfactor", "Fill factor", "number", min=10, max=100, native_keyword="WITH (FILLFACTOR)",
          help="Disabled when an existing index is chosen."),
        f("condeferrable", "Deferrable?", "boolean", native_keyword="DEFERRABLE"),
        f("condeferred", "Deferred?", "boolean", native_keyword="INITIALLY DEFERRED",
          visible_when=when("condeferrable", truthy=True)),
    ]
    if unique:
        cols.append(f("indnullsnotdistinct", "NULLs not distinct?", "boolean", version=vmin("15"),
                      native_keyword="NULLS NOT DISTINCT"))
    return cols


FK_ACTIONS = opts(("a", "NO ACTION"), ("r", "RESTRICT"), ("c", "CASCADE"), ("n", "SET NULL"), ("d", "SET DEFAULT"))
partition_key_cols = [
    f("key_type", "Key type", "select", required=True, default="column",
      options=opts(("column", "Column"), ("expression", "Expression"))),
    f("pt_column", "Column", "select", option_values_path=["draft", "columns"], visible_when=when("key_type", equals="column")),
    f("expression", "Expression", "code", language="sql", visible_when=when("key_type", equals="expression")),
    f("collationame", "Collation", "select", option_values_path=["catalog", "collations"]),
    f("op_class", "Operator class", "select", option_values_path=["catalog", "operator_classes"]),
]
PARTITION_HELP = ("Create a table: multiple partitions can be created while creating a new partitioned table "
                  "(Operation switch disabled). Edit existing table: create/attach/detach partitions; attach picks from "
                  "the list of suitable tables. Default: stores rows that fall in no other partition. From/To/In: "
                  "values must be single-quoted; several partition key values are comma separated. From/To for range, "
                  "In for list, Modulus/Remainder for hash.")
table_fields = [
    f("name", "Name", "text", "General", required=True),
    props("oid", "OID", "text", "General"),
    f("relowner", "Owner", "reference", "General", reference_kind="role", required=True, native_keyword="OWNER"),
    f("schema", "Schema", "reference", "General", reference_kind="schema", required=True),
    props("is_sys_table", "System table?", "boolean", "General"),
    f("relpersistence", "Unlogged?", "boolean", "General", native_keyword="UNLOGGED",
      help="Corresponds to the family's table_type=unlogged variant. Read-only once the table exists."),
    f("description", "Comment", "text", "General", native_keyword="COMMENT ON TABLE"),
    f("columns", "Columns", "grid", "Columns", required=True, reorderable=True,
      help="Reorder is allowed in create mode only. Rows inherited from a parent table (inheritedfrom set) cannot be "
           "edited or deleted; adding is disabled while 'Of type' is set. Grid columns shown inline: name, cltype, "
           "attlen, attprecision, attnotnull, is_primary_key, defval; the rest open in the row editor.",
      columns=[
          f("name", "Name", "text", required=True),
          f("is_primary_key", "Primary key?", "boolean", default=False,
            help="Only shown while creating a table; toggling it maintains the Primary key constraint row."),
          props("attnum", "Position", "text"),
          f("cltype", "Data type", "select", required=True, option_values_path=["catalog", "column_types"],
            help="pgAdmin loads get_types; in edit mode the list is filtered to the column's edit_types "
                 "(implicit casts). Custom type selector not expressible (see gaps)."),
          f("inheritedid", "Inherited id", "text", help="Hidden; parent table OID sent to the backend."),
          f("inheritedfrom", "Inherited from table", "text", readonly=True,
            help="Only shown while creating a table."),
          f("inheritedfromtype", "Inherited from type", "text", help="Hidden tracking field (OF TYPE columns)."),
          f("inheritedfromtable", "Inherited from table", "text", help="Hidden tracking field (parent tables)."),
          f("original_defval", "Original Default", "text", help="Hidden; original DEFAULT from the composite type."),
          f("original_attnotnull", "Original NOT NULL", "boolean", help="Hidden; original NOT NULL from the composite type."),
          f("geometry", "Geometry Type", "select", option_values_path=["catalog", "geometry_types"],
            visible_when=when("cltype", in_=["geometry", "geography"])),
          f("srid", "SRID", "number", visible_when=when("cltype", in_=["geometry", "geography"])),
          f("attlen", "Length/Precision", "number",
            help="Enabled only for types with a length; min/max come from the type list (min_val/max_val)."),
          f("attprecision", "Scale", "number",
            help="Enabled only for types with a precision; PostgreSQL allows negative precision."),
          f("attcompression", "Compression", "select", version=vmin("14"), native_keyword="COMPRESSION",
            options=opts(("pglz", "PGLZ"), ("lz4", "LZ4")), help="Enabled for variable-length types only."),
          f("collspcname", "Collation", "select", option_values_path=["catalog", "collations"],
            native_keyword="COLLATE", help="Enabled only when the type is collatable."),
          f("attstattarget", "Statistics", "number", modes=ALTER, native_keyword="SET STATISTICS"),
          f("attstorage", "Storage", "select", native_keyword="SET STORAGE",
            options=opts(("p", "PLAIN"), ("m", "MAIN"), ("e", "EXTERNAL"), ("x", "EXTENDED"), ("d", "DEFAULT")),
            help="'DEFAULT' exists on PostgreSQL 16+; before 16 the field is only shown in edit mode."),
          f("defval", "Default", "text", native_keyword="DEFAULT",
            help="Disabled for serial types and when the column is identity/generated."),
          f("attnotnull", "Not NULL?", "boolean", default=False, native_keyword="NOT NULL",
            help="Forced on for identity columns."),
          f("colconstype", "Type", "radio", version=vmin("10"), default="n",
            options=opts(("n", "NONE"), ("i", "IDENTITY"), ("g", "GENERATED")),
            help="GENERATED needs PostgreSQL 12+ and cannot be applied to an existing column."),
          f("attidentity", "Identity", "select", version=vmin("10"), default="a",
            options=opts(("a", "ALWAYS"), ("d", "BY DEFAULT")), visible_when=when("colconstype", equals="i"),
            native_keyword="GENERATED ... AS IDENTITY"),
          f("seqincrement", "Increment", "number", min=1, visible_when=when("colconstype", equals="i")),
          f("seqstart", "Start", "number", visible_when=when("colconstype", equals="i")),
          f("seqmin", "Minimum", "number", visible_when=when("colconstype", equals="i")),
          f("seqmax", "Maximum", "number", visible_when=when("colconstype", equals="i")),
          f("seqcache", "Cache", "number", min=1, visible_when=when("colconstype", equals="i")),
          f("seqcycle", "Cycled", "boolean", visible_when=when("colconstype", equals="i")),
          f("genexpr", "Expression", "code", language="sql", version=vmin("12"),
            visible_when=when("colconstype", equals="g"), native_keyword="GENERATED ALWAYS AS ... STORED",
            help="Read-only once the column exists."),
          props("is_pk", "Primary key?", "boolean"),
          props("is_fk", "Foreign key?", "boolean"),
          props("is_inherited", "Inherited?", "boolean"),
          props("tbls_inherited", "Inherited from table(s)", "text"),
          props("is_sys_column", "System column?", "boolean"),
          f("description", "Comment", "text", native_keyword="COMMENT ON COLUMN"),
          f("attoptions", "Variables", "grid", native_keyword="SET (n_distinct)",
            columns=[f("name", "Name", "select", required=True,
                       options=opts(("n_distinct", "n_distinct"), ("n_distinct_inherited", "n_distinct_inherited"))),
                     f("value", "Value", "text", required=True)]),
          privileges("attacl", None, "column", ["a", "r", "w", "x"], modes=ALTER),
          seclabels(tab=None, version=vmin("9.1")),
      ]),
    f("primary_key", "Primary key", "grid", "Constraints", group="Primary key", native_keyword="PRIMARY KEY",
      help="At most one row; a row can be added once any column has a name. Disabled on partitioned tables before "
           "PostgreSQL 11.", columns=idx_constraint_columns(False)),
    f("foreign_key", "Foreign keys", "grid", "Constraints", group="Foreign keys", native_keyword="FOREIGN KEY",
      help="Rows can be added once any column has a name. Disabled on partitioned tables before PostgreSQL 11. "
           "Grid columns shown inline: name, columns, references_table_name.",
      columns=[
          f("name", "Name", "text"),
          props("oid", "OID", "text"),
          props("is_sys_obj", "System foreign key?", "boolean"),
          f("comment", "Comment", "text", help="Enabled once the constraint has a name."),
          f("condeferrable", "Deferrable?", "boolean", native_keyword="DEFERRABLE"),
          f("condeferred", "Deferred?", "boolean", native_keyword="INITIALLY DEFERRED",
            visible_when=when("condeferrable", truthy=True)),
          f("confmatchtype", "Match type", "radio", default=False, native_keyword="MATCH",
            options=opts((True, "FULL"), (False, "SIMPLE"))),
          f("convalidated", "Validated?", "boolean", native_keyword="NOT VALID",
            help="Read-only once an existing constraint is validated."),
          f("autoindex", "Auto FK index?", "boolean", default=True,
            help="Create mode only; forced off while creating the whole table (pgAdmin). Read-only when an index exists."),
          f("coveringindex", "Covering index", "text", visible_when=when("autoindex", truthy=True),
            help="Defaults to fki_<name>; required when Auto FK index is on."),
          f("references_table_name", "Referenced Table", "text", readonly=True,
            help="Hidden; joined from the column rows."),
          f("columns", "Columns", "grid", required=True,
            help="pgAdmin header form: Local column / References (table) / Referencing (column). Rows can only be "
                 "added or removed while the constraint is new; after the first row the referenced table is locked.",
            columns=[
                f("local_column", "Local", "select", required=True, option_values_path=["draft", "columns"]),
                f("references", "References", "reference", reference_kind="table", required=True),
                f("referenced", "Referenced", "select", required=True, option_values_path=["catalog", "columns"],
                  help="Columns of the referenced table (get_columns?tid=references)."),
                f("references_table_name", "Referenced Table", "text", readonly=True),
            ]),
          f("confupdtype", "On update", "select", default="a", options=FK_ACTIONS, native_keyword="ON UPDATE"),
          f("confdeltype", "On delete", "select", default="a", options=FK_ACTIONS, native_keyword="ON DELETE"),
      ]),
    f("check_constraint", "Check", "grid", "Constraints", group="Check", native_keyword="CHECK",
      help="Grid columns shown inline: name, consrc.",
      columns=[
          f("name", "Name", "text"),
          props("oid", "OID", "text"),
          props("is_sys_obj", "System check constraint?", "boolean"),
          f("comment", "Comment", "text", help="Enabled once the constraint has a name."),
          f("consrc", "Check", "code", language="sql", required=True, help="Read-only once the constraint exists."),
          f("connoinherit", "No inherit?", "boolean", version=vmin("9.2"), native_keyword="NO INHERIT",
            help="Read-only once the constraint exists."),
          f("convalidated", "Don't validate?", "boolean", version=vmin("9.2"), native_keyword="NOT VALID",
            help="Read-only once an existing constraint is validated."),
      ]),
    f("unique_constraint", "Unique", "grid", "Constraints", group="Unique", native_keyword="UNIQUE",
      help="Rows can be added once any column has a name. Disabled on partitioned tables before PostgreSQL 11.",
      columns=idx_constraint_columns(True)),
    f("exclude_constraint", "Exclude", "grid", "Constraints", group="Exclude", native_keyword="EXCLUDE",
      help="Rows can be added once any column has a name. Grid columns shown inline: name, columns, constraint.",
      columns=[
          f("name", "Name", "text"),
          props("oid", "OID", "text"),
          props("is_sys_obj", "System exclusion constraint?", "boolean"),
          f("comment", "Comment", "text", help="Enabled once the constraint has a name."),
          f("spcname", "Tablespace", "select", option_values_path=["catalog", "tablespaces"], native_keyword="USING INDEX TABLESPACE"),
          f("amname", "Access method", "select", option_values_path=["catalog", "index_access_methods"], native_keyword="USING",
            help="Changing it clears the column rows (pgAdmin confirms first)."),
          f("fillfactor", "Fill factor", "number", native_keyword="WITH (FILLFACTOR)"),
          f("condeferrable", "Deferrable?", "boolean", native_keyword="DEFERRABLE"),
          f("condeferred", "Deferred?", "boolean", native_keyword="INITIALLY DEFERRED",
            visible_when=when("condeferrable", truthy=True)),
          f("indconstraint", "Constraint", "code", language="sql", native_keyword="WHERE",
            help="Predicate; read-only once the constraint exists."),
          f("columns", "Columns/Expressions", "grid", required=True,
            help="pgAdmin header form: Is expression / Column / Expression. Operator list depends on the column type "
                 "(get_operator?col_type); operator classes depend on the access method.",
            columns=[
                f("is_exp", "Is expression", "boolean", default=False),
                f("column", "Col/Exp", "text", required=True,
                  help="Column name (picked from the draft columns) or the expression text."),
                f("oper_class", "Operator class", "select", option_values_path=["catalog", "operator_classes"]),
                f("order", "Order", "select", options=opts((True, "ASC"), (False, "DESC"))),
                f("nulls_order", "NULLs order", "select", options=opts((True, "FIRST"), (False, "LAST"))),
                f("operator", "Operator", "select", required=True, option_values_path=["catalog", "operators"]),
            ]),
          f("include", "Include columns", "multiselect", version=vmin("11"), option_values_path=["draft", "columns"],
            native_keyword="INCLUDE"),
      ]),
    f("is_partitioned", "Partitioned table?", "boolean", "Partitions", version=vmin("10"), default=False,
      native_keyword="PARTITION BY", help="Read-only once the table exists."),
    f("partition_type", "Partition Type", "select", "Partitions", modes=CREATE, version=vmin("10"), default="range",
      options=opts(("range", "Range"), ("list", "List"), ("hash", "Hash")),
      visible_when=when("is_partitioned", truthy=True), help="Hash needs PostgreSQL 11+."),
    f("partition_keys", "Partition Keys", "grid", "Partitions", modes=CREATE, version=vmin("10"),
      visible_when=when("is_partitioned", truthy=True), columns=partition_key_cols,
      help="Partition table supports two types of keys: Column (any column from the list) or Expression (e.g. "
           "extract(YEAR from saledate)). List partitioning accepts a single key. At least one key is required."),
    f("partition_scheme", "Partition Scheme", "text", "Partitions", modes=ALTER, readonly=True, version=vmin("10"),
      help="Existing PARTITION BY clause (pgAdmin note control)."),
    f("partitions", "Partitions", "grid", "Partitions", version=vmin("10"),
      visible_when=when("is_partitioned", truthy=True), help=PARTITION_HELP + " Deleting a row detaches the partition.",
      columns=[
          props("oid", "OID", "text"),
          f("is_attach", "Operation", "select", default=False, options=opts((True, "Attach"), (False, "Create")),
            help="Editable only when adding a partition to an existing table."),
          f("partition_name", "Name", "text", required=True,
            help="When attaching, pgAdmin offers the suitable tables (get_attach_tables) instead of free text."),
          f("amname", "Access Method", "select", version=vmin("12"), option_values_path=["catalog", "table_access_methods"],
            native_keyword="USING", help="Disabled when sub-partitioned; alterable only on PostgreSQL 15+."),
          f("is_default", "Default", "boolean", version=vmin("11"), native_keyword="DEFAULT",
            help="Range and list partitions only."),
          f("values_from", "From", "text", help="Range partitions; quoted literal(s)."),
          f("values_to", "To", "text", help="Range partitions; quoted literal(s)."),
          f("values_in", "In", "text", help="List partitions; comma separated quoted literals."),
          f("values_modulus", "Modulus", "number", help="Hash partitions."),
          f("values_remainder", "Remainder", "number", help="Hash partitions."),
          f("is_sub_partitioned", "Partitioned table?", "boolean", default=False,
            help="Not available when attaching."),
          f("sub_partition_type", "Partition Type", "select", default="range",
            options=opts(("range", "Range"), ("list", "List"), ("hash", "Hash")),
            visible_when=when("is_sub_partitioned", truthy=True)),
          f("sub_partition_keys", "Partition Keys", "grid", visible_when=when("is_sub_partitioned", truthy=True),
            columns=partition_key_cols),
          f("sub_partition_scheme", "Partition Scheme", "text", readonly=True, modes=ALTER),
      ]),
    f("spcname", "Tablespace", "select", "Options", option_values_path=["catalog", "tablespaces"],
      native_keyword="TABLESPACE", help="pg_global is excluded."),
    f("fillfactor", "Fill factor", "number", "Options", min=10, max=100, native_keyword="WITH (fillfactor)",
      help="Disabled for partitioned tables."),
    f("coll_inherits", "Inherited from table(s)", "multiselect", "Engine", group="Inheritance",
      option_values_path=["catalog", "tables"], native_keyword="INHERITS",
      help="Selecting a parent copies its columns into the Columns grid; disabled when 'Of type' is set or the table "
           "is partitioned. Properties mode shows the same id as text."),
    props("inherited_tables_cnt", "Inherited tables count", "text", "Engine", group="Inheritance"),
    props("relhassubclass", "Is inherited?", "boolean", "Engine", group="Inheritance"),
    f("typname", "Of type", "select", "Engine", group="Inheritance", option_values_path=["catalog", "composite_types"],
      native_keyword="OF", help="Disabled when inheriting from tables; changing it replaces the column definitions "
                                "(pgAdmin confirms first) and clears constraints and partition keys."),
    f("rlspolicy", "RLS Policy?", "boolean", "Engine", group="Row level security", version=vmin("9.6"),
      native_keyword="ENABLE ROW LEVEL SECURITY",
      help="Please check if any policy exists. If no policy exists for the table, a default-deny policy is used, "
           "meaning that no rows are visible or can be modified by other users."),
    f("forcerlspolicy", "Force RLS Policy?", "boolean", "Engine", group="Row level security", version=vmin("9.6"),
      native_keyword="FORCE ROW LEVEL SECURITY", visible_when=when("rlspolicy", truthy=True)),
    f("replica_identity", "Replica Identity", "text", "Engine", group="Replication", modes=ALTER,
      native_keyword="REPLICA IDENTITY"),
    f("amname", "Access Method", "select", "Engine", group="Storage", version=vmin("12"),
      option_values_path=["catalog", "table_access_methods"], native_keyword="USING",
      help="Disabled for partitioned tables; alterable only on PostgreSQL 15+."),
    f("toast_tuple_target", "Toast tuple target", "number", "Engine", group="Storage", min=128, version=vmin("11"),
      native_keyword="toast_tuple_target", help="Disabled for partitioned tables."),
    f("parallel_workers", "Parallel workers", "number", "Engine", group="Storage", version=vmin("9.6"),
      native_keyword="parallel_workers", help="Disabled for partitioned tables."),
    f("relhasoids", "Has OIDs?", "boolean", "Engine", group="Storage", native_keyword="WITH OIDS",
      help="Disabled on PostgreSQL 12+ (OIDs removed) and in catalogs."),
    props("conname", "Primary key", "text", "Engine", group="Storage"),
    props("vacuum_settings_str", "Storage settings", "text", "Engine", group="Storage"),
    f("like_relation", "Relation", "select", "Engine", group="Like", modes=CREATE,
      option_values_path=["catalog", "relations"], native_keyword="LIKE",
      help="Disabled when 'Of type' is set. The With ... switches reset when the relation is cleared."),
    f("like_default_value", "With default values?", "boolean", "Engine", group="Like", modes=CREATE,
      native_keyword="INCLUDING DEFAULTS", visible_when=when("like_relation", truthy=True)),
    f("like_constraints", "With constraints?", "boolean", "Engine", group="Like", modes=CREATE,
      native_keyword="INCLUDING CONSTRAINTS", visible_when=when("like_relation", truthy=True)),
    f("like_indexes", "With indexes?", "boolean", "Engine", group="Like", modes=CREATE,
      native_keyword="INCLUDING INDEXES", visible_when=when("like_relation", truthy=True)),
    f("like_storage", "With storage?", "boolean", "Engine", group="Like", modes=CREATE,
      native_keyword="INCLUDING STORAGE", visible_when=when("like_relation", truthy=True)),
    f("like_comments", "With comments?", "boolean", "Engine", group="Like", modes=CREATE,
      native_keyword="INCLUDING COMMENTS", visible_when=when("like_relation", truthy=True)),
    f("like_compression", "With compression?", "boolean", "Engine", group="Like", modes=CREATE, version=vmin("14"),
      native_keyword="INCLUDING COMPRESSION", visible_when=when("like_relation", truthy=True)),
    f("like_generated", "With generated?", "boolean", "Engine", group="Like", modes=CREATE, version=vmin("12"),
      native_keyword="INCLUDING GENERATED", visible_when=when("like_relation", truthy=True)),
    f("like_identity", "With identity?", "boolean", "Engine", group="Like", modes=CREATE,
      native_keyword="INCLUDING IDENTITY", visible_when=when("like_relation", truthy=True)),
    f("like_statistics", "With statistics?", "boolean", "Engine", group="Like", modes=CREATE,
      native_keyword="INCLUDING STATISTICS", visible_when=when("like_relation", truthy=True)),
    f("autovacuum_custom", "Custom auto-vacuum?", "boolean", "Engine", group="Autovacuum",
      help="Disabled for partitioned tables."),
    f("autovacuum_enabled", "Autovacuum Enabled?", "radio", "Engine", group="Autovacuum", default="x",
      options=opts(("x", "Not set"), ("t", "Yes"), ("f", "No")), native_keyword="autovacuum_enabled",
      visible_when=when("autovacuum_custom", truthy=True)),
    f("vacuum_table", "Autovacuum settings", "grid", "Engine", group="Autovacuum",
      help="Fixed rows (one per autovacuum_* storage parameter from the vacuum settings endpoint); only Value is editable.",
      visible_when=when("autovacuum_custom", truthy=True),
      columns=[f("label", "Label", "text", readonly=True), f("value", "Value", "number"),
               f("setting", "Default", "text", readonly=True)]),
    f("toast_autovacuum", "Custom auto-vacuum?", "boolean", "Engine", group="TOAST autovacuum",
      help="Enabled when the table has a TOAST table (or while creating)."),
    f("toast_autovacuum_enabled", "Autovacuum Enabled?", "radio", "Engine", group="TOAST autovacuum", default="x",
      options=opts(("x", "Not set"), ("t", "Yes"), ("f", "No")), native_keyword="toast.autovacuum_enabled",
      visible_when=when("toast_autovacuum", truthy=True)),
    f("vacuum_toast", "TOAST autovacuum settings", "grid", "Engine", group="TOAST autovacuum",
      help="Fixed rows (toast.autovacuum_* parameters); only Value is editable.",
      visible_when=when("toast_autovacuum", truthy=True),
      columns=[f("label", "Label", "text", readonly=True), f("value", "Value", "number"),
               f("setting", "Default", "text", readonly=True)]),
    props("relacl_str", "Privileges", "text", "Security"),
    privileges("relacl", "Security", "table", TABLE_PRIVS),
    seclabels(version=vmin("9.1")),
    props("reltuples", "Rows (estimated)", "text", "Statistics"),
    props("rows_cnt", "Rows (counted)", "text", "Statistics", help="Counted on demand (Count rows); shows 0 until then."),
]
write("table", ["table", "partition", "foreign-table"], table_fields,
      LEGACY + "Sources: " + SRC + "databases/schemas/tables/static/js/table.ui.js (TableSchema, ConstraintsSchema, "
      "LikeSchema), partition.utils.ui.js (PartitionKeysSchema, PartitionsSchema), columns/static/js/column.ui.js, "
      "constraints/index_constraint/static/js/{primary_key,unique_constraint}.ui.js, "
      "constraints/foreign_key/static/js/foreign_key.ui.js, constraints/check_constraint/static/js/check_constraint.ui.js, "
      "constraints/exclusion_constraint/static/js/exclusion_constraint.ui.js, static/js/vacuum.ui.js, "
      "static/js/privilege.ui.js, static/js/sec_label.ui.js. Mapping: General->General; Columns->Columns "
      "(coll_inherits->Engine); Constraints nested tab->Constraints groups Primary key/Foreign keys/Check/Unique/Exclude; "
      "Partitions->Partitions; Advanced: spcname/fillfactor->Options, typname/coll_inherits/rlspolicy/replica identity/"
      "access method/toast/parallel/oids/Like->Engine, reltuples/rows_cnt->Statistics; Parameters (vacuum nested "
      "tab)->Engine groups Autovacuum/TOAST autovacuum; Security->Security. The partition resource kind "
      "(partitions/static/js/partition.ui.js) is the same field set minus Columns/Like/typname.",
      gaps=[
          {"concept": "Column data type selector",
           "reason": "pgAdmin's cltype select carries per-type length/precision ranges (min_val/max_val) and the "
                     "edit-mode cast filter (edit_types); the descriptor select cannot carry those and the hidden "
                     "min_val_attlen/max_val_attlen/min_val_attprecision/max_val_attprecision fields are omitted."},
          {"concept": "Foreign table variant (resource_kind foreign-table)",
           "reason": "foreign_tables/static/js/foreign_table.ui.js (server/options/columns) is a different field set and "
                     "was not transcribed into this form.", "tracking": "phase 5"},
          {"concept": "Cross-field synchronisation",
           "reason": "pgAdmin depChange keeps columns.is_primary_key, primary_key.columns, foreign_key/unique column "
                     "renames and partition key resets in sync, confirms before 'Of type' or access-method changes and "
                     "fetches inherited columns; none of this is expressible as visible_when."},
          {"concept": "Partition value editability by partition type",
           "reason": "values_from/to (range), values_in (list), values_modulus/remainder (hash) are enabled by the "
                     "parent's partition_type, not by a field of the row."},
          {"concept": "PG17 MAINTAIN privilege code 'm'",
           "reason": "only offered on 17+ by getPrivilegesForTableAndLikeObjects; a single multiselect option cannot be version-gated."},
          {"concept": "Partition note texts",
           "reason": "partition_key_note and partition_note are static notes; folded into help text."},
      ])

# ---------------------------------------------------------------- view
view_fields = [
    f("variant", "Variant", "select", "General", default="ordinary", required=True,
      options=opts(("ordinary", "View"), ("materialized", "Materialized view")),
      help="Selects view.ui.js (ordinary) or mview.ui.js (materialized) field set."),
    f("name", "Name", "text", "General", required=True),
    props("oid", "OID", "text", "General"),
    f("owner", "Owner", "reference", "General", reference_kind="role", native_keyword="OWNER"),
    f("schema", "Schema", "reference", "General", reference_kind="schema"),
    props("system_view", "System view?", "boolean", "General"),
    f("comment", "Comment", "text", "General", native_keyword="COMMENT ON VIEW"),
    f("security_barrier", "Security barrier?", "boolean", "Definition", version=vmin("9.2"),
      native_keyword="security_barrier", visible_when=when("variant", equals="ordinary")),
    f("security_invoker", "Security invoker?", "boolean", "Definition", version=vmin("15"),
      native_keyword="security_invoker", visible_when=when("variant", equals="ordinary")),
    f("check_option", "Check options", "select", "Definition", version=vmin("9.4"), default="no",
      options=opts(("no", "No"), ("local", "Local"), ("cascaded", "Cascaded")), native_keyword="WITH CHECK OPTION",
      visible_when=when("variant", equals="ordinary")),
    f("with_data", "With data?", "boolean", "Definition", native_keyword="WITH DATA",
      visible_when=when("variant", equals="materialized")),
    f("spcname", "Tablespace", "select", "Definition", option_values_path=["catalog", "tablespaces"],
      native_keyword="TABLESPACE", visible_when=when("variant", equals="materialized")),
    f("amname", "Access Method", "select", "Definition", version=vmin("12"),
      option_values_path=["catalog", "table_access_methods"], native_keyword="USING",
      visible_when=when("variant", equals="materialized"), help="Alterable only on PostgreSQL 15+."),
    f("fillfactor", "Fill factor", "number", "Definition", min=10, max=100, native_keyword="WITH (fillfactor)",
      visible_when=when("variant", equals="materialized")),
    f("toast_tuple_target", "Toast tuple target", "number", "Definition", min=128, max=8160, version=vmin("11"),
      native_keyword="toast_tuple_target", visible_when=when("variant", equals="materialized")),
    f("dependsonextensions", "Depends on extensions", "multiselect", "Definition", version=vmin("13"),
      option_values_path=["catalog", "extensions"], native_keyword="ALTER ... DEPENDS ON EXTENSION",
      visible_when=when("variant", equals="materialized")),
    props("vacuum_settings_str", "Storage settings", "text", "Definition",
          visible_when=when("variant", equals="materialized")),
    f("definition", "Code", "code", "Definition", language="sql", required=True, native_keyword="AS SELECT",
      help="Changing the column list of a view drops and re-creates it (pgAdmin warns); changing a materialized "
           "view's definition drops and re-creates it."),
    f("autovacuum_custom", "Custom auto-vacuum?", "boolean", "Engine", group="Autovacuum",
      visible_when=when("variant", equals="materialized")),
    f("autovacuum_enabled", "Autovacuum Enabled?", "radio", "Engine", group="Autovacuum", default="x",
      options=opts(("x", "Not set"), ("t", "Yes"), ("f", "No")), visible_when=when("autovacuum_custom", truthy=True)),
    f("vacuum_table", "Autovacuum settings", "grid", "Engine", group="Autovacuum",
      visible_when=when("autovacuum_custom", truthy=True),
      help="Fixed rows (autovacuum_* storage parameters); only Value is editable.",
      columns=[f("label", "Label", "text", readonly=True), f("value", "Value", "number"),
               f("setting", "Default", "text", readonly=True)]),
    f("toast_autovacuum", "Custom auto-vacuum?", "boolean", "Engine", group="TOAST autovacuum",
      visible_when=when("variant", equals="materialized")),
    f("toast_autovacuum_enabled", "Autovacuum Enabled?", "radio", "Engine", group="TOAST autovacuum", default="x",
      options=opts(("x", "Not set"), ("t", "Yes"), ("f", "No")), visible_when=when("toast_autovacuum", truthy=True)),
    f("vacuum_toast", "TOAST autovacuum settings", "grid", "Engine", group="TOAST autovacuum",
      visible_when=when("toast_autovacuum", truthy=True),
      help="Fixed rows (toast.autovacuum_* parameters); only Value is editable.",
      columns=[f("label", "Label", "text", readonly=True), f("value", "Value", "number"),
               f("setting", "Default", "text", readonly=True)]),
    props("acl", "Privileges", "text", "Security"),
    privileges("datacl", "Security", "table", TABLE_PRIVS),
    seclabels(),
]
write("view", ["view", "materialized-view"], view_fields,
      LEGACY + "Sources: " + SRC + "databases/schemas/views/static/js/view.ui.js (ViewSchema) and mview.ui.js "
      "(MViewSchema, variant materialized), static/js/vacuum.ui.js, static/js/privilege.ui.js, static/js/sec_label.ui.js. "
      "Mapping: General->General, Definition->Definition, Code->Definition (definition), mview Parameter nested tab "
      "(autovacuum)->Engine, Security->Security. The skeleton's Options fields (check_option, security_barrier, "
      "with_data) are kept on Definition to follow the pgAdmin dialog literally.",
      gaps=[
          {"concept": "Skeleton Columns tab (column aliases)",
           "reason": "pgAdmin has no column alias grid for views; aliases are part of the SQL definition."},
          {"concept": "PG17 MAINTAIN privilege code 'm'",
           "reason": "only offered on 17+ by getPrivilegesForTableAndLikeObjects."},
      ],
      omitted=[{"tab": "Columns", "reason": "pgAdmin edits view columns only through the SQL definition."}])

# ---------------------------------------------------------------- index
AM_OPTS = "Access method options"
index_fields = [
    f("name", "Name", "text", "General", required=True, help="Required in edit mode."),
    props("oid", "OID", "number", "General"),
    f("indisunique", "Unique?", "boolean", "General", native_keyword="UNIQUE",
      help="btree only; read-only once the index exists."),
    f("indconstraint", "Constraint", "code", "General", language="sql", native_keyword="WHERE",
      help="Partial index predicate; read-only once the index exists."),
    f("columns", "Columns/Expressions", "grid", "General", required=True,
      help="pgAdmin header form: Is expression / Column / Expression. Rows can be added or removed only while the "
           "index is new. Sort order and NULLs apply to btree only; operator classes are filtered by access method.",
      columns=[
          f("is_exp", "Is expression", "boolean", default=False, help="Hidden in the grid (shown as E/C)."),
          f("colname", "Col/Exp", "text", required=True),
          f("op_class", "Operator class", "select", option_values_path=["catalog", "operator_classes"]),
          f("sort_order", "Sort order", "select", default=False, options=opts((False, "ASC"), (True, "DESC"))),
          f("nulls", "NULLs", "select", default=False, options=opts((True, "FIRST"), (False, "LAST"))),
          f("collspcname", "Collation", "select", option_values_path=["catalog", "collations"]),
          f("statistics", "Statistics", "number", min=-1, max=10000, modes=ALTER,
            native_keyword="ALTER INDEX ... SET STATISTICS", help="Expression columns only, PostgreSQL 11+."),
      ]),
    props("indisvalid", "Valid?", "boolean", "General"),
    props("indisprimary", "Primary?", "boolean", "General"),
    props("is_sys_idx", "System index?", "boolean", "General"),
    f("description", "Comment", "text", "General", native_keyword="COMMENT ON INDEX",
      help="Enabled once the index has a name."),
    f("amname", "Access Method", "select", "Options", required=True,
      option_values_path=["catalog", "index_access_methods"], native_keyword="USING",
      help="Read-only once the index exists; changing it clears the column rows (pgAdmin confirms first)."),
    f("include", "Include columns", "multiselect", "Options", version=vmin("11"),
      option_values_path=["catalog", "columns"], native_keyword="INCLUDE",
      help="Read-only once the index exists."),
    f("fillfactor", "Fill factor", "number", "Options", min=10, max=100, native_keyword="WITH (fillfactor)",
      visible_when=when("amname", in_=["btree", "hash", "gist", "spgist"])),
    f("isconcurrent", "Concurrent build?", "boolean", "Options", modes=CREATE, native_keyword="CONCURRENTLY"),
    f("spcname", "Tablespace", "select", "Options", option_values_path=["catalog", "tablespaces"], native_keyword="TABLESPACE"),
    f("dependsonextensions", "Depends on extensions", "multiselect", "Engine", version=vmin("13"),
      option_values_path=["catalog", "extensions"], native_keyword="ALTER ... DEPENDS ON EXTENSION"),
    f("indisonly", "Only Table?", "boolean", "Engine", modes=CREATE, version=vmin("11"), native_keyword="ON ONLY",
      help="When enabled, the index will only be created on this table, not on its partitions. Enabled for "
           "partitioned tables only."),
    f("gin_pending_list_limit", "Gin pending list limit", "number", "Engine", group=AM_OPTS, min=64, max=2147483647,
      native_keyword="gin_pending_list_limit", visible_when=when("amname", equals="gin"),
      help="This value is specified in kilobytes."),
    f("pages_per_range", "Pages per range", "number", "Engine", group=AM_OPTS, native_keyword="pages_per_range",
      visible_when=when("amname", equals="brin"),
      help="Number of table blocks that make up one block range for each entry of a BRIN index."),
    f("buffering", "Buffering", "select", "Engine", group=AM_OPTS, native_keyword="buffering", default="auto",
      options=opts(("auto", "Auto"), ("on", "On"), ("off", "Off")), visible_when=when("amname", equals="gist")),
    f("deduplicate_items", "Deduplicate items?", "boolean", "Engine", group=AM_OPTS, version=vmin("13"),
      native_keyword="deduplicate_items", default=True, visible_when=when("amname", equals="btree")),
    f("fastupdate", "Fast update?", "boolean", "Engine", group=AM_OPTS, native_keyword="fastupdate", default=True,
      visible_when=when("amname", equals="gin")),
    f("autosummarize", "Autosummarize?", "boolean", "Engine", group=AM_OPTS, native_keyword="autosummarize",
      visible_when=when("amname", equals="brin")),
    f("indnullsnotdistinct", "NULLs not distinct?", "boolean", "Engine", version=vmin("15"),
      native_keyword="NULLS NOT DISTINCT", visible_when=when("indisunique", truthy=True),
      help="Read-only once the index exists."),
    f("indisclustered", "Clustered?", "boolean", "Engine", native_keyword="CLUSTER ON",
      help="Enabled once the index has a name."),
]
write("index", ["index"], index_fields,
      LEGACY + "Source: " + SRC + "databases/schemas/tables/indexes/static/js/index.ui.js (IndexSchema, "
      "IndexColHeaderSchema, IndexColumnSchema, WithSchema). Mapping by field match: name/unique/constraint(where)/"
      "columns/comment->General; access method/include/fillfactor/concurrent/tablespace->Options; With fieldset "
      "access-method options, only-table, extensions, nulls-not-distinct, clustered->Engine.",
      gaps=[
          {"concept": "Access-method dependent clearing",
           "reason": "pgAdmin depChange blanks fillfactor/buffering/fastupdate/... when amname changes and sets "
                     "nulls=FIRST when sort_order becomes DESC; visible_when only hides."},
          {"concept": "Skeleton 'table' field",
           "reason": "the owning table is the tree parent in pgAdmin, not a form field."},
      ])

# ---------------------------------------------------------------- routine
FN = when("variant", equals="function")
FP = when("variant", in_=["function", "procedure"])
AGG = when("variant", equals="aggregate")
routine_fields = [
    f("variant", "Variant", "select", "General", required=True, default="function",
      options=opts(("function", "Function"), ("procedure", "Procedure"), ("aggregate", "Aggregate")),
      help="function/procedure share FunctionSchema (procedure.js passes type procedure); aggregate uses the "
           "read-only AggregateSchema."),
    f("name", "Name", "text", "General", required=True, help="Aggregates are read-only in pgAdmin."),
    props("oid", "OID", "text", "General"),
    f("funcowner", "Owner", "reference", "General", reference_kind="role", required=True, native_keyword="OWNER",
      visible_when=FP),
    f("pronamespace", "Schema", "reference", "General", reference_kind="schema", required=True, visible_when=FP),
    f("owner", "Owner", "text", "General", readonly=True, visible_when=AGG),
    f("schema", "Schema", "text", "General", readonly=True, visible_when=AGG),
    props("sysfunc", "System function?", "boolean", "General", visible_when=FN),
    props("sysproc", "System procedure?", "boolean", "General", visible_when=when("variant", equals="procedure")),
    props("is_sys_obj", "System aggregate?", "boolean", "General", visible_when=AGG),
    f("description", "Comment", "text", "General", native_keyword="COMMENT ON"),
    props("pronargs", "Argument count", "text", "Definition", visible_when=FP),
    props("proargs", "Arguments", "text", "Definition", visible_when=FP),
    props("proargtypenames", "Signature arguments", "text", "Definition", visible_when=FP),
    f("customreturn", "Custom return type?", "boolean", "Definition", modes=CREATE, visible_when=FN,
      help="When on, the return type is typed as free text instead of picked from the type list."),
    f("prorettypename", "Return type", "select", "Definition", required=True, visible_when=FN,
      option_values_path=["catalog", "types"], native_keyword="RETURNS",
      help="Read-only once the function exists (shown as text in edit/properties). Free text when customreturn is on."),
    f("lanname", "Language", "select", "Definition", required=True, option_values_path=["catalog", "languages"],
      native_keyword="LANGUAGE", visible_when=FP, help="Procedures need PostgreSQL 11+."),
    f("dependsonextensions", "Depends on extensions", "multiselect", "Definition", version=vmin("13"),
      option_values_path=["catalog", "extensions"], native_keyword="ALTER ... DEPENDS ON EXTENSION", visible_when=FP),
    f("probin", "Object file", "text", "Definition", default="$libdir/", native_keyword="AS 'obj_file'",
      visible_when=when("lanname", equals="c"), help="Required for language c."),
    f("prosrc_c", "Link symbol", "text", "Definition", native_keyword="AS 'obj_file', 'link_symbol'",
      visible_when=when("lanname", equals="c"), help="Required for language c."),
    f("prosrc", "Code", "code", "Definition", language="plpgsql", required=True, visible_when=FP,
      help="Hidden for language c (object file + link symbol are used instead)."),
    f("arguments", "Arguments", "grid", "Parameters", group="Arguments", visible_when=FP,
      help="Rows can be added or removed only while the routine is new. Default is disabled for OUT/INOUT arguments.",
      columns=[
          f("argid", "Argument id", "text", help="Hidden."),
          f("argtype", "Data type", "select", required=True, option_values_path=["catalog", "types"]),
          f("argmode", "Mode", "select", default="IN",
            options=opts(("IN", "IN"), ("OUT", "OUT"), ("INOUT", "INOUT"), ("VARIADIC", "VARIADIC"))),
          f("argname", "Argument name", "text"),
          f("argdefval", "Default", "text"),
      ]),
    variables("variables", "Parameters", ["name", "value"], label="Configuration parameters",
              group="Configuration (SET)", visible_when=FP),
    f("provolatile", "Volatility", "select", "Options", native_keyword="VOLATILE | STABLE | IMMUTABLE",
      options=opts(("v", "VOLATILE"), ("s", "STABLE"), ("i", "IMMUTABLE")), visible_when=FP,
      help="For procedures only on EDB SPL 9.5+."),
    f("proretset", "Returns a set?", "boolean", "Options", native_keyword="RETURNS SETOF", visible_when=FN,
      help="Read-only once the function exists."),
    f("proisstrict", "Strict?", "boolean", "Options", native_keyword="STRICT", visible_when=FP),
    f("prosecdef", "Security of definer?", "boolean", "Options", native_keyword="SECURITY DEFINER", visible_when=FP),
    f("proiswindow", "Window?", "boolean", "Options", native_keyword="WINDOW", visible_when=FN,
      help="Read-only once the function exists."),
    f("proparallel", "Parallel", "select", "Options", version=vmin("9.6"), native_keyword="PARALLEL",
      options=opts(("u", "UNSAFE"), ("r", "RESTRICTED"), ("s", "SAFE")), visible_when=FP),
    f("procost", "Estimated cost", "number", "Options", native_keyword="COST", visible_when=FP),
    f("prorows", "Estimated rows", "number", "Options", native_keyword="ROWS", default=0,
      visible_when=when("proretset", truthy=True)),
    f("proleakproof", "Leak proof?", "boolean", "Options", version=vmin("9.2"), native_keyword="LEAKPROOF", visible_when=FP),
    f("prosupportfunc", "Support function", "select", "Options", version=vmin("12"), native_keyword="SUPPORT",
      option_values_path=["catalog", "support_functions"], visible_when=FN, help="Superuser only."),
    f("input_types", "Input types", "text", "Options", group="Aggregate", readonly=True, visible_when=AGG),
    f("state_type", "State type", "text", "Options", group="Aggregate", readonly=True, visible_when=AGG, native_keyword="STYPE"),
    f("state_func", "State function", "text", "Options", group="Aggregate", readonly=True, visible_when=AGG, native_keyword="SFUNC"),
    f("state_data_size", "State data size", "text", "Options", group="Aggregate", readonly=True, visible_when=AGG, native_keyword="SSPACE"),
    f("final_type", "Final type", "text", "Options", group="Aggregate", readonly=True, visible_when=AGG),
    f("final_func", "Final function", "text", "Options", group="Aggregate", readonly=True, visible_when=AGG, native_keyword="FINALFUNC"),
    f("final_func_modify", "Final function modify", "text", "Options", group="Aggregate", readonly=True, visible_when=AGG,
      version=vmin("11"), native_keyword="FINALFUNC_MODIFY"),
    f("final_extra_param", "Pass extra arguments to final function", "boolean", "Options", group="Aggregate",
      readonly=True, visible_when=AGG, native_keyword="FINALFUNC_EXTRA"),
    f("initial_val", "Initial condition", "text", "Options", group="Aggregate", readonly=True, visible_when=AGG, native_keyword="INITCOND"),
    f("moving_state_type", "State type", "text", "Options", group="Moving aggregate", readonly=True, visible_when=AGG, native_keyword="MSTYPE"),
    f("moving_state_func", "State function", "text", "Options", group="Moving aggregate", readonly=True, visible_when=AGG, native_keyword="MSFUNC"),
    f("moving_state_data_size", "State data size", "text", "Options", group="Moving aggregate", readonly=True, visible_when=AGG, native_keyword="MSSPACE"),
    f("moving_final_func", "Final function", "text", "Options", group="Moving aggregate", readonly=True, visible_when=AGG, native_keyword="MFINALFUNC"),
    f("moving_final_func_modify", "Final function modify", "text", "Options", group="Moving aggregate", readonly=True,
      visible_when=AGG, version=vmin("11"), native_keyword="MFINALFUNC_MODIFY"),
    f("moving_final_extra_param", "Pass extra arguments to final function", "boolean", "Options", group="Moving aggregate",
      readonly=True, visible_when=AGG, native_keyword="MFINALFUNC_EXTRA"),
    f("moving_inverse_func", "Inverse function", "text", "Options", group="Moving aggregate", readonly=True, visible_when=AGG, native_keyword="MINVFUNC"),
    f("moving_initial_val", "Initial condition", "text", "Options", group="Moving aggregate", readonly=True, visible_when=AGG, native_keyword="MINITCOND"),
    f("sort_oper", "Sort operator", "text", "Engine", group="Aggregate functions", readonly=True, visible_when=AGG, native_keyword="SORTOP"),
    f("combine_func", "Combine function", "text", "Engine", group="Aggregate functions", readonly=True, visible_when=AGG, native_keyword="COMBINEFUNC"),
    f("serialization_func", "Serialization function", "text", "Engine", group="Aggregate functions", readonly=True, visible_when=AGG, native_keyword="SERIALFUNC"),
    f("deserialization_func", "Deserialization function", "text", "Engine", group="Aggregate functions", readonly=True, visible_when=AGG, native_keyword="DESERIALFUNC"),
    props("proacl", "Privileges", "text", "Security", visible_when=FP),
    privileges("acl", "Security", "function", ["X"], visible_when=FP),
    seclabels(version=vmin("9.1"), visible_when=FN),
]
write("routine", ["function", "procedure", "aggregate"], routine_fields,
      LEGACY + "Sources: " + SRC + "databases/schemas/functions/static/js/function.ui.js (FunctionSchema, "
      "DefaultArgumentSchema; procedure.js reuses it with type procedure), databases/schemas/aggregates/static/js/"
      "aggregate.ui.js (AggregateSchema, all read-only), static/js/variable.ui.js (keys name/value), "
      "static/js/privilege.ui.js, static/js/sec_label.ui.js. Mapping: General->General; Definition->Definition except "
      "the arguments grid, which goes to the family's Parameters tab (the skeleton defines that tab as the argument "
      "grid); Code->Definition (prosrc); Options->Options; pgAdmin Parameters (SET variables)->Parameters group "
      "'Configuration (SET)'; Security->Security; aggregate Options/Moving Options->Options groups, Advanced->Engine. "
      "Variant-specific fields use visible_when on 'variant'.",
      gaps=[
          {"concept": "Parameters tab holds two grids",
           "reason": "pgAdmin's 'Parameters' group is SET configuration variables while the skeleton's Parameters tab is "
                     "the argument grid; both are listed on Parameters in separate groups. Decide whether variables "
                     "move to Options or Engine.", "tracking": "ui_unified_design open decisions"},
          {"concept": "Aggregate create/alter",
           "reason": "AggregateSchema is read-only in pgAdmin (no CREATE AGGREGATE dialog); every aggregate field is readonly."},
          {"concept": "EDB SPL rules",
           "reason": "isLessThan95ORNonSPL/isLessThan96ORNonSPL disable volatility/strict/cost/leakproof/parallel for "
                     "procedures unless EDB SPL; ppas is out of beta scope."},
          {"concept": "Return type control switch",
           "reason": "prorettypename is a select unless customreturn is on, then free text; typed select."},
      ])

# ---------------------------------------------------------------- trigger
TR = when("variant", equals="trigger")
EV = when("variant", equals="event")
trigger_fields = [
    f("variant", "Variant", "select", "General", required=True, default="trigger",
      options=opts(("trigger", "Table/view trigger"), ("event", "Event trigger")),
      help="trigger uses trigger.ui.js (TriggerSchema + EventSchema); event uses event_trigger.ui.js."),
    f("name", "Name", "text", "General", required=True),
    props("oid", "OID", "number", "General"),
    f("eventowner", "Owner", "reference", "General", reference_kind="role", native_keyword="OWNER", visible_when=EV),
    props("is_sys_trigger", "System trigger?", "boolean", "General", visible_when=TR),
    props("is_sys_obj", "System event trigger?", "boolean", "General", visible_when=EV),
    f("description", "Comment", "text", "General", native_keyword="COMMENT ON TRIGGER", visible_when=TR),
    f("comment", "Comment", "text", "General", native_keyword="COMMENT ON EVENT TRIGGER", visible_when=EV),
    f("fires", "Fires", "select", "General", group="Events", default="BEFORE", visible_when=TR,
      options=opts(("BEFORE", "BEFORE"), ("AFTER", "AFTER"), ("INSTEAD OF", "INSTEAD OF")),
      help="INSTEAD OF is offered for view triggers only. Forced to AFTER for constraint triggers; read-only once "
           "the trigger exists."),
    f("evnt_insert", "INSERT", "boolean", "General", group="Events", default=False, visible_when=TR,
      help="At least one event is required. Read-only once the trigger exists."),
    f("evnt_update", "UPDATE", "boolean", "General", group="Events", default=False, visible_when=TR),
    f("evnt_delete", "DELETE", "boolean", "General", group="Events", default=False, visible_when=TR),
    f("evnt_truncate", "TRUNCATE", "boolean", "General", group="Events", default=False,
      visible_when=when("is_row_trigger", equals=False), help="Statement-level triggers only."),
    f("columns", "Columns", "multiselect", "General", group="Events", option_values_path=["catalog", "columns"],
      native_keyword="UPDATE OF", visible_when=when("evnt_update", truthy=True),
      help="Read-only once the trigger exists."),
    f("whenclause", "When", "code", "General", group="Events", language="sql", native_keyword="WHEN",
      visible_when=TR, help="Read-only once the trigger exists."),
    f("is_enable_trigger", "Trigger enabled?", "select", "Definition", modes=ALTER, visible_when=TR,
      native_keyword="ENABLE / DISABLE TRIGGER",
      options=opts(("O", "Enable"), ("R", "Enable Replica"), ("A", "Enable Always"), ("D", "Disable")),
      help="Disabled for view triggers and catalogs."),
    f("is_row_trigger", "Row trigger?", "boolean", "Definition", default=True, native_keyword="FOR EACH ROW",
      visible_when=TR, help="Forced on for constraint triggers; off for partitioned tables before PostgreSQL 11; "
                            "read-only once the trigger exists."),
    f("is_constraint_trigger", "Constraint trigger?", "boolean", "Definition", native_keyword="CONSTRAINT TRIGGER",
      visible_when=TR, help="Not available on views or partitioned tables; read-only once the trigger exists."),
    f("tgdeferrable", "Deferrable?", "boolean", "Definition", native_keyword="DEFERRABLE",
      visible_when=when("is_constraint_trigger", truthy=True)),
    f("tginitdeferred", "Deferred?", "boolean", "Definition", native_keyword="INITIALLY DEFERRED",
      visible_when=when("tgdeferrable", truthy=True)),
    f("tfunction", "Trigger function", "select", "Definition", required=True, visible_when=TR,
      option_values_path=["catalog", "trigger_functions"], native_keyword="EXECUTE FUNCTION",
      help="pgAdmin loads get_triggerfunctions; read-only once the trigger exists."),
    f("tgargs", "Arguments", "text", "Definition", visible_when=TR, help="Read-only once the trigger exists."),
    f("enabled", "Trigger enabled?", "select", "Definition", visible_when=EV, native_keyword="ENABLE / DISABLE EVENT TRIGGER",
      options=opts(("O", "Enable"), ("D", "Disable"), ("R", "Replica"), ("A", "Always"))),
    f("eventfunname", "Trigger function", "select", "Definition", visible_when=EV,
      option_values_path=["catalog", "event_trigger_functions"], native_keyword="EXECUTE FUNCTION"),
    f("eventname", "Event", "select", "Definition", visible_when=EV, native_keyword="ON",
      options=opts(("DDL_COMMAND_START", "DDL COMMAND START"), ("DDL_COMMAND_END", "DDL COMMAND END"), ("SQL_DROP", "SQL DROP"))),
    f("when", "When TAG in", "code", "Definition", language="sql", visible_when=EV, native_keyword="WHEN TAG IN"),
    f("prosrc", "Code", "code", "Definition", language="plpgsql", visible_when=TR,
      help="Inline body; enabled only on EDB with trigger function 'Inline EDB-SPL' (ppas is out of beta scope)."),
    f("tgoldtable", "Old table", "text", "Engine", group="Transition tables", visible_when=TR,
      native_keyword="REFERENCING OLD TABLE AS",
      help="Create only, PostgreSQL 10+, table triggers only: AFTER, not a constraint trigger, exactly one of "
           "UPDATE/DELETE and no UPDATE column list."),
    f("tgnewtable", "New table", "text", "Engine", group="Transition tables", visible_when=TR,
      native_keyword="REFERENCING NEW TABLE AS",
      help="Create only, PostgreSQL 10+, table triggers only: AFTER, not a constraint trigger, exactly one of "
           "UPDATE/INSERT and no UPDATE column list."),
    seclabels(tab="Engine", group="Security", visible_when=EV),
]
write("trigger", ["trigger", "event-trigger"], trigger_fields,
      LEGACY + "Sources: " + SRC + "databases/schemas/tables/triggers/static/js/trigger.ui.js (TriggerSchema, "
      "EventSchema), databases/event_triggers/static/js/event_trigger.ui.js (EventTriggerSchema, variant event), "
      "static/js/sec_label.ui.js. Mapping: General->General; Events group->General (matches timing/events/columns/when); "
      "Definition->Definition; Code->Definition (prosrc); Transition->Engine; event trigger Security->Engine (no "
      "Security tab on the trigger family). Rules (tables/rules/static/js/rule.ui.js) are routed to engine_object in "
      "capabilities.json and are listed under gaps, not as a variant.",
      gaps=[
          {"concept": "Rewrite rules (rule.ui.js)",
           "reason": "fields name, oid, is_enable_rule (O/R/A/D), event (SELECT/INSERT/UPDATE/DELETE), do_instead, "
                     "condition (sql), statements (sql), system_rule, comment; capabilities.json maps kind 'rule' to "
                     "engine_object with no form, so it is not a variant here.", "tracking": "ui_unified_design open decisions"},
          {"concept": "Transition table enablement",
           "reason": "disableTransition() depends on fires, is_constraint_trigger, the three events and columns at once; "
                     "not expressible as a single visible_when."},
          {"concept": "View-vs-table context",
           "reason": "fires options (INSTEAD OF), is_constraint_trigger and is_enable_trigger depend on whether the "
                     "parent is a view; the parent is tree context, not a field."},
      ])

# ---------------------------------------------------------------- sequence
sequence_fields = [
    f("name", "Name", "text", "General", required=True),
    props("oid", "OID", "text", "General"),
    f("seqowner", "Owner", "reference", "General", reference_kind="role", native_keyword="OWNER"),
    f("schema", "Schema", "reference", "General", reference_kind="schema"),
    props("is_sys_obj", "System sequence?", "boolean", "General"),
    f("comment", "Comment", "text", "General", native_keyword="COMMENT ON SEQUENCE"),
    f("current_value", "Current value", "number", "General", modes=ALTER, native_keyword="RESTART WITH",
      help="Sets the sequence object's current value. The next nextval will return exactly the specified value, and "
           "sequence advancement commences with the following nextval."),
    f("increment", "Increment", "number", "General", native_keyword="INCREMENT BY"),
    f("start", "Start", "number", "General", native_keyword="START WITH"),
    f("minimum", "Minimum", "number", "General", native_keyword="MINVALUE"),
    f("maximum", "Maximum", "number", "General", native_keyword="MAXVALUE"),
    f("cache", "Cache", "number", "General", min=1, native_keyword="CACHE"),
    f("cycled", "Cycled", "boolean", "General", native_keyword="CYCLE"),
    f("relpersistence", "Unlogged?", "boolean", "Engine", version=vmin("15"), native_keyword="UNLOGGED"),
    f("owned_table", "Table", "reference", "Engine", group="Owned by", reference_kind="table", native_keyword="OWNED BY",
      help="The OWNED BY option causes the sequence to be associated with a specific table column, such that if that "
           "column (or its whole table) is dropped, the sequence will be automatically dropped as well. The specified "
           "table must have the same owner and be in the same schema as the sequence."),
    f("owned_column", "Column", "select", "Engine", group="Owned by", option_values_path=["catalog", "columns"],
      visible_when=when("owned_table", truthy=True), help="Columns of the selected table (get_columns?tid=owned_table)."),
    props("acl", "Privileges", "text", "Security"),
    privileges("relacl", "Security", "sequence", ["r", "w", "U"]),
    seclabels("securities"),
]
write("sequence", ["sequence"], sequence_fields,
      LEGACY + "Source: " + SRC + "databases/schemas/sequences/static/js/sequence.ui.js (SequenceSchema, "
      "OwnedBySchema), static/js/privilege.ui.js, static/js/sec_label.ui.js. Mapping by field match: Definition "
      "counters->General, Unlogged and Owned By->Engine, Security->Security. Security labels use the pgAdmin id "
      "'securities' (not 'seclabels') on this node.",
      gaps=[])

# ---------------------------------------------------------------- type
DOM = when("variant", equals="domain")
TYP = when("variant", in_=["composite", "enum", "range", "external", "shell", "multirange"])
COMP = when("variant", equals="composite")
ENUM = when("variant", equals="enum")
RNG = when("variant", equals="range")
EXT = when("variant", equals="external")
TYPE_CATEGORIES = opts(('A', 'Array types'), ('B', 'Boolean types'), ('C', 'Composite types'), ('D', 'Date/time types'),
                       ('E', 'Enum types'), ('G', 'Geometric types'), ('I', 'Network address types'),
                       ('N', 'Numeric types'), ('P', 'Pseudo-types'), ('S', 'String types'), ('T', 'Timespan types'),
                       ('U', 'User-defined types'), ('V', 'Bit-string types'), ('X', 'unknown type'))
EXTG = "External type"
type_fields = [
    f("variant", "Variant", "select", "General", required=True, default="composite",
      options=opts(("domain", "Domain"), ("composite", "Composite"), ("enum", "Enumeration"), ("external", "External"),
                   ("range", "Range"), ("shell", "Shell"), ("multirange", "Multirange")),
      help="domain uses domain.ui.js; the others use type.ui.js where typtype carries the same choice "
           "(c/e/b/r/p; m is shown for existing types only). Read-only once the type exists."),
    f("name", "Name", "text", "General", required=True),
    props("oid", "OID", "text", "General"),
    f("owner", "Owner", "reference", "General", reference_kind="role", native_keyword="OWNER", visible_when=DOM),
    f("basensp", "Schema", "reference", "General", reference_kind="schema", visible_when=DOM),
    f("typeowner", "Owner", "reference", "General", reference_kind="role", required=True, native_keyword="OWNER", visible_when=TYP),
    f("schema", "Schema", "reference", "General", reference_kind="schema", required=True, visible_when=TYP),
    props("sysdomain", "System domain?", "boolean", "General", visible_when=DOM),
    props("is_sys_type", "System type?", "boolean", "General", visible_when=TYP),
    f("description", "Comment", "text", "General", native_keyword="COMMENT ON"),
    f("typtype", "Type", "select", "General", visible_when=TYP, native_keyword="CREATE TYPE ... AS",
      options=opts(("c", "Composite"), ("e", "Enumeration"), ("b", "External"), ("r", "Range"), ("p", "Shell"), ("m", "Multirange")),
      help="Backend id for the variant (same choice as 'variant'); read-only once the type exists."),
    f("basetype", "Base type", "select", "General", required=True, option_values_path=["catalog", "types"],
      native_keyword="AS", visible_when=DOM, help="Read-only once the domain exists."),
    f("typlen", "Length", "number", "General", visible_when=when("variant", in_=["domain", "external"]),
      native_keyword="INTERNALLENGTH (external) / type modifier (domain)",
      help="Domain: enabled for base types with a length (range from the type list); external: internal length. "
           "Read-only once the type exists."),
    f("precision", "Precision", "number", "General", visible_when=DOM,
      help="Enabled for base types with a precision; read-only once the domain exists."),
    f("typdefault", "Default", "text", "General", native_keyword="DEFAULT",
      visible_when=when("variant", in_=["domain", "external"])),
    f("typnotnull", "Not NULL?", "boolean", "General", native_keyword="NOT NULL", visible_when=DOM),
    f("collname", "Collation", "select", "General", option_values_path=["catalog", "collations"], native_keyword="COLLATE",
      visible_when=when("variant", in_=["domain", "range"]),
      help="Domain: read-only once it exists. Range: enabled only when the subtype is collatable."),
    f("composite", "Composite Type", "grid", "General", group="Members", visible_when=COMP, native_keyword="AS (...)",
      help="Members are unique by name. Length/precision cells enable per type (same rules as table columns).",
      columns=[
          f("member_name", "Member Name", "text", required=True),
          f("type", "Type", "select", required=True, option_values_path=["catalog", "types"]),
          f("tlength", "Length/Precision", "number"),
          f("precision", "Scale", "number"),
          f("collation", "Collation", "select", option_values_path=["catalog", "collations"]),
      ]),
    f("enum", "Enumeration type", "grid", "General", group="Labels", visible_when=ENUM, reorderable=True,
      native_keyword="AS ENUM", help="Labels are unique; reorder and delete only while the type is new (ALTER TYPE ADD VALUE after).",
      columns=[f("label", "Label", "text", required=True)]),
    f("typname", "Subtype", "select", "General", group="Range", visible_when=RNG, option_values_path=["catalog", "types"],
      native_keyword="SUBTYPE", help="Read-only once the type exists."),
    f("opcname", "Subtype operator class", "select", "General", group="Range", visible_when=RNG,
      option_values_path=["catalog", "operator_classes"], native_keyword="SUBTYPE_OPCLASS",
      help="Filtered by the chosen subtype (get_subopclass). Read-only once the type exists."),
    f("rngcanonical", "Canonical function", "select", "General", group="Range", visible_when=RNG,
      option_values_path=["catalog", "functions"], native_keyword="CANONICAL",
      help="Candidates from get_canonical(name). Read-only once the type exists."),
    f("rngsubdiff", "Subtype diff function", "select", "General", group="Range", visible_when=RNG,
      option_values_path=["catalog", "functions"], native_keyword="SUBTYPE_DIFF",
      help="Candidates from get_stypediff(subtype, opclass). Read-only once the type exists."),
    f("rngmultirangetype", "Multirange type name", "text", "General", group="Range", visible_when=RNG, version=vmin("14"),
      native_keyword="MULTIRANGE_TYPE_NAME", help="Read-only once the type exists."),
    props("alias", "Alias", "text", "General", visible_when=TYP),
    props("member_list", "Members", "text", "General", visible_when=COMP),
    props("enum_list", "Labels", "text", "General", visible_when=ENUM),
    f("constraints", "Constraints", "grid", "Constraints", visible_when=DOM, native_keyword="CONSTRAINT ... CHECK",
      columns=[
          f("conname", "Name", "text"),
          f("consrc", "Check", "code", language="sql", required=True, help="Editable only while the constraint is new."),
          f("convalidated", "Validate?", "boolean", default=True, help="Read-only once an existing constraint is validated."),
      ]),
    f("typinput", "Input function", "select", "Engine", group=EXTG, visible_when=EXT, required=True,
      option_values_path=["catalog", "functions"], native_keyword="INPUT", help="Read-only once the type exists."),
    f("typoutput", "Output function", "select", "Engine", group=EXTG, visible_when=EXT, required=True,
      option_values_path=["catalog", "functions"], native_keyword="OUTPUT", help="Read-only once the type exists."),
    f("typreceive", "Receive function", "select", "Engine", group=EXTG, visible_when=EXT,
      option_values_path=["catalog", "functions"], native_keyword="RECEIVE"),
    f("typsend", "Send function", "select", "Engine", group=EXTG, visible_when=EXT,
      option_values_path=["catalog", "functions"], native_keyword="SEND"),
    f("typmodin", "Typmod in function", "select", "Engine", group=EXTG, visible_when=EXT,
      option_values_path=["catalog", "functions"], native_keyword="TYPMOD_IN"),
    f("typmodout", "Typmod out function", "select", "Engine", group=EXTG, visible_when=EXT,
      option_values_path=["catalog", "functions"], native_keyword="TYPMOD_OUT"),
    f("typanalyze", "Analyze function", "select", "Engine", group=EXTG, visible_when=EXT,
      option_values_path=["catalog", "functions"], native_keyword="ANALYZE"),
    f("typsubscript", "Subscript function", "select", "Engine", group=EXTG, visible_when=EXT, version=vmin("14"),
      option_values_path=["catalog", "functions"], native_keyword="SUBSCRIPT"),
    f("typcategory", "Category type", "select", "Engine", group=EXTG, visible_when=EXT, options=TYPE_CATEGORIES,
      native_keyword="CATEGORY", help="Read-only once the type exists."),
    f("typispreferred", "Preferred?", "boolean", "Engine", group=EXTG, visible_when=EXT, native_keyword="PREFERRED",
      help="Read-only once the type exists."),
    f("element", "Element type", "select", "Engine", group=EXTG, visible_when=EXT, option_values_path=["catalog", "types"],
      native_keyword="ELEMENT", help="Read-only once the type exists."),
    f("typdelim", "Delimiter", "text", "Engine", group=EXTG, visible_when=EXT, native_keyword="DELIMITER",
      help="Read-only once the type exists."),
    f("typalign", "Alignment type", "select", "Engine", group=EXTG, visible_when=EXT, native_keyword="ALIGNMENT",
      options=opts(("c", "char"), ("s", "int2"), ("i", "int4"), ("d", "double")), help="Read-only once the type exists."),
    f("typstorage", "Storage type", "select", "Engine", group=EXTG, visible_when=EXT, native_keyword="STORAGE",
      options=opts(("p", "PLAIN"), ("e", "EXTERNAL"), ("m", "MAIN"), ("x", "EXTENDED"))),
    f("typbyval", "Passed by value?", "boolean", "Engine", group=EXTG, visible_when=EXT, native_keyword="PASSEDBYVALUE",
      help="Read-only once the type exists."),
    f("is_collatable", "Collatable?", "boolean", "Engine", group=EXTG, visible_when=EXT, version=vmin("9.1"),
      native_keyword="COLLATABLE", help="Read-only once the type exists."),
    props("type_acl", "Privileges", "text", "Security", visible_when=TYP),
    privileges("typacl", "Security", "type", ["U"], visible_when=TYP,
               help="Privilege code U (USAGE). Not available for shell types."),
    seclabels(version=vmin("9.1")),
]
write("type", ["domain", "type"], type_fields,
      LEGACY + "Sources: " + SRC + "databases/schemas/domains/static/js/domain.ui.js (DomainSchema, DomainConstSchema, "
      "variant domain) and databases/schemas/types/static/js/type.ui.js (TypeSchema, CompositeSchema, "
      "EnumerationSchema, RangeSchema, ExternalSchema), static/js/privilege.ui.js, static/js/sec_label.ui.js. "
      "Mapping by field match: General/Definition->General (groups Members/Labels/Range), domain Constraints->Constraints, "
      "External Type nested tab->Engine group 'External type', Security->Security. Ids shared by two sub-schemas "
      "(collname, typlen, typdefault, precision) are listed once with visible_when on both variants; properties-only "
      "duplicates of range/external ids (typname, opcname, rngcanonical, typinput, ...) are not repeated.",
      gaps=[
          {"concept": "EDB nested table / varying array (typtype N/V, DataTypeSchema)",
           "reason": "ppas-only (type, tlength, precision, maxsize); out of beta scope."},
          {"concept": "Function pickers filtered by signature",
           "reason": "ExternalSchema.filterFunctionOptions narrows typinput/typoutput/... to functions with a matching "
                     "signature; option_values_path catalog.functions is unfiltered."},
          {"concept": "Composite member length/precision ranges",
           "reason": "CompositeSchema enables tlength/precision per member type from the type list; typed as number."},
          {"concept": "Skeleton length/precision/scale/members ids",
           "reason": "pgAdmin ids are typlen/precision (domain) and the composite/enum grids; the skeleton's generic ids "
                     "are not used so the backend contract stays intact."},
      ])
