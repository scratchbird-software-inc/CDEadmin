"""Native runtime and persisted configuration, including unloaded components."""

# The native persisted table does not expose a sensitivity classification. An
# unloaded component can leave credentials there under an arbitrary name.
# Preserve that object's identity and presence without exporting its value.
SELECT = '''SELECT n.VARIABLE_NAME,g.VARIABLE_VALUE AS GLOBAL_VALUE,
v.VARIABLE_SOURCE,v.VARIABLE_PATH,v.MIN_VALUE,v.MAX_VALUE,
v.SET_TIME,v.SET_USER,v.SET_HOST,
m.VARIABLE_SCOPE,m.DATA_TYPE,m.MIN_VALUE AS NATIVE_MIN_VALUE,m.MAX_VALUE AS NATIVE_MAX_VALUE,m.DOCUMENTATION,
m.VARIABLE_NAME IS NOT NULL AS NATIVE_METADATA_PRESENT,
CASE WHEN g.VARIABLE_NAME IS NULL THEN NULL ELSE p.VARIABLE_VALUE END AS PERSISTED_VALUE,
g.VARIABLE_NAME IS NOT NULL AS GLOBAL_PRESENT,
p.VARIABLE_NAME IS NOT NULL AS PERSISTED_PRESENT,
(g.VARIABLE_NAME IS NULL AND p.VARIABLE_NAME IS NOT NULL) AS PERSISTED_VALUE_REDACTED,
CASE WHEN p.VARIABLE_NAME IS NULL THEN 'absent'
 WHEN g.VARIABLE_NAME IS NULL THEN 'redacted'
 WHEN p.VARIABLE_VALUE='' THEN 'null_or_empty'
 WHEN p.VARIABLE_VALUE IS NULL THEN 'unconfirmed'
 ELSE 'value' END AS PERSISTED_VALUE_STATE
FROM (SELECT VARIABLE_NAME FROM performance_schema.global_variables
UNION SELECT VARIABLE_NAME FROM performance_schema.persisted_variables
UNION SELECT VARIABLE_NAME FROM performance_schema.variables_metadata) n
LEFT JOIN performance_schema.global_variables g ON g.VARIABLE_NAME=n.VARIABLE_NAME
LEFT JOIN performance_schema.variables_info v ON v.VARIABLE_NAME=n.VARIABLE_NAME
LEFT JOIN performance_schema.variables_metadata m ON m.VARIABLE_NAME=n.VARIABLE_NAME
LEFT JOIN performance_schema.persisted_variables p ON p.VARIABLE_NAME=n.VARIABLE_NAME
ORDER BY n.VARIABLE_NAME'''


def persistence_present(facts):
    """Presence is independent of a value that can be NULL or redacted."""
    if 'persisted_present' in facts:
        return facts['persisted_present'] in (True, 1, '1')
    return facts.get('persisted_value') is not None


def administration(facts):
    """SESSION_ONLY metadata does not authorize global/persist assignments."""
    if facts.get('variable_scope') != 'SESSION_ONLY': return None
    return {'allowed_operations': ['inspect'] + (['reset_persist'] if persistence_present(facts) else [])}


def persisted_value_ambiguous(facts):
    """P_S string rows contain no native NULL/empty type discriminator."""
    state = facts.get('persisted_value_state')
    if state is not None:
        return state in {'null_or_empty', 'unconfirmed'}
    # Older captures lack the explicit classification. They must not turn
    # ambiguous empty text into an exact persisted-value postcondition either.
    return persistence_present(facts) and facts.get('persisted_value') == ''
