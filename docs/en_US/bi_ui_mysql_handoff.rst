.. _bi_ui_mysql_handoff:

*************************************
BI questions: MySQL descriptor handoff
*************************************

The BI questions tool (:doc:`bi_query_builder_ui`) is registered for SQLite,
DuckDB, Firebird, MariaDB and PostgreSQL. ``ui_descriptors/mysql/`` belongs to
another stream and was not edited, so MySQL has no menu entry yet.

The generic ``open_tool`` handler is already admitted by
``web/pgadmin/cdeadmin/context_menu.py`` (``_HANDLERS``) and by
``SAFE_HANDLERS`` in ``web/pgadmin/browser/static/js/ProviderContextMenu.js``.
The only change MySQL needs is one object appended to the ``tools`` array of
``web/pgadmin/cdeadmin/ui_descriptors/mysql/tools.json``:

.. code-block:: json

   {
     "command_id": "endpoint.mysql.bi_questions",
     "scope": "endpoint",
     "label": "BI questions...",
     "description": "Collections, the visual query builder, saved questions and their revision history.",
     "handler": "open_tool",
     "slot": "after_verify",
     "icon": "tool.data-explorer",
     "group": "information",
     "priority": 72,
     "arguments": {"surface": "bi.questions"},
     "enabled_when": ["verified"]
   }

No React or Python change is required. After adding it, run
``python3 tools/validate_ui_descriptors.py --counts`` (the counts do not move)
and ``pytest tools/tests/test_ui_descriptor_tools.py
tools/tests/test_cdeadmin_context_menu.py``.
