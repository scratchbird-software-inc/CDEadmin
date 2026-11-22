/* Public SQLite expert index advisor API forwarding only.
 * Wraps variadic sqlite3_expert_config in a fixed-signature helper for ABI safety.
 */
#include "sqlite3.h"
#include "sqlite3expert.h"

int cdeadmin_sqlite_expert_abi(void) { return 1; }
const char *cdeadmin_sqlite3_libversion(void) { return sqlite3_libversion(); }
const char *cdeadmin_sqlite3_sourceid(void) { return sqlite3_sourceid(); }
const char *cdeadmin_sqlite3_errstr(int code) { return sqlite3_errstr(code); }
void cdeadmin_sqlite3_free(void *ptr) { sqlite3_free(ptr); }
int cdeadmin_sqlite3_open_v2(const char *path, sqlite3 **db, int flags, const char *vfs) {
  return sqlite3_open_v2(path, db, flags, vfs);
}
int cdeadmin_sqlite3_close(sqlite3 *db) { return sqlite3_close(db); }
int cdeadmin_sqlite3_enable_load_extension(sqlite3 *db, int enabled) {
  return sqlite3_enable_load_extension(db, enabled);
}
int cdeadmin_sqlite3_limit(sqlite3 *db, int category, int value) {
  return sqlite3_limit(db, category, value);
}
int cdeadmin_sqlite3_expert_set_sample(sqlite3expert *p, int sample_percent) {
  return sqlite3_expert_config(p, EXPERT_CONFIG_SAMPLE, sample_percent);
}
