/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

export {
  DDN_DESIGNER_VERSION,
  DDN_RUNTIME_VERSION,
  loadDDNLibraries,
  resetDDNLibraryLoaderForTests,
  setDDNLibraryLoaderForTests,
} from './library.js';
export {
  DDN_ASSET_SCHEMA,
  DDN_SNAPSHOT_FORMATS,
  DDN_SURFACE_SCHEMA,
  ddnAssetPayload,
  validateDDNAssetRef,
  validateDDNFiles,
  validateDDNSnapshot,
} from './contracts.js';
export {
  DDN_PERSISTENCE_STATES,
  DDNSessionController,
} from './DDNSessionController.js';
export {DDNViewerSurface} from './DDNViewerSurface';
export {DDNDesignerSurface} from './DDNDesignerSurface';
export {
  DDN_MODULE_ID,
  PROJECT_ASSET_SERVICE_ID,
  ddnModuleDefinition,
  registerDDNModule,
} from './module.js';
export {
  DESIGN_KINDS,
  DESIGN_SAVE_POINTS,
  DesignStoreClient,
  DesignStoreClientError,
  ERD_MODELLING_LEVELS,
  SharedDDNTaskController,
} from './sharedDesignLibrary.js';
export {ERDDesignerSurface} from './ERDDesignerSurface';
export {
  ERD_MODEL_CREATE_EVENT,
  ERD_MODEL_OPEN_EVENT,
  ERDModelsNavigator,
  openERDModel,
  requestERDModelCreate,
} from './ERDModelsNavigator';
export {
  DESIGN_STORE_SERVICE_ID,
  ERD_DESIGN_ASSET_TYPE,
  ERD_MODULE_ID,
  erdModuleDefinition,
  registerERDModule,
} from './erdModule.js';
