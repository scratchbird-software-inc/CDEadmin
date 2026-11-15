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
  stepX = 20,
  radius = 8,
  hasToggle = false,
}: {
  item: FileOrDir
  activeItem?: FileOrDir | null
  stepX?: number
  radius?: number
  hasToggle?: boolean
}) {
  const segments = treeBranchSegments(item);
  const activeSet = activeItem ? activeAncestorsSet(activeItem) : null;
  const isSelfActive = Boolean(activeItem && activeItem === item);
  const w = Math.max(18, Math.min(28, Number(stepX) || 20));
  const cx = Math.round(w / 2);
  const r = Math.max(4, Math.min(cx - 1, Number(radius) || 8));
  const h = 28;
  const midY = h / 2;
  const circleRadius = 8;
  const guideStroke = 'var(--sr-tree-guide, rgba(71, 85, 105, 0.78))';
  const activeStroke = 'var(--sr-accent, #0f62fe)';
  const strokeWidth = 2.2;
  const activeStrokeWidth = 2.5;

  // Build ancestor chain per visible segment column so active trace highlights only real ancestors.
  const ancestorsByColumn: (FileOrDir | null)[] = [];
  if (segments.length > 0) {
    let cursor = (item?.parent as FileOrDir) || null;
    for (let idx = 0; idx < segments.length; idx += 1) {
      ancestorsByColumn.unshift(cursor);
      cursor = (cursor?.parent as FileOrDir) || null;
    }
  }

  return (
    <span className="tree-branch" aria-hidden="true" style={{display: 'inline-flex', alignItems: 'stretch', height: h}}>
      {segments.map((segment, index) => {
        const isCurrent = segment.kind === 'current';
        const showTrunkTop = isCurrent || segment.continues;
        const showTrunkBottom = segment.continues;
        const showActiveElbow = isCurrent && isSelfActive;
        const columnAncestor = ancestorsByColumn[index];
        const showActivePassThrough =
          !isCurrent &&
          showTrunkBottom &&
          Boolean(
            activeSet &&
              columnAncestor &&
              activeSet.has(columnAncestor) &&
              activeItem !== columnAncestor &&
              (activeItem?.depth ?? 0) > (item?.depth ?? 0)
          );

        // When the row has a circular (+/-) toggle in the next `w`-wide slot, its circle
        // has radius `circleRadius` centered at `w + cx`, so its left border is at
        // `w + cx - circleRadius`. Extending 1px inside the 2px circle border fuses
        // the curved line seamlessly to the circle with zero gap at any zoom.
        // When the row has no children (`!hasToggle`), end cleanly right before the icon.
        const horizEnd = hasToggle
          ? w + Math.max(0, cx - circleRadius) + 1
          : w + 1;
        const elbowCornerEnd = Math.min(horizEnd, cx + r);
        const currentColor = showActiveElbow ? activeStroke : guideStroke;
        const currentWidth = showActiveElbow ? activeStrokeWidth : strokeWidth;

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
              style={{display: 'block', overflow: 'visible', pointerEvents: 'none'}}
            >
              {showTrunkTop && !isCurrent && showTrunkBottom && (
                <path
                  d={`M ${cx} 0 V ${h}`}
                  stroke={guideStroke}
                  strokeWidth={strokeWidth}
                  strokeLinecap="butt"
                />
              )}
              {isCurrent && segment.continues && (
                <path
                  d={`M ${cx} 0 V ${h}`}
                  stroke={guideStroke}
                  strokeWidth={strokeWidth}
                  strokeLinecap="butt"
                />
              )}
              {isCurrent && (
                <>
                  <path
                    d={`M ${cx} 0 V ${midY - r} Q ${cx} ${midY} ${elbowCornerEnd} ${midY} H ${horizEnd}`}
                    stroke={currentColor}
                    strokeWidth={currentWidth}
                    strokeLinecap="butt"
                    strokeLinejoin="round"
                  />
                  {!hasToggle && (
                    <circle
                      cx={horizEnd}
                      cy={midY}
                      r={currentWidth / 2}
                      fill={currentColor}
                    />
                  )}
                </>
              )}
              {showActivePassThrough && (
                <path
                  d={`M ${cx} 0 V ${h}`}
                  stroke={activeStroke}
                  strokeWidth={activeStrokeWidth}
                  strokeLinecap="butt"
                  opacity="0.82"
                />
              )}
            </svg>
          </span>
        );
      })}
    </span>
  );
}
