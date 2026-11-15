"""SQL completion type spellings, separate from source grammar productions.

This profile is qualified for MariaDB 12.2.2. Examples are column type clauses,
not expressions or application-side conversions. Native preparation remains
the authority for a caller's exact clause and session context.
"""
import re


# Each family shares the native parameter grammar, not necessarily storage
# semantics (REAL and DATE, for example, depend on the native SQL mode).
FAMILIES = (
    ('TINYINT INT1 SMALLINT INT2 MEDIUMINT INT3 MIDDLEINT INT INT4 INTEGER BIGINT INT8',
     'optional', '(display_width)', 'INT(11)', 'numeric'),
    ('DEC DECIMAL NUMERIC FIXED', 'optional', '(precision[,scale])', 'DECIMAL(10,2)', 'numeric'),
    ('FLOAT FLOAT4', 'optional', '(precision) or (display_width,scale)', 'FLOAT(24)', 'numeric'),
    ('REAL DOUBLE FLOAT8', 'optional', '(display_width,scale)', 'DOUBLE(10,2)', 'numeric'),
    ('BIT', 'optional', '(length)', 'BIT(8)', 'bit'),
    ('BOOL BOOLEAN', 'none', '', 'BOOLEAN', 'boolean-alias'),
    ('YEAR SQL_TSI_YEAR', 'optional', '(display_width)', 'YEAR(4)', 'temporal'),
    ('DATE', 'none', '', 'DATE', 'temporal'),
    ('TIME TIMESTAMP DATETIME', 'optional', '(fractional_seconds_precision)', 'TIME(6)', 'temporal'),
    ('CHAR CHARACTER NCHAR BINARY', 'optional', '(length)', 'CHAR(16)', 'string'),
    ('VARCHAR VARCHARACTER NVARCHAR VARBINARY', 'required', '(length)', 'VARCHAR(255)', 'string'),
    ('TINYBLOB MEDIUMBLOB LONGBLOB TINYTEXT MEDIUMTEXT LONGTEXT LONG JSON',
     'none', '', 'TEXT', 'lob'),
    ('BLOB TEXT', 'optional', '(length)', 'BLOB(255)', 'lob'),
    ('ENUM SET', 'required', "('member'[, ...])", "ENUM('a','b')", 'members'),
    ('GEOMETRY POINT LINESTRING POLYGON MULTIPOINT MULTILINESTRING MULTIPOLYGON GEOMETRYCOLLECTION',
     'none', '', 'POINT', 'spatial'),
    ('VECTOR', 'required', '(dimensions)', 'VECTOR(3)', 'vector'),
)
COMPOUND = (
    ('DOUBLE PRECISION', 'optional', '(display_width,scale)', 'DOUBLE PRECISION(10,2)', 'numeric'),
    ('NATIONAL CHAR', 'optional', '(length)', 'NATIONAL CHAR(16)', 'string'),
    ('NATIONAL CHARACTER', 'optional', '(length)', 'NATIONAL CHARACTER(16)', 'string'),
    ('CHAR VARYING', 'required', '(length)', 'CHAR VARYING(16)', 'string'),
    ('CHARACTER VARYING', 'required', '(length)', 'CHARACTER VARYING(16)', 'string'),
    ('NATIONAL VARCHAR', 'required', '(length)', 'NATIONAL VARCHAR(16)', 'string'),
    ('NATIONAL VARCHARACTER', 'required', '(length)', 'NATIONAL VARCHARACTER(16)', 'string'),
    ('NCHAR VARCHAR', 'required', '(length)', 'NCHAR VARCHAR(16)', 'string'),
    ('NCHAR VARCHARACTER', 'required', '(length)', 'NCHAR VARCHARACTER(16)', 'string'),
    ('NATIONAL CHAR VARYING', 'required', '(length)', 'NATIONAL CHAR VARYING(16)', 'string'),
    ('NATIONAL CHARACTER VARYING', 'required', '(length)', 'NATIONAL CHARACTER VARYING(16)', 'string'),
    ('NCHAR VARYING', 'required', '(length)', 'NCHAR VARYING(16)', 'string'),
    ('LONG VARBINARY', 'none', '', 'LONG VARBINARY', 'lob'),
    ('LONG VARCHAR', 'none', '', 'LONG VARCHAR', 'lob'),
    ('LONG VARCHARACTER', 'none', '', 'LONG VARCHARACTER', 'lob'),
    ('LONG CHAR VARYING', 'none', '', 'LONG CHAR VARYING', 'lob'),
    ('LONG CHARACTER VARYING', 'none', '', 'LONG CHARACTER VARYING', 'lob'),
)
ORACLE = (
    ('NUMBER', 'optional', '(precision[,scale])', 'NUMBER(10,2)', 'numeric'),
    ('VARCHAR2', 'required', '(length)', 'VARCHAR2(16)', 'string'),
    ('RAW', 'required', '(length)', 'RAW(16)', 'string'),
    ('CLOB', 'none', '', 'CLOB', 'lob'),
)
KNOWN_PLUGINS = frozenset({'UUID', 'INET4', 'INET6'})
ROUTINE_PLUGINS = frozenset({'ASSOCIATIVE_ARRAY', 'SYS_REFCURSOR'})


def candidates(version, sql_mode, plugins):
    """Return typed candidates and explicit unsupported-profile observations."""
    if not isinstance(version, str) or not re.match(r'^12\.2\.2(?:-|$)', version):
        return [], [{'section': 'native-sql-types', 'available': False,
                     'reason': 'type-profile-version-unqualified'}]
    definitions = []
    for names, requirement, parameters, example, family in FAMILIES:
        for name in names.split():
            # Preserve each spelling in its example, rather than displaying a
            # family representative with different mode-sensitive semantics.
            suffix = example[example.find('('):] if '(' in example else ''
            definitions.append((name, requirement, parameters, name + suffix, family))
    definitions.extend(COMPOUND)
    mode = {part.strip().upper() for part in str(sql_mode).split(',')}
    if 'ORACLE' in mode:
        definitions.extend(ORACLE)
    observations = [{'section': 'native-sql-types', 'available': True,
                     'profile': 'mariadb.sql-types@12.2.2', 'oracle_mode': 'ORACLE' in mode}]
    installed = set()
    for name, status in plugins:
        if isinstance(name, str) and str(status).upper() == 'ACTIVE':
            installed.add(name.upper())
    for name in sorted(KNOWN_PLUGINS & installed):
        definitions.append((name, 'none', '', name, 'installed-plugin'))
    routine = sorted(installed & ROUTINE_PLUGINS)
    if routine:
        observations.append({'section': 'native-routine-type-contexts', 'available': False,
            'reason': 'routine-local-type-completion-unimplemented', 'plugins': routine})
    unknown = sorted(installed - KNOWN_PLUGINS - ROUTINE_PLUGINS)
    if unknown:
        observations.append({'section': 'native-type-plugin-parameters', 'available': False,
            'reason': 'installed-type-parameter-shape-unqualified', 'plugins': unknown})
    rows = []
    for name, requirement, parameters, example, family in definitions:
        rows.append({'name': name, 'syntax': {
            'parameter_requirement': requirement, 'parameters': parameters,
            'example_sql': example, 'family': family,
            'availability': 'active-native-plugin' if family == 'installed-plugin' else
                            'oracle-mode' if name in {row[0] for row in ORACLE} else 'native-core',
            'semantics_authority': 'native-type-handler-and-sql-mode'},
            'detail': 'MariaDB column type' + (' ' + parameters if parameters else '')})
    return rows, observations
