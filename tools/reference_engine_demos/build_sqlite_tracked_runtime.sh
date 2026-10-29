#!/bin/bash
# build_sqlite_tracked_runtime.sh <version> <amalgamation-dir> <prefix>
# One build recipe for every tracked SQLite version, so runtime catalogs
# (functions, pragmas, modules) differ only by SQLite version, not by flags.
# Feature flags = the 3.53.0 reference *library's* compile options (not the
# CLI's, which configure --all builds with extras), plus JSON1
# and DESERIALIZE, which older releases need and newer releases ignore.
set -euo pipefail
version=$1; amal=$2; prefix=$3
FLAGS=(
  -DSQLITE_THREADSAFE=1 -DSQLITE_TEMP_STORE=1
  -DHAVE_ISNAN=1 -DSQLITE_DIRECT_OVERFLOW_READ
  -DSQLITE_ENABLE_CARRAY -DSQLITE_ENABLE_DBPAGE_VTAB -DSQLITE_ENABLE_DBSTAT_VTAB
  -DSQLITE_ENABLE_FTS3 -DSQLITE_ENABLE_FTS4 -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_GEOPOLY
  -DSQLITE_ENABLE_MATH_FUNCTIONS -DSQLITE_ENABLE_PERCENTILE -DSQLITE_ENABLE_PREUPDATE_HOOK
  -DSQLITE_ENABLE_RTREE -DSQLITE_ENABLE_SESSION
  -DSQLITE_ENABLE_JSON1 -DSQLITE_ENABLE_DESERIALIZE
)
mkdir -p "$prefix/lib" "$prefix/bin" "$prefix/include"
cd "$amal"
gcc -O2 -fPIC -shared "${FLAGS[@]}" sqlite3.c -o "$prefix/lib/libsqlite3.so.$version" \
    -Wl,-soname,libsqlite3.so.0 -lpthread -ldl -lm 2> "$prefix/gcc-lib.log"
ln -sf "libsqlite3.so.$version" "$prefix/lib/libsqlite3.so.0"
ln -sf "libsqlite3.so.$version" "$prefix/lib/libsqlite3.so"
gcc -O2 "${FLAGS[@]}" shell.c sqlite3.c -o "$prefix/bin/sqlite3" -lpthread -ldl -lm \
    2> "$prefix/gcc-shell.log"
cp sqlite3.h sqlite3ext.h "$prefix/include/"
printf '%s\n' "${FLAGS[@]}" > "$prefix/BUILD_FLAGS"
"$prefix/bin/sqlite3" --version
