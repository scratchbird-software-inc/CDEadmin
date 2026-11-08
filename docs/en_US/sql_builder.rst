.. _sql_builder:

***********************
`SQL builder`:index:
***********************

.. note::

   Owner direction, 2026-11-06 (option b): a visual SQL builder opened from
   the SQL tab writes a query into the editor. Owner direction, 2026-11-08:
   SQLite and DuckDB first. Added 2026-11-08.

The SQL builder is a form that writes a ``SELECT`` statement in the
connection's own SQL and puts it in the SQL tab's editor. It never runs the
statement: review it, change it if you like, and run it as usual.

Opening the builder
===================

On the SQL tab of a connection whose engine offers the builder, click
*Build query…* on the toolbar. As of 2026-11-08 the SQLite and DuckDB
connections offer it; on other connections the button is not shown.

The *Build a query* dialog (form reference SR-F-010017) reads the tables
and views of the connection's catalog, with their columns, and the options
the connected engine has.

Options and why some are disabled
=================================

Every option is shown for every connection. An option the connection lacks
is disabled, and the reason is shown with it: in the choice's label in a
list, or under the field. *Options for this connection*, at the top of the
dialog, lists all of them.

The options are:

* common table expressions (``WITH``), ``RECURSIVE``, and ``MATERIALIZED`` or
  ``NOT MATERIALIZED``;
* ``DISTINCT`` and ``DISTINCT ON``;
* inner, left, right, full, cross and natural joins, and joins on equal
  column names (``USING``);
* ``WHERE`` conditions, combined with ``AND`` or ``OR``;
* the aggregates ``count``, ``sum``, ``avg``, ``min`` and ``max``, also over
  distinct values;
* ``GROUP BY`` columns, ``ROLLUP``, ``CUBE``, ``GROUPING SETS`` and
  ``GROUP BY ALL``, and ``HAVING``;
* ``ORDER BY`` with ``NULLS FIRST`` or ``NULLS LAST``, ``LIMIT`` and
  ``OFFSET``;
* ``UNION``, ``UNION ALL``, ``INTERSECT`` and ``EXCEPT``.

Each engine declares which options it has, from which version, and the
reason shown when one is missing. The declaration is checked against the
version of the connected server or library:

* **SQLite** has no ``DISTINCT ON``, ``ROLLUP``, ``CUBE``, ``GROUPING SETS``
  or ``GROUP BY ALL``. Right and full joins are offered from SQLite 3.45.1,
  the oldest tracked SQLite build that accepts them; SQLite 3.35.0 refuses
  them.
* **DuckDB** has every option. It was checked on DuckDB 1.5.2 only.

The server checks the options again when it writes the statement. If a
query uses an option the connection lacks, the dialog shows the reason and
nothing is put in the editor.

Building a query
================

A query is one or more ``SELECT`` blocks. Each block has:

* **FROM**: a table, view or common table expression, with an optional
  alias, and any joins;
* **Columns**: columns, aggregates or values, each with an optional alias,
  or all columns (``*``). With no columns, every column is read;
* **WHERE**, **Grouping** and **HAVING**.

*Add SELECT (UNION, INTERSECT, EXCEPT)* adds another block, joined to the
previous one by a set operation. *ORDER BY, LIMIT and OFFSET* apply to the
whole query. When the query has more than one block, it is sorted by the
names of its result columns.

Under *WITH*, *Add common table expression* adds a named query that the
main query, and later common table expressions, can read like a table. With
*RECURSIVE*, a common table expression can also read itself; give it a
second block joined by ``UNION ALL`` that follows its rows, for example
from an employee to the people reporting to them.

Column choices are written as *alias.column*, or *table.column* when the
source has no alias. If you rename an alias or a common table expression
after choosing its columns, those choices are marked *(no longer
available)* and are still written as chosen, until you choose again.

*Preview SQL* shows the statement in the dialog. *Insert into editor* puts
it in the editor. If the editor holds text you wrote, you are asked before
it is replaced; nothing is replaced while a statement is running.

How names and values are written
================================

Names are written the way *Browse data* writes them: without quotes when
the connection's SQL reads the name back unchanged, and quoted otherwise.
Text values are written as SQL string literals; numbers must be finite.
Values are never pasted into the statement as SQL.

Limits
======

As of 2026-11-08 the builder writes column references, values and
aggregates only. It has no arithmetic, other functions, ``CASE``,
subqueries, ``IN`` lists or window functions, and it does not keep a query
once the dialog is closed. Edit the statement in the editor for anything
else.
