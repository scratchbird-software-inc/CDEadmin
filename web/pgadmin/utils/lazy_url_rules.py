##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""URL rules that compile their URL builders on first use.

When a rule is added to the URL map, werkzeug's ``Rule.compile()`` generates
two URL-builder functions for it through ``ast`` and ``compile()``: one for
``url_for`` with only the rule's own arguments and one that appends unknown
arguments as a query string. With about 1400 rules this was about 40% of the
CPU time of ``create_app()`` (performance review, 2026-11-07), and a process
uses few of those builders. ``LazyBuilderRule`` defers each builder to its
first use; the URLs it builds are werkzeug's own.

It depends on werkzeug calling ``Rule._compile_builder(append_unknown)`` from
``compile()`` and binding the result to the rule.
``tools/tests/test_lazy_url_rules.py`` compares the built URLs with
werkzeug's ``Rule`` and fails if that hook changes.
"""
from werkzeug.routing import Rule


class LazyBuilderRule(Rule):
    """A werkzeug rule that compiles each URL builder when first used."""

    def _compile_builder(self, append_unknown=True):
        compile_builder = super()._compile_builder
        compiled = None

        def build(rule, *args, **kwargs):
            # Two threads may both compile on first use; the builders are
            # equivalent, so either result is correct.
            nonlocal compiled
            if compiled is None:
                compiled = compile_builder(append_unknown)
            return compiled(rule, *args, **kwargs)
        return build
