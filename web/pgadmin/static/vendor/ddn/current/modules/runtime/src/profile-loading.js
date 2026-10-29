const hosts = new WeakMap();
/** Distribution-host hook; DDN source cannot supply code or a loading URL. */
export function attachProfileLoadingHost(runtime, host) { hosts.set(runtime, host); }
export function profileLoadingHost(runtime) { return hosts.get(runtime); }
export async function prepareRuntimeProfiles(runtime, input, options) {
    await hosts.get(runtime)?.ensure(input, options);
}
//# sourceMappingURL=profile-loading.js.map