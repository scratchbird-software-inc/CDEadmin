# Development and qualification

Start with the [development and demo guide](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/tools/development/README.md)
and the [contribution guide](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/CONTRIBUTING.md).
The current tree uses a Flask/Python application, React client and Electron
desktop runtime. Provider code owns exact native dialect and capability
behavior; shared controls must not flatten engine differences.

The [implementation status](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/implementation_status.rst)
distinguishes source presence, local tests, CI and release approval. A provider
manifest's activation gate is bounded evidence. It is not a substitute for
live browser, driver, failure and platform qualification. Record exact source,
DDN and native-runtime revisions with test logs outside the implementation
repository.

Before any commit-validation build or test, follow the repository's `AGENTS.md`
DDN freshness instructions: inspect the sister project's revision and public
API, refresh the consumed runtime/editor/tool snapshot, then test the same
captured dependency. Do not edit the sister project's active checkout. Keep
generated builds, raw logs and fixtures out of source control.

The open-source site is built from versioned files in `docs/`; wiki pages are
versioned in `wiki/`. The GitHub wiki has a separate publication repository,
and GitHub Pages publishes from the configured branch and `/docs` directory.
Documentation must not promote uncommitted features to shipped status.
