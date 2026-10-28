import { bootComputeWorker } from '../../execution/src/worker-entry.js';
import { createNativePack } from '../../profiles/src/native.js';
bootComputeWorker({
    versions: { api: '1.0', language: 'ddn-next-1', defaults: 'ddn-next-1', packs: {} },
    packs: [createNativePack()],
});
//# sourceMappingURL=worker-bootstrap.js.map