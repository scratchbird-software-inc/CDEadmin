import type { CommandService, TaskOptions } from '@ddn/types';
import { type CommandHistoryGroup } from '../../runtime/src/commands.js';
export declare const LIVE_SETTINGS_CHANGE = "ddn-settings-change";
export interface LiveSettingsState {
    readonly busy: boolean;
    readonly changed: boolean;
    readonly current: boolean;
    readonly error?: unknown;
}
export interface LiveSettingsOptions {
    readonly body: HTMLElement;
    readonly commands: CommandService;
    /** Read current controls synchronously before the first await. */
    readonly submit: () => Promise<void>;
    readonly showError: (error: unknown) => void;
    readonly onState?: (state: LiveSettingsState) => void;
    readonly afterRevert?: () => void | Promise<void>;
}
export interface LiveSettings {
    readonly group: CommandHistoryGroup;
    request(): void;
    flush(): Promise<void>;
    revert(): Promise<void>;
    /** Keep the last valid changes on user dismissal; drain pending work first. */
    finish(): Promise<void>;
    /** Abort on host teardown/new document; no queued edits can reach the new model. */
    dispose(): void;
}
/** Programmatic sample buttons use the same route as sliders and text controls. */
export declare function notifyLiveSettings(body: HTMLElement): void;
/** Editors flush before changing the meaning/target of their controls. */
export declare function flushLiveSettings(body: HTMLElement): Promise<void>;
/** Save may stop waiting without cancelling the user's independent live edit. */
export declare function waitForSettingsSave(flush: () => Promise<void>, task?: TaskOptions): Promise<TaskOptions>;
/** A single bounded queue per editor. A slider replaces queued values, not undo history. */
export declare function createLiveSettings(options: LiveSettingsOptions): LiveSettings;
