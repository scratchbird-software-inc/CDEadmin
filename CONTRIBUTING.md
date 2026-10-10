# Contributing to ScratchRobin CDE Admin

Thank you for your interest in contributing to CDEadmin.

The project is currently in heavy development and is not accepting external
contributions. Defects and security reports must be sent to CDEadmin's own
project channels, not to the pgAdmin Development Team.

Current work must follow these rules:

- Provider code describes only behavior supported by the exact engine.
- The target is full replacement of each engine's management console. An
  engine's unique features are required coverage, not optional exceptions to
  a common feature set. Catalog completeness alone does not prove this.
- Shared UI components may provide layout but may not invent shared engine
  semantics or silently substitute PostgreSQL behavior.
- Reuse functional forms when their provider contracts allow it. Hide fields
  and actions that do not apply to the selected engine, version, edition or
  attachment mode. A missing implementation is an open coverage obligation,
  not evidence that the native engine lacks the feature.
- Backend contributors own functional forms and native workflows, including
  validation, permissions, execution and outcome handling. The human-interface
  team owns visual refinement; that handoff must not leave functionality
  unimplemented.
- A supported mutation needs a provider-owned form, validation, preview,
  execution path, live evidence and browser review.
- Secrets must not appear in routes, logs, screenshots or retained evidence.
- Native transaction completion belongs to the provider session; common code
  must not replay mutations or infer commit success.
- Existing upstream copyright headers and the PostgreSQL Licence must remain.
- New project-owned names use ScratchRobin/CDEadmin naming unless an inherited
  compatibility interface requires otherwise.

Development reports, workplans and QA evidence belong under the external
``~/Sandbox/pgadmin4_work_area/`` workspace. Product code and documentation
belong in this repository. ScratchBird source/specifications and donor-engine
source trees are read-only research inputs.
