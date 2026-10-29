/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The alert and subscription actions (docs/en_US/bi_alerts.rst, "Actions") as
 * methods biClient.js mixes into the one BI client. `call(action, request)` is
 * the same unwrapping post the other BI methods use.
 */

const withId = (alertId, extra = {}) => ({alert_id: alertId, ...extra});

export function createAlertsClient(call) {
  return {
    alertCatalog: () => call('bi_alert_catalog'),
    schedulePreview: (schedule, count = 5) => call('bi_alert_schedule_preview', {schedule, count}),
    listAlerts: async (type, id, kind) => (await call('bi_alert_list', {
      resource_type: type, resource_id: id, ...(kind ? {kind} : {})})).items || [],
    getAlert: (alertId) => call('bi_alert_get', withId(alertId)),
    createAlert: (alert) => call('bi_alert_create', {alert}),
    updateAlert: (alertId, expectedRevision, alert) => call('bi_alert_update', withId(alertId, {
      expected_revision: expectedRevision, alert})),
    deleteAlert: (alertId) => call('bi_alert_delete', withId(alertId)),
    /** Dry run: a stored alert by id, or an unsaved definition. Nothing is sent or kept. */
    testAlert: (alertId, alert) => call('bi_alert_test', alertId ? withId(alertId) : {alert}),
    runAlertNow: (alertId) => call('bi_alert_run_now', withId(alertId)),
    muteAlert: (alertId, durationMinutes) => call('bi_alert_mute', withId(alertId, {
      duration_minutes: durationMinutes})),
    unmuteAlert: (alertId) => call('bi_alert_unmute', withId(alertId)),
    rearmAlert: (alertId) => call('bi_alert_rearm', withId(alertId)),
    pauseAlert: (alertId) => call('bi_alert_pause', withId(alertId)),
    resumeAlert: (alertId, reset = false) => call('bi_alert_resume', withId(alertId, {reset})),
    alertHistory: async (alertId, limit = 50) => (await call('bi_alert_history', withId(alertId, {limit}))).items || [],
    listNotifications: async (unreadOnly = false, limit = 50) => {
      const listing = await call('bi_notification_list', {unread_only: unreadOnly, limit});
      return {unread: listing.unread || 0, items: listing.items || []};
    },
    markNotificationsRead: (ids) => call('bi_notification_read', ids ? {ids} : {}),
  };
}
