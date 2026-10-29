import type { Runtime, RuntimeOptions, SourceSet, Verifier } from '@ddn/types';
import type { Designer, Viewer, AssetProvider } from '@ddn/types/browser';
export interface ShellFactories {
    mode: 'viewer' | 'designer' | 'verifier';
    edition?: 'native' | 'complete';
    options: () => RuntimeOptions;
    verifier: (options: RuntimeOptions) => Verifier;
    viewer?: (element: HTMLElement, options: {
        runtimeOptions: RuntimeOptions;
        assets: AssetProvider;
    }) => Viewer;
    designer?: (viewer: Viewer) => Designer;
    newDiagram?: (viewer: Viewer, create: (source: string) => Promise<void>) => void;
    getRuntime?: (viewer: Viewer) => Runtime;
    initial?: {
        sources: SourceSet;
        view?: string | undefined;
        assets?: Readonly<Record<string, {
            text: string;
            mime: string;
        }>>;
    };
    ready?: (state: {
        viewer?: Viewer;
        designer?: Designer;
        verifier?: Verifier;
    }) => void;
}
export declare function mountShell(factories: ShellFactories): void;
