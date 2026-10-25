/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Descriptor-driven object editing (design: docs/en_US/ui_unified_design.rst,
 * phase 2). Everything here is engine-agnostic; engines are described by
 * web/pgadmin/cdeadmin/ui_descriptors/<engine>/.
 */

export {default as ObjectEditor, planSqlText} from './ObjectEditor';
export {default as OperationDialog} from './OperationDialog';
export {
  default as ProviderObjectEditorHost, makePost, recordFromResource, resourceNative,
} from './ProviderObjectEditorHost';
export {default as FieldControl, fieldHelpText} from './FieldControl';
export {default as RecordGrid} from './RecordGrid';
export {default as KeyValueEditor} from './KeyValueEditor';
export {
  DescriptorClient, descriptorClient, resetDescriptorClient, visualAdminCalls,
} from './DescriptorClient';
export {
  MENU_CATEGORIES,
  SHELL_PRIMITIVES,
  activeFields,
  buildOptionContext,
  diffColumns,
  editorAvailable,
  fieldOptions,
  fieldVisible,
  formForKind,
  initialDraft,
  menuForKind,
  resolveBundle,
  resolveForm,
  toBackendDraft,
  validateDraft,
} from './descriptors';
