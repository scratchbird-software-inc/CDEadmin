/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {FileOrDir} from 'react-aspen';

export interface ITreeBranchSegment {
  kind: 'ancestor' | 'current'
  continues: boolean
  isLast: boolean
}

function siblingsOf(item: FileOrDir): FileOrDir[] {
  const siblings = item?.parent?.children;
  return Array.isArray(siblings) ? siblings : [];
}

export function isLastTreeSibling(item: FileOrDir): boolean {
  const siblings = siblingsOf(item);
  if (siblings.length === 0) {
    return true;
  }
  const last = siblings[siblings.length - 1];
  return last === item || (last?.id !== undefined && last.id === item?.id);
}

/**
 * Return one segment for each visible indentation level. Ancestor segments
 * carry vertical lines only while later siblings remain. The current segment
 * draws either a tee or an end elbow into the node's disclosure/leaf marker.
 */
export function treeBranchSegments(item: FileOrDir): ITreeBranchSegment[] {
  const visibleDepth = Math.max(0, Number(item?.depth ?? 0) - 1);
  if (visibleDepth === 0) {
    return [];
  }

  const ancestorSegments: ITreeBranchSegment[] = [];
  let ancestor = item.parent as FileOrDir;
  for (let index = 0; index < visibleDepth - 1 && ancestor; index += 1) {
    const continues = !isLastTreeSibling(ancestor);
    ancestorSegments.unshift({
      kind: 'ancestor',
      continues,
      isLast: !continues,
    });
    ancestor = ancestor.parent as FileOrDir;
  }

  const isLast = isLastTreeSibling(item);
  return [
    ...ancestorSegments,
    {kind: 'current', continues: !isLast, isLast},
  ];
}

function activeAncestorsSet(activeItem?: FileOrDir | null): Set<FileOrDir> {
  const set = new Set<FileOrDir>();
  let cur = activeItem || null;
  while (cur) {
    set.add(cur);
    cur = (cur.parent as FileOrDir) || null;
  }
  return set;
}

export function TreeBranchGuides({
  item,
  activeItem = null,
  stepX = 18,
  radius = 8,
}: {
  item: FileOrDir
  activeItem?: FileOrDir | null
  stepX?: number
  radius?: number
}) {
  const segments = treeBranchSegments(item);
  const activeSet = activeItem ? activeAncestorsSet(activeItem) : null;
  const isSelfActive = Boolean(activeItem && activeItem === item);
  const w = Math.max(12, Math.min(28, Number(stepX) || 18));
  const r = Math.max(4, Math.min(12, Number(radius) || 8));
  const h = 28;
  const cx = Math.round(w * 0.45);
  const midY = h / 2;

  return (
    <span className="tree-branch" aria-hidden="true" style={{display: 'inline-flex', alignItems: 'stretch'}}>
      {segments.map((segment, index) => {
        const elbowEnd = Math.min(w - 1, cx + r);
        const isCurrent = segment.kind === 'current';
        const showTrunkTop = isCurrent || segment.continues;
        const showTrunkBottom = segment.continues;
        const showActiveElbow = isCurrent && isSelfActive;
        const showActivePassThrough =
          !isCurrent &&
          Boolean(
            activeSet &&
              item?.parent &&
              activeSet.has(item.parent as FileOrDir) &&
              activeItem !== item.parent &&
              (activeItem?.depth ?? 0) > (item?.depth ?? 0)
          );

        return (
          <span
            key={`${segment.kind}-${index}`}
            className={[
              'tree-branch-segment',
              segment.kind,
              segment.continues ? 'continues' : '',
              segment.isLast ? 'is-last' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            style={{width: w, height: h, display: 'inline-block', flexShrink: 0, position: 'relative'}}
          >
            <svg
              width={w}
              height={h}
              viewBox={`0 0 ${w} ${h}`}
              fill="none"
              aria-hidden="true"
              style={{display: 'block', overflow: 'visible'}}
            >
              {showTrunkTop && !isCurrent && showTrunkBottom && (
                <path
                  d={`M ${cx} 0 V ${h}`}
                  stroke="var(--sr-border-default, rgba(100,116,139,0.35))"
                  strokeWidth="1.25"
                />
              )}
              {isCurrent && segment.continues && (
                <path
                  d={`M ${cx} 0 V ${h}`}
                  stroke="var(--sr-border-default, rgba(100,116,139,0.35))"
                  strokeWidth="1.25"
                />
              )}
              {isCurrent && (
                <path
                  d={`M ${cx} 0 V ${midY - r} Q ${cx} ${midY} ${elbowEnd} ${midY} H ${w}`}
                  stroke={
                    showActiveElbow
                      ? 'var(--sr-accent, #1a73e8)'
                      : 'var(--sr-border-default, rgba(100,116,139,0.4))'
                  }
                  strokeWidth={showActiveElbow ? '1.85' : '1.25'}
                  strokeLinecap="round"
                />
              )}
              {showActivePassThrough && (
                <path
                  d={`M ${cx} 0 V ${h}`}
                  stroke="var(--sr-accent, #1a73e8)"
                  strokeWidth="1.75"
                  opacity="0.7"
                />
              )}
            </svg>
          </span>
        );
      })}
    </span>
  );
}
