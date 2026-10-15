# Dependency build adjustments

`ddn-windows-paths.patch` fixes native Windows path matching in DDN 0.8.0's
Rollup build configuration. It normalizes the separator before testing whether
an import belongs to a sibling bundle. It changes build tooling, not the DDN
renderer, editor or source language.

`tools/refresh_ddn.py` applies it only inside the disposable Windows source
capture, checks that it applies, and records the patch SHA-256 and adjusted
source file SHA-256 in the consumed resource manifest. The original sister
checkout remains untouched. A changed upstream configuration that no longer
accepts the patch must be reconciled explicitly; the last admitted bundle is
preserved when capture or build fails.
