/* Public SQLite RBU API forwarding only. All handles stay with the same linked
 * runtime; RBU itself remains the unmodified SQLite ext/rbu implementation.
 */
#include "sqlite3.h"
#include "sqlite3rbu.h"

int cdeadmin_sqlite_rbu_abi(void) { return 1; }
const char *cdeadmin_sqlite3_libversion(void) { return sqlite3_libversion(); }
const char *cdeadmin_sqlite3_sourceid(void) { return sqlite3_sourceid(); }
const char *cdeadmin_sqlite3_errstr(int code) { return sqlite3_errstr(code); }
void cdeadmin_sqlite3_free(void *ptr) { sqlite3_free(ptr); }
