Firebird platform and release evidence
======================================

Native qualification is bound to the delivered source and the actual operating
system. Linux observations are never relabeled as Windows or macOS evidence.
This workflow qualifies Firebird 5.0.4 with CPython 3.14 and firebird-driver
1.10.11. It preserves engine-specific functionality and does not downgrade a
failed platform to a generic SQL-only provider.

Native platform inventory
--------------------------

``tools/development/firebird_platform.py`` owns its runtime copies, native server,
security database and disposable database directories. It does not install a
service or use an existing application's database. Passwords are generated for
the owned server and passed through a named child environment variable; routes,
receipts and command arguments contain no password. Runtime security templates
are fingerprinted before and after qualification. Cleanup is required for success.

Each host qualifies network and embedded attachments independently, in fresh
processes with explicit native client paths. The driver gate observes the actual
remote protocol and verifies exact-engine creation, non-ASCII metadata/values,
ARRAYs, large BLOBs and bounded streaming, independent pending/committed
visibility, rollback, Services API where applicable and release. Embedded
attachments use the embedded provider and filesystem scope, with no Services
API or network credential substitution.

Both modes run all 47 legacy charset checks, the complete GB18030 Unicode and
admitted byte-grammar domains, and UNICODE_FSS conversion against the native
engine. ``--quick-codecs`` is diagnostic only and cannot qualify a release.
The ``firebird-codecs`` development stage (``--driver-only`` on the platform
runner) preserves exhaustive conversion differences and transport observations
without workflows; it deliberately returns an incomplete release receipt.
``firebird-abi`` provisions only the native Firebird kit and pinned Python
driver for focused event calling-convention diagnosis. Its diagnostic receipt
cannot qualify a backend release.
Independent workflow fixtures cover editor execution, row SQL, templates,
profiling/statistics, data export/import, test-data generation, metadata search,
BLOB operations, DDN/native SQL replay, events, recreate-empty and registration
clone/move. Failures are collected without discarding other workflow outcomes.
Each workflow must release its handles and remove its owned databases.
Each workflow runs in a separate bounded native process. A crash or stalled
native call preserves its failure and traceback without skipping later workflows.

GB18030 selects a qualified conversion profile from the connected engine's
observed mappings. Its ICU data may differ across native distributions; the
client operating system is not used to guess a remote server's mapping. The
probe owns a separate read-only transaction and leaves user work untouched.
Native checks cover SQL/metadata, scalar and ARRAY roundtrips and pending-work
preservation as well as the complete conversion domains. Unknown profiles fail
explicitly. The pinned event driver uses a fixed-prefix variadic binding so
Apple Silicon receives native event names through its actual C calling convention.
The Mac binding zero-extends the bounded event count to 32 bits to accommodate
Apple libffi's fixed-argument validation. Focused native diagnosis covers
concurrent one-name and fifteen-name collectors and a 127-byte UTF-8 event name.
The subscription owns the pinned driver's native event buffers. Confirmed
cancellation and thread release precede deallocation through the admitted client;
failed cancellation retains the buffers for the connection's owned cleanup retry.
The fixed-count representation follows `Apple's argument-extension rules
<https://developer.apple.com/documentation/xcode/writing-arm64-code-for-apple-platforms>`_;
the narrow-argument check is visible in `Apple's libffi implementation
<https://github.com/apple-oss-distributions/libffi/blob/main/src/prep_cif.c>`_.

Windows additionally qualifies actual XNET shared memory and Win_Sspi trusted
authentication. Its owned server uses a unique IPC name and an isolated global
mapping for the test principal. The trusted-authentication fixture permits native
wire encryption negotiation because Win_Sspi supplies no encryption key;
password/TCP checks still require encryption. Receipts must observe XNET and
Win_Sspi explicitly; TCP or embedded fallback does not qualify them. Native
client binaries must match the host's PE, Mach-O or ELF format.
The native mapped-authentication receipt ``Mapped from Win_Sspi`` is also
accepted; another plugin or an inferred trusted-authentication flag is refused.
Creation paths retain server-side Windows drive/UNC or POSIX semantics from
any application host, with ambiguous paths and lexical root escapes refused.

GitHub and local execution
---------------------------

The native development workflow supports ``firebird-platform`` as a targeted
stage. A fresh Windows or Mac run can use::

    gh workflow run native-development.yml --ref <candidate-branch> -f stages=prerequisites,doctor,clients,python,frontend-install,firebird-platform

