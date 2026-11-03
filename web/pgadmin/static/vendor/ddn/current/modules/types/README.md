# @ddn/types

Declaration-only contracts for the new DDN standalone utilities. The [adopted standard utility specification](../../../../standard/utilities/README.md) supplies the complete core, scene and browser ABI. The [property codex](../../../../standard/codex/CONTRACT.md) defines normalized language records; these API declarations do not introduce a second language schema.

| Import | Contract |
| --- | --- |
| `@ddn/types` | Type-only exports of core and scene contracts; no DOM requirement |
| `@ddn/types/core` | Source/model revisions, references, diagnostics, lifecycle, commands, profiles, computation and runtime/verifier interfaces |
| `@ddn/types/scene` | Scene primitives, occurrences, geometry, coverage and incremental patches |
| `@ddn/types/browser` | Viewer/designer capabilities, browser assets, navigation and capture; DOM declarations required |

```ts
import type { Ref, Runtime, ModelSnapshot } from '@ddn/types';
import type { Viewer, Designer } from '@ddn/types/browser';
```

All package exports have only a TypeScript `types` condition. Runtime imports are deliberately unavailable because no factories are implemented here. Package version `0.0.0` denotes this private integration package; the adopted API and language identities remain `1.0` and `ddn-next-1`. No default-version identity is invented by this package.

The three declaration files are exact copies of their specification counterparts, with local `.js` import specifiers resolving to sibling declarations. The type-only root index keeps browser declarations out of headless consumers. [The manifest](contract-manifest.json) records their sources and SHA-256 values. Regenerate/check from the repository root using `node project/ddn/tooling/sync-contracts.mjs --write` or `--check`.
