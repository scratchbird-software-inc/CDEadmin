{# ===== Schema, relation and column names for Browse data (2026-11-06) ===== #}
{# Columns in table order; system and dropped columns are left out, as SELECT * does. #}
{% if obj_id %}
SELECT n.nspname, r.relname, a.attname
FROM pg_catalog.pg_class r
    JOIN pg_catalog.pg_namespace n ON (r.relnamespace = n.oid)
    LEFT JOIN pg_catalog.pg_attribute a ON (a.attrelid = r.oid
        AND a.attnum > 0 AND NOT a.attisdropped)
WHERE r.oid = {{obj_id}}::oid
ORDER BY a.attnum;
{% endif %}