The default platform list is Windows x64, Intel macOS and Apple Silicon macOS.
The existing full development environment stages remain distinct from this
Firebird-specific qualification. The workflow checks out the exact candidate
revision. ``frontend-install`` supplies the locked Node dependencies used by
backend helpers; the ``frontend`` stage separately compiles the application.
The workflow also checks out
the DDN revision recorded by that candidate. Source checkout uses
LF files on every host, avoiding accidental hash differences from Git conversion.
Before each build/test batch, the current designated DDN snapshot is refreshed
with its runtime, editor, declarations, assets and provenance together.
The portable DDN build-path correction is applied in isolated captures on every
host, keeping the consumed bundle and its provenance consistent across the matrix.
Native development evidence also preserves the consumed DDN provenance manifest
so source and dependency differences can be reviewed directly.

After installing the native dependencies and selecting the qualified complete
runtime, run the same inventory locally in a fresh process::

    python -m tools.development.firebird_platform --runtime-root /absolute/native/firebird --evidence /absolute/external/new-evidence

The evidence directory must be outside the checkout and must not exist. Windows
uses its native absolute paths. Linux contributors may use their owned Firebird
5.0.4 build; Windows and Mac contributors use their matching native distribution.
No Docker or Linux client extraction is used by this platform runner. Native
development setup and Electron/browser startup remain separate checks.
The runner supplies the application import path to each workflow subprocess;
local contributors do not need to export ``PYTHONPATH`` in their shell.

Source and artifact reconciliation
-----------------------------------

``platform.json`` records operating system/architecture, Python, the exact source
revision and dirty state, hashes of all tracked/unignored source, DDN revision
and artifacts, native binary format/hash, mode receipts and owned cleanup.
Source hashes are checked again after execution. Every published receipt/log is
hashed; native security databases and private runtime directories are excluded.
GitHub run identifiers are retained when present. Logs and failure inventories
remain outside the implementation repository.

``tools/firebird_release_evidence.py`` reconciles the four required native hosts:
Linux x64, Windows x64, Intel Mac and Apple Silicon Mac. Supply the expected source
fingerprint from the release candidate and each downloaded ``platform.json``::

    python -m tools.firebird_release_evidence --source-sha256 <candidate-sha256> --receipt /evidence/linux/platform.json --receipt /evidence/windows/platform.json --receipt /evidence/mac-intel/platform.json --receipt /evidence/mac-arm/platform.json --output /evidence/release.json

The reconciler verifies preserved artifact bytes and opens the native driver and
workflow receipts. It refuses missing hosts, duplicate evidence, mismatched
source/runner bindings, stale provider files, incomplete codec or workflow
inventories, failed release/cleanup, an unexpected transport/authentication
method, and changed native client hashes. A top-level success flag alone is
insufficient. A targeted, skipped or incomplete run is not full platform evidence.

Candidate collection
--------------------

``tools/firebird_release_candidate.py`` collects the native matrix for one clean,
committed candidate from the Linux x64 qualification host. Refresh the current
DDN dependency before commit validation, commit and publish the candidate, then
dispatch the targeted native workflow above against that exact revision. Supply
the resulting run ID and a complete, matching Linux Firebird runtime::

    python -m tools.firebird_release_candidate --native-run <run-id> --runtime-root /absolute/native/firebird --wait-seconds 21600 --evidence /absolute/external/new-candidate-evidence

Use the qualified CPython 3.14 application environment with its locked Node
dependencies. This command runs Linux network and embedded qualification in a
fresh process, captures the three native GitHub artifacts, and invokes the strict
four-host reconciler. It preserves ``candidate.json``, GitHub run/artifact
metadata before and after capture, download logs, each platform's original
receipts/logs, ``release.json`` and ``summary.md``. Evidence must be outside the
checkout in a new directory. An existing exact-candidate Linux proof can be
supplied with ``--linux-receipt /evidence/linux/platform.json`` instead of
``--runtime-root``; its public artifacts are verified and copied into the new
evidence directory. Runtime directories, security databases and keys are excluded.

The collector admits only this repository's native workflow dispatch for the
candidate's exact revision. Artifact names, repository identity, run ID, rerun
attempt, retention, host, clean source fingerprint and DDN artifacts must all
match. A rerun during capture invalidates the collection. It never fills a
missing host with an older artifact or relabels a development-only run as backend
release proof. Failed hosts and downloads are retained in the failure inventory
while other hosts are still inspected. The command exits nonzero on incomplete
or inconsistent evidence, or if the local candidate changes during collection.
GitHub authentication uses the contributor's existing ``gh`` session.

Release boundaries
-------------------

A complete matrix establishes native driver and portable backend workflow
qualification for the captured candidate. It does not grant whole-product
release approval. The receipt preserves separate requirements for human form
validation, platform keyboard/accessibility/visual QA, signed installers and
installed-application lifecycle testing, and live ScratchBird monitoring-history
acceptance. Linux desktop Docker/terminal evidence remains scoped to Linux until
those desktop tools have their own platform implementation and qualification.
Owner-assigned human validation is not replaced with automatic form signoff.
