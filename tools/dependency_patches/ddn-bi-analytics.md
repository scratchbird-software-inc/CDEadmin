# Reviewed consumer patch: `bi.analytics@1` profile

Date: 2026-11-10

## Scope and reason

Following owner direction (2026-11-07, 2026-11-08, 2026-11-09 and 2026-11-10),
ScratchRobin extends its own isolated DDN capture to support a dedicated BI
analytics and dashboard wiring profile (`bi.analytics@1`) without modifying the
upstream public `Diagram-Design-Notation` repository.

`ddn_bi_analytics.py` registers `bi.analytics@1` in the isolated build snapshot
before `project/ddn/packages/profiles/tools/generate.py` compiles the codex and
shard packs:

- Primary palette: `dashboard`, `saved_view`, `query_operation`, `dataset`,
  `table`, `view`, `metric`, `report`, `record`, `field`, `binding`.
- Relation vocabulary: `aggregates`, `assoc`, `bindfield`, `binds`, `derives`,
  `filters`, `joins`, `lookup`, `owns`, `part`, `ref`, `report`, `uses`.
- Presentation: graph projection in the `graphs-erd` shard with inline `data`
  compartment rows and explicit crow's-foot cardinality markers so source
  tables/datasets, SBsql query joins, metrics, saved question views, dashboard
  cards and filter bindings render cleanly in the shared viewer alongside
  `panels.composed@1` (composed dashboard tabs), `chart.*@1`,
  `timeline.basic@1` and `table.records@1`.

Every changed input hash and the patch/review hashes are recorded in
`web/pgadmin/static/vendor/ddn/current/resource-manifest.json` under
`consumer_patches.bi_analytics`.
