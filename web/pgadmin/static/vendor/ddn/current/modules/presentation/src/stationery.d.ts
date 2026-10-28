import type { ProjectedRecord } from './project.js';
/** Add paper surfaces and stationery after layout. The original target, hit
 * bounds, status and text remain unchanged. Generated paint bounds include blur
 * and attachments, and the marker makes nested projection calls idempotent.
 * Existing clips remain authoritative; callers should apply to semantic frames,
 * not individual data marks or cells. */
export declare function decoratePaper(entry: ProjectedRecord): ProjectedRecord;
