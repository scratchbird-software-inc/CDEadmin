import { bootComputeWorker } from '../../execution/src/worker-entry.js';
import { createCompletePack } from '../../profiles/src/index.js';
bootComputeWorker({
    versions: { api: '1.0', language: 'ddn-next-1', defaults: 'ddn-next-1', packs: {} },
    packs: [createCompletePack()],
});
//# sourceMappingURL=complete-worker-bootstrap.js.map