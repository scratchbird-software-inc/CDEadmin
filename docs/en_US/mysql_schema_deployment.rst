Versioned MySQL schema deployment automation
============================================

``tools/cdeadmin_mysql_deploy.py`` provides a local operator/CI entry point over
the existing native MySQL DDN plan, validation, durable review, application and
receipt services. It uses the admitted MySQL 9.7.0 profile and the installed
corrected Connector/Python 26.7.0 interface selected by each registration.

Run it with the application's Python environment and Node runtime, using the
same application configuration and durable operation store as the desktop or
server. Normal ``config_local.py``/system configuration applies;
``CONFIG_DISTRO_FILE_PATH`` selects a distribution configuration when needed.
Initialize the application configuration database through normal setup first.

This is a trusted local operator command, like local server import/export.
The operator must have access to the application configuration and supply the
explicit active owner's email, owned registration, registered target and native
database credential. It does not expose a network authentication bypass. Native
provider administration/execution admission and database privileges still apply.
Passwords come from the explicitly named environment variable, never an argument,
artifact, review ticket or report; the CLI consumes that variable before native
verification and forgets retained credentials on normal exit.

Capture, package and review
---------------------------

For example, with the CI secret available as ``DEPLOY_DATABASE_PASSWORD``::

    python tools/cdeadmin_mysql_deploy.py capture --user OWNER --server-id 7 --target-id TARGET_UUID --environment staging --password-env DEPLOY_DATABASE_PASSWORD --output staging-capture.json

The capture contains an exact native binding and a DDN workspace under
``snapshot``. Prepare the desired DDN workspace through the existing native
catalog/design workflow and save its workspace envelope as ``staging-desired.json``.
The baseline remains the original capture. Preserve its native identities and
explicit alteration/removal instructions. A missing selected object is not
permission to drop it.

Create a manifest, with local paths relative to that manifest::

    {
      "version": "release.2026.10.22.1",
      "environments": {
        "staging": {
          "capture": "staging-capture.json",
          "desired": "staging-desired.json",
          "execution": null
        }
      }
    }

Package and inspect the exact release::

    python tools/cdeadmin_mysql_deploy.py pack --manifest release-input.json --output release.json
    python tools/cdeadmin_mysql_deploy.py plan --user OWNER --server-id 7 --target-id TARGET_UUID --environment staging --password-env DEPLOY_DATABASE_PASSWORD --artifact release.json --output staging-plan.json

The artifact embeds its baseline and desired DDN; it has no runtime file/network
references. Canonical content hashes cover its version, environment bindings,
DDN and execution policies. Versions are labels; the exact content fingerprint
is the release identity. Up to sixteen independently captured environments can
share one artifact. Each has its own native baseline/desired pair and binding:
owner ID, registration ID, endpoint ID, target ID, database name, native server
UUID, runtime version and registration fingerprint. Selecting another environment
does not rewrite schemas, SQL, definers, identities or deletion authority.

The plan report contains native statements, blockers, conflicts, ignored
selections and ``execution_sha256``. Planning performs native validation without
applying its statements. Review requires that displayed execution fingerprint::

    python tools/cdeadmin_mysql_deploy.py review --user OWNER --server-id 7 --target-id TARGET_UUID --environment staging --password-env DEPLOY_DATABASE_PASSWORD --artifact release.json --expect-plan EXECUTION_SHA256 --ticket-output staging-review.json --output staging-review-report.json

A review ticket binds the exact artifact, environment and native durable review.
Its native review expires after five minutes. Apply checks the ticket against
that durable record and recompiles the artifact's intended operations through
the existing native planner. Relabelling an older review cannot authorize a
new artifact. Changed native definitions or registrations require a fresh
capture/plan/review; no implicit baseline replacement occurs.

Apply and observe
------------------

Approve the exact ticket fingerprint printed by ``review``::

    python tools/cdeadmin_mysql_deploy.py apply --user OWNER --server-id 7 --target-id TARGET_UUID --environment staging --password-env DEPLOY_DATABASE_PASSWORD --artifact release.json --ticket staging-review.json --approve TICKET_SHA256 --output staging-apply.json
    python tools/cdeadmin_mysql_deploy.py receipt --user OWNER --server-id 7 --target-id TARGET_UUID --environment staging --password-env DEPLOY_DATABASE_PASSWORD --artifact release.json --ticket staging-review.json --output staging-receipt.json

