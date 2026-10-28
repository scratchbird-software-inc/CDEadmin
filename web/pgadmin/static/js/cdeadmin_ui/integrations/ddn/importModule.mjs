// Keep the public SDK's ESM import native. The host's legacy CommonJS Babel
// transform applies to .js files; .mjs is passed directly to webpack.
export const importPublicModule = url => import(/* webpackIgnore: true */ url);
