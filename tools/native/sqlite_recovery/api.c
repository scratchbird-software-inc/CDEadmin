/* Public SQLite API forwarding only. All handles stay with the same linked
 * runtime, including on Windows where GetProcAddress does not search a DLL's
 * dependencies. Recovery itself remains the unmodified SQLite implementation.
 */
#include "sqlite3.h"

int cdeadmin_sqlite_recovery_abi(void) { return 1; }
const char *cdeadmin_sqlite3_libversion(void) { return sqlite3_libversion(); }
const char *cdeadmin_sqlite3_sourceid(void) { return sqlite3_sourceid(); }
const char *cdeadmin_sqlite3_errstr(int code) { return sqlite3_errstr(code); }
int cdeadmin_sqlite3_compileoption_used(const char *name) { return sqlite3_compileoption_used(name); }
int cdeadmin_sqlite3_open_v2(const char *path, sqlite3 **db, int flags, const char *vfs) {
  return sqlite3_open_v2(path, db, flags, vfs);
}
int cdeadmin_sqlite3_close(sqlite3 *db) { return sqlite3_close(db); }
int cdeadmin_sqlite3_auto_extension(void (*entry)(void)) { return sqlite3_auto_extension(entry); }
int cdeadmin_sqlite3_set_authorizer(sqlite3 *db,
  int (*callback)(void *, int, const char *, const char *, const char *, const char *), void *context) {
  return sqlite3_set_authorizer(db, callback, context);
}
const char *cdeadmin_sqlite3_db_filename(sqlite3 *db, const char *name) { return sqlite3_db_filename(db, name); }
int cdeadmin_sqlite3_enable_load_extension(sqlite3 *db, int enabled) { return sqlite3_enable_load_extension(db, enabled); }
int cdeadmin_sqlite3_limit(sqlite3 *db, int category, int value) { return sqlite3_limit(db, category, value); }
