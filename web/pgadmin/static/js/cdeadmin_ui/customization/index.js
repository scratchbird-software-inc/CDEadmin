export * from './appearance';
export * from './profile';

export const APPEARANCE_PREFERENCES_ID = 'cde-appearance';
export const DESIGNER_PREFERENCES_ID = 'cde-designer';

export function requestPreferencesSection(sectionId, target = typeof window !== 'undefined' ? window : null) {
  if (!target?.dispatchEvent) return;
  target.dispatchEvent(
    new CustomEvent('scratchrobin:open-preferences', {
      detail: {mode: 'user', sectionId: sectionId || null},
    })
  );
}
