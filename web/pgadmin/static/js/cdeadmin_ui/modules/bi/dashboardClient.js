/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The bi_dashboard_* actions (docs/en_US/bi_dashboards.rst, "Actions") and
 * the stored-question run a drill-through needs, as methods that biClient.js
 * mixes into the one BI client. `call(action, request)` is the same
 * unwrapping post the question methods use.
 */

const present = (value) => value && Object.keys(value).length > 0;

export function createDashboardClient(call) {
  return {
    listDashboards: async () => (await call('bi_dashboard_list')).items || [],
    getDashboard: (dashboardId) => call('bi_dashboard_get', {dashboard_id: dashboardId}),
    createDashboard: (dashboard) => call('bi_dashboard_create', {dashboard}),
    updateDashboard: (dashboardId, expectedRevision, dashboard) => call('bi_dashboard_update',
      {dashboard_id: dashboardId, expected_revision: expectedRevision, dashboard}),
    setDashboardStatus: (dashboardId, expectedRevision, status) => call('bi_dashboard_status',
      {dashboard_id: dashboardId, expected_revision: expectedRevision, status}),
    moveDashboard: (dashboardId, expectedRevision, collectionId) => call('bi_dashboard_move',
      {dashboard_id: dashboardId, expected_revision: expectedRevision, collection_id: collectionId}),
    cloneDashboard: (dashboardId, name) => call('bi_dashboard_clone', {dashboard_id: dashboardId, name}),
    dashboardHistory: async (dashboardId) => (await call('bi_dashboard_history',
      {dashboard_id: dashboardId})).items || [],
    dashboardRevision: (dashboardId, revision) => call('bi_dashboard_revision',
      {dashboard_id: dashboardId, revision}),

    /** One question card with the current filter values; `exclude` lists {card_id, filter_id} pairs. */
    runDashboardCard: (dashboardId, cardId, {filters, exclude, pageSize, bypassCache = false} = {}) =>
      call('bi_dashboard_card_run', {
        dashboard_id: dashboardId, card_id: cardId,
        ...(present(filters) ? {filters} : {}),
        ...(exclude?.length ? {exclude} : {}),
        ...(pageSize ? {page_size: pageSize} : {}),
        ...(bypassCache ? {bypass_cache: true} : {}),
      }),
    crossFilter: (dashboardId, crossFilterId, row, filters) => call('bi_dashboard_cross_filter', {
      dashboard_id: dashboardId, cross_filter_id: crossFilterId, row,
      ...(present(filters) ? {filters} : {}),
    }),
    drill: (dashboardId, drillId, row, filters) => call('bi_dashboard_drill', {
      dashboard_id: dashboardId, drill_id: drillId, row,
      ...(present(filters) ? {filters} : {}),
    }),

    /** Monitoring (DDN) snapshot to dashboard document: {dashboard, loss}. */
    dashboardFromDdn: (snapshot, name) => call('bi_dashboard_from_ddn', {
      snapshot, ...(name ? {name} : {}),
    }),

    /** A drill-through into a pinned stored question. */
    executeStored: (questionId, revision, {parameters, pageSize, bypassCache = false} = {}) =>
      call('bi_question_execute', {
        question_id: questionId, revision,
        ...(present(parameters) ? {parameters} : {}),
        ...(pageSize ? {page_size: pageSize} : {}),
        ...(bypassCache ? {bypass_cache: true} : {}),
      }),
  };
}
