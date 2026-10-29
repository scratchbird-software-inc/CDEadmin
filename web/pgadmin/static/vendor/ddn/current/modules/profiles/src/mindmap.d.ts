/** Mind-map membership is local to a view, not a global property of a definition. */
export interface MindmapRecord {
    readonly file: string;
    readonly ref: {
        readonly id: string;
    };
    readonly record: Readonly<Record<string, unknown>>;
}
export declare function isMindmapTopic(record: Readonly<Record<string, unknown>>): boolean;
export declare function mindmapKey(record: Pick<MindmapRecord, 'file' | 'ref'>): string;
export type MindmapRelationKind = 'internal' | 'external' | 'unrelated' | 'unresolved';
/** topicKeys contains only the selected topic definitions in this view. */
export declare function mindmapRelationKind(from: MindmapRecord | undefined, to: MindmapRecord | undefined, topicKeys: ReadonlySet<string>): MindmapRelationKind;