Application uses independent native connections and the existing durable
once-only claim, baseline/absence revalidation, native acknowledgement and
rediscovery rules. Existing interactive transactions, savepoints and warning
areas remain independent. MySQL DDL commits implicitly; a batch can commit a
prefix and cannot promise transactional rollback. Native concurrency warnings
and required maintenance windows remain part of the reviewed plan.

Repeating ``apply`` with a spent ticket returns its original receipt without
redispatch. An interrupted command may have spent its ticket or completed native
DDL before losing its report. Query the original receipt; do not create a new
review automatically. A fresh ``plan`` against an already applied baseline can
report drift: the original receipt is the record of that application.

Controlled native ALTER and online copy
----------------------------------------

Set ``execution`` to the same explicit policy accepted by the existing controlled
DDL workspace, for example::

    {"method":"native","algorithm":"INSTANT","lock":"DEFAULT","lock_wait_seconds":2,"timeout_seconds":30}

Controlled execution uses the existing owned asynchronous worker, progress and
cancellation contract. ``apply --wait-seconds N`` bounds CLI waiting; native
execution limits still apply. On a normal CLI exit its owned worker is stopped
and joined, and the final durable status is read again. Cancellation is not
reported as rollback or proof that the target stayed unchanged.

The admitted Percona Toolkit 3.7.2 online-copy policy uses
``method: pt-online-schema-change``, ``algorithm: COPY`` and ``lock: NONE``.
Its pinned script, native Perl/DBI/DBD runtime, execution-host admission, replica
bindings, source/load gates and private utility supervision remain the existing
online-schema-change contract. Install it through the existing native tool setup.
Headless cutover additionally requires ``apply --cutover`` on the exact approved
ticket. Without that explicit approval the CLI stops its worker when it reaches
the cutover wait. No native algorithm fallback, automatic retry or unattended
cutover is inferred from a successful plan or native PREPARE.

Reports, exits and retention
----------------------------

Every command prints one JSON summary to stdout. Startup messages use stderr.
``--output`` holds the complete private artifact/capture/plan/report; review also
requires a private ticket output. Files are created exclusively with mode 0600
on POSIX and are never overwritten, including through an existing symlink.
Claiming an unavailable report or ticket path fails before native work. A failed
command can leave its newly reserved output incomplete; use a new output path
and inspect the original native receipt before deciding on further application.
The reports can contain native SQL and private metadata; sharing is deliberate.

.. list-table:: CI exit contract
   :header-rows: 1

   * - Exit
     - Meaning
   * - 0
     - Capture/package succeeded; plan is unblocked (possibly no changes); review was prepared; or native application committed with verified rediscovery.
   * - 2
     - Invalid input/binding/admission, blocked native validation, or a CLI/runtime/report failure. An apply/report failure is not proof that no native work occurred.
   * - 3
     - The three-way plan found native baseline drift.
   * - 4
     - The native receipt reports not dispatched.
   * - 5
     - Partial/unknown/active outcome, or committed without verified rediscovery. Query the original receipt; no automatic retry is authorized.

Operating-system interruption can prevent any JSON report from being delivered.
Durable native receipt state remains authoritative. The CLI creates no engine
migration-history table and does not depend on ScratchBird history. Artifact,
ticket and report retention belongs to the selected local/CI paths; native review
and outcome retention stays in the application's durable schema receipt store.

Qualification
--------------

``tools/cdeadmin_mysql_deployment_qualification.py`` exercises actual CLI
subprocesses with independent native environments, both connector interfaces,
source/data and transaction preservation, artifact/ticket refusal, drift exits,
process loss after the durable claim, and native controlled/online-copy outcomes.
Store all evidence and disposable fixtures outside the repository. Linux
qualification records its exact source and native tool identities; Windows/macOS
qualification remains with the platform teams. ScratchBird history testing stays
owner-deferred.
