"""Native runtime and persisted configuration, including unloaded components."""

# The native persisted table does not expose a sensitivity classification. An
# unloaded component can leave credentials there under an arbitrary name.
# Preserve that object's identity and presence without exporting its value.
SELECT = '''SELECT n.VARIABLE_NAME,g.VARIABLE_VALUE AS GLOBAL_VALUE,
v.VARIABLE_SOURCE,v.VARIABLE_PATH,v.MIN_VALUE,v.MAX_VALUE,
v.SET_TIME,v.SET_USER,v.SET_HOST,
CASE WHEN g.VARIABLE_NAME IS NULL THEN NULL ELSE p.VARIABLE_VALUE END AS PERSISTED_VALUE,
g.VARIABLE_NAME IS NOT NULL AS GLOBAL_PRESENT,
p.VARIABLE_NAME IS NOT NULL AS PERSISTED_PRESENT,
(g.VARIABLE_NAME IS NULL AND p.VARIABLE_NAME IS NOT NULL) AS PERSISTED_VALUE_REDACTED
FROM (SELECT VARIABLE_NAME FROM performance_schema.global_variables
UNION SELECT VARIABLE_NAME FROM performance_schema.persisted_variables) n
LEFT JOIN performance_schema.global_variables g ON g.VARIABLE_NAME=n.VARIABLE_NAME
LEFT JOIN performance_schema.variables_info v ON v.VARIABLE_NAME=n.VARIABLE_NAME
LEFT JOIN performance_schema.persisted_variables p ON p.VARIABLE_NAME=n.VARIABLE_NAME
ORDER BY n.VARIABLE_NAME'''


def persistence_present(facts):
    """Presence is independent of a value that can be NULL or redacted."""
    if 'persisted_present' in facts:
        return facts['persisted_present'] in (True, 1, '1')
    return facts.get('persisted_value') is not None
