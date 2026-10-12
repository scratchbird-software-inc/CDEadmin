Firebird driver development and platform handoff
===============================================

ScratchRobin's Firebird provider targets Firebird 5.0.4 and currently pins
``firebird-driver==1.10.11``. Both authenticated network attachments and local
embedded attachments use the native Firebird client API. The backend team owns
driver correctness, engine-specific operations, capability reporting and
functional forms. Windows and macOS teams own native UX refinement and platform
QA; low-level defects found there return to the backend workstream.

Dependencies and library selection
----------------------------------

Install the application, regression and reference-engine Python requirements in
one platform-native virtual environment. Keep the repository lockfiles and
driver pin. Python 3.12 is the current Linux qualification baseline; a different
Python version requires its own native checks. Do not copy a Linux virtual
environment or native library into Windows/macOS.

Use a complete Firebird 5.0.4 distribution of the same architecture as Python:

* Windows: ``fbclient.dll`` with its dependent runtime libraries and plugins.
* macOS: the distribution's native client dylib/framework, matching the Python
  process architecture, with its plugin and internationalisation resources.
* Linux: ``libfbclient.so`` and the matching distribution resources.

Set ``CDEADMIN_FIREBIRD_CLIENT_LIBRARY`` to the absolute client-library path
before starting the application. Library selection is process-wide: restart
before changing it. The provider refuses changing an already initialized API
to another library. For embedded execution, the complete local engine, plugins,
ICU/internationalisation files and writable database/lock locations are required;
a client library alone is insufficient. Select the owned runtime root through
``FIREBIRD`` when the runtime is not installed in its standard location. Native
loader diagnostics, OS permissions, quarantine/signing and architecture issues
must be tested on their actual host; Linux evidence does not establish them.

Portable native driver gate
---------------------------

``tools/cdeadmin_firebird_driver_platform_gate.py`` uses an installed runtime or
an already running dedicated test server. It does not depend on Docker, Linux
runtime staging or browser automation. Run it from the repository root in a
fresh process. Select an existing dedicated fixture directory that the server
(or embedded process) can write. The runner generates a random database name,
never overwrites a database, and drops only the database it successfully created.
No existing database belongs in the route file.

For a network test, create a UTF-8 JSON route file such as::

    {
      "host": "127.0.0.1",
      "port": 3050,
      "user": "PLATFORM_TEST_USER",
      "auth_plugin_list": "Srp256",
      "wire_crypt": "Required"
    }

The test principal needs database creation rights and access to the chosen test
directory. Passwords are prompted without echo. For automation, use
``--password-env NAME`` to name a process environment variable; never place a
password in a command or route file. The runner also checks Services API
attachment and engine version. It changes no server configuration or accounts.

Windows example, with a native Windows server directory::

    python -B -m tools.cdeadmin_firebird_driver_platform_gate --route-json C:\qa\route.json --fixture-directory C:\qa\databases --server-path-style windows --client-library "C:\Program Files\Firebird\Firebird_5_0\fbclient.dll" --evidence C:\qa\evidence\driver-001 --exhaustive-codecs

macOS example; replace the client path with the installed distribution path::

    python3 -B -m tools.cdeadmin_firebird_driver_platform_gate --route-json /Users/developer/qa/route.json --fixture-directory /Users/developer/qa/databases --server-path-style posix --client-library /absolute/path/to/libfbclient.dylib --evidence /Users/developer/qa/evidence/driver-001 --exhaustive-codecs

For a remote server, the fixture directory and ``--server-path-style`` describe
the server filesystem, not the workstation filesystem. The evidence directory
is always local to the runner and must not already exist.

For embedded mode, use this route instead::

    {"attachment_mode": "embedded", "user": "PLATFORM_LOCAL"}

Choose a dedicated local fixture directory and the local server path style.
Do not supply host, port, network authentication options or a password. This
mode creates its own database and exercises a second local attachment; it does
not attempt a Services API connection.

The basic gate exercises production provider creation/opening, non-ASCII
metadata and values, integer ARRAYs, a large text BLOB, pending/committed
visibility through an independent attachment, explicit rollback/commit,
bounded BLOB streaming, Services API attachment where applicable, handle
release and owned-database cleanup. ``--exhaustive-codecs`` additionally checks
all 47 legacy charsets, the complete GB18030 Unicode-scalar and admitted
one/two/four-byte grammar domains, and canonical UNICODE_FSS conversion for
every Unicode scalar against native conversions. Allow several
minutes for that mode; run it on each new Python/native-runtime combination.

The receipt records actual platform, architecture, Python/driver/client
versions, selected-library hash, provider source hashes, completed checks and
cleanup. Exceptions are recorded by type without raw native messages or
credentials. A failed check or incomplete cleanup returns a nonzero exit status.
The random fixture name remains in the receipt for investigating an interrupted
creation or cleanup; the runner never guesses that an uncertain creation may
safely be deleted.

UNICODE_FSS compatibility limit
-------------------------------

The provider distinguishes FSS SQL/identifier encoding from UTF8 data-message
and ARRAY transport. This prevents silent supplementary-character narrowing.
The qualified native 5.0.4 runtime still rejects some supplementary inputs on
FSS attachments and can corrupt its default FSS text-BLOB conversion. Those
paths fail explicitly: ordinary reads reject invalid UTF8 and streaming reads
validate text incrementally before declaring completion. No bytes are stripped
and no SQL is replayed. Use a UTF8 attachment for unrestricted Unicode SQL,
input and text BLOBs. BMP FSS BLOBs, exact scalar reads and character ARRAY reads
are qualified separately. These engine limits are not Windows/macOS UX issues.

Additional qualification responsibilities
-----------------------------------------

A portable-gate pass is a driver integration result, not full product acceptance.
Use the retained native qualification gates for the affected area when reporting
a defect or qualifying a change:

* ARRAYs: ``cdeadmin_firebird_array_charset_gate`` covers every catalog charset
  with fixed/varying arrays, ordinary and streamed reads, views and scalar
  subscript comparisons. Its local runtime fixture is currently Linux-specific.
* Character conversions: the legacy and GB18030 oracle callbacks are also
  invoked by the portable gate, so platform teams need not port Linux staging.
* Authentication and network options: repeat actual native plugin negotiation,
  encryption, connection interruption and credential lifecycle checks.
* Windows-specific: Win_Sspi requires a Windows application host; XNET requires
  actual local shared-memory transport. Neither is established by password/TCP
  tests or by a Windows browser connected to a Linux application.
* Embedded runtime: verify DLL/dylib and plugin discovery, concurrent attachment,
  file permissions/ACLs, lock cleanup and recovery on the native OS.
* Native forms and application lifecycle: verify functional operations through
  the platform application, then perform keyboard, accessibility and visual QA.

Keep evidence outside the repository. Report the exact source revision and
uncommitted source hashes, architecture, driver/native-library versions,
redacted reproduction and receipt. A successful Linux test must not be recorded
as Windows/macOS acceptance. UI and packaging acceptance are independent of
backend feature coverage; unresolved backend defects remain explicit work.
