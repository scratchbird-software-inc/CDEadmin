/* Qualification-only extension. Never installed in the application runtime. */
#include "sqlite3ext.h"
#include <string.h>
SQLITE_EXTENSION_INIT1
static void probe(sqlite3_context *context, int argc, sqlite3_value **argv) {
  sqlite3_result_text(context, "native extension: \xe9\x9b\xaa", -1, SQLITE_STATIC);
}
#ifdef _WIN32
__declspec(dllexport)
#endif
int sqlite3_extension_init(sqlite3 *db, char **error, const sqlite3_api_routines *api) {
  SQLITE_EXTENSION_INIT2(api);
  char *message = 0;
  int guarded = sqlite3_exec(db, "SELECT load_extension('cde_must_never_load')", 0, 0, &message);
  int disabled = guarded == SQLITE_ERROR && message && strcmp(message, "not authorized") == 0;
  sqlite3_free(message);
  if (!disabled) {
    *error = sqlite3_mprintf("SQL extension loading was enabled during native initialization");
    return SQLITE_ERROR;
  }
  int rc = sqlite3_create_function(db, "cde_native_probe", 0, SQLITE_UTF8 | SQLITE_DETERMINISTIC, 0, probe, 0, 0);
#ifdef CDE_PROBE_PARTIAL_FAILURE
  if (rc == SQLITE_OK) {
    *error = sqlite3_mprintf("Qualification failure after registering a native function");
    return SQLITE_ERROR;
  }
#endif
  return rc;
}
