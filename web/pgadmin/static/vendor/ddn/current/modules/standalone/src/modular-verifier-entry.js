import * as api from './modular-verifier-api.js';
import { bootModularShell } from './modular-shell.js';
const { createModularRuntimeOptions, createVerifier } = api;
export { api };
bootModularShell({ mode: 'verifier', options: createModularRuntimeOptions, verifier: createVerifier }, api);
//# sourceMappingURL=modular-verifier-entry.js.map