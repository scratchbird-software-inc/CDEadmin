/* Public SQLite incremental integrity-check API forwarding only. */
#include "sqlite3.h"
#include "sqlite3intck.h"

int cdeadmin_sqlite_intck_abi(void) { return 1; }
const char *cdeadmin_sqlite3_libversion(void) { return sqlite3_libversion(); }
const char *cdeadmin_sqlite3_sourceid(void) { return sqlite3_sourceid(); }
const char *cdeadmin_sqlite3_errstr(int code) { return sqlite3_errstr(code); }
int cdeadmin_sqlite3_open_v2(const char *path, sqlite3 **db, int flags, const char *vfs) {
  return sqlite3_open_v2(path, db, flags, vfs);
}
int cdeadmin_sqlite3_close(sqlite3 *db) { return sqlite3_close(db); }
int cdeadmin_sqlite3_enable_load_extension(sqlite3 *db, int enabled) {
  return sqlite3_enable_load_extension(db, enabled);
}
int cdeadmin_sqlite3_scalar_int(sqlite3 *db, const char *sql, int *out_val) {
  sqlite3_stmt *stmt = 0;
  int rc = sqlite3_prepare_v2(db, sql, -1, &stmt, 0);
  if (rc != SQLITE_OK) return rc;
  rc = sqlite3_step(stmt);
  if (rc == SQLITE_ROW && out_val) {
    *out_val = sqlite3_column_int(stmt, 0);
    rc = SQLITE_OK;
  } else if (rc == SQLITE_DONE) {
    rc = SQLITE_OK;
  }
  sqlite3_finalize(stmt);
  return rc;
}
