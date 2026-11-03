import './schema-native.js';
import { bootComputeWorker } from '../../execution/src/worker-entry.js';
import { loadedProfilePacks } from '../../profiles/src/family-packs.js';
bootComputeWorker({ versions: { api: '1.0', language: 'ddn-next-1', defaults: 'ddn-next-1', packs: {} }, packs: loadedProfilePacks() });
//# sourceMappingURL=modular-worker.js.map