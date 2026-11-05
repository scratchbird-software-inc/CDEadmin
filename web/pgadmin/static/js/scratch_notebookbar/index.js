/////////////////////////////////////////////////////////////
//
// Scratch notebook bar
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Public API; see README.md. Nothing here imports from the host application.

export {NotebookBar} from './NotebookBar';
export {NotebookBarCustomizer} from './NotebookBarCustomizer';
export {
  CONTROL_TYPES, CUSTOMIZATION_SCHEMA, applyCustomization, emptyCustomization,
  flattenControls, isControlEnabled, isControlVisible, isGroupVisible,
  mergeContributions, normalizeModel, visibleTabs,
} from './model';
export {assignAccessKeys, foldGroups, matchAccessKey} from './layout';
export {NOTEBOOKBAR_CSS, useNotebookBarStyles} from './styles';
export {DEFAULT_MESSAGES} from './messages';
