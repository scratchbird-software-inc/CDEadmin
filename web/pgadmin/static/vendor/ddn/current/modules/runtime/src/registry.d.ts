import type { Pack, PackRegistrations, Registry, VersionSet } from '@ddn/types';
export declare function registryPacks(registry: Registry): readonly Pack[];
export declare function registrations(registry: Registry): PackRegistrations;
export declare function createRegistry(versions: VersionSet, onChange?: () => void): Registry;
