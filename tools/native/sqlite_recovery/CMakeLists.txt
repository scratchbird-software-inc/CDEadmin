cmake_minimum_required(VERSION 3.20)
project(cdeadmin_sqlite_recovery LANGUAGES C)

# Build against a supplied, unmodified SQLite source distribution. SQLite owns
# the recovery implementation; this target only exposes its public recovery API.
set(SCRATCHROBIN_SQLITE_SOURCE "" CACHE PATH "SQLite 3.53.0 source directory")
set(recovery_source "${SCRATCHROBIN_SQLITE_SOURCE}/ext/recover")
foreach(name sqlite3recover.c sqlite3recover.h dbdata.c)
  if(NOT EXISTS "${recovery_source}/${name}")
    message(FATAL_ERROR "SCRATCHROBIN_SQLITE_SOURCE must contain ext/recover/${name}")
  endif()
endforeach()
# Owner direction 2026-10-29: SQLite from the 3.35.0 floor; the helper
# refuses at load time any runtime older than the headers it was built with.
find_package(SQLite3 3.35.0 REQUIRED)
add_library(cdeadmin_sqlite_recovery SHARED
  "${recovery_source}/sqlite3recover.c" "${recovery_source}/dbdata.c" api.c)
target_include_directories(cdeadmin_sqlite_recovery PRIVATE "${recovery_source}")
target_compile_definitions(cdeadmin_sqlite_recovery PRIVATE SQLITE_CORE)
target_link_libraries(cdeadmin_sqlite_recovery PRIVATE SQLite::SQLite3)
# An API newer than the build headers must fail the build, not leave an
# unresolved symbol (or an int-sized pointer) for load time.
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(cdeadmin_sqlite_recovery PRIVATE -Werror=implicit-function-declaration -Werror=int-conversion)
endif()
set_target_properties(cdeadmin_sqlite_recovery PROPERTIES
  C_STANDARD 99 WINDOWS_EXPORT_ALL_SYMBOLS ON)
if(APPLE)
  set_target_properties(cdeadmin_sqlite_recovery PROPERTIES INSTALL_RPATH "@loader_path")
elseif(UNIX)
  set_target_properties(cdeadmin_sqlite_recovery PROPERTIES INSTALL_RPATH "$ORIGIN")
endif()
set(expected_sqlite3recover_c bc56c1131dfdc979fd93a7e013856f4c2a98570c722c069600f6c66d2d47743f)
set(expected_sqlite3recover_h c088088d15af055304e931842f7c197024d46ff1b7077912ec42149e9fa4f9bb)
set(expected_dbdata_c 0a57eae22b51507c28f6c647fba00ccacd39b5aaf3393dfe9435fb04810a6e0e)
foreach(name sqlite3recover.c sqlite3recover.h dbdata.c)
  file(SHA256 "${recovery_source}/${name}" source_sha)
  string(REPLACE "." "_" key "${name}")
  if(NOT source_sha STREQUAL expected_${key})
    message(FATAL_ERROR "${name} differs from the qualified SQLite 3.53.0 recovery source")
  endif()
  string(APPEND provenance "\"${name}\":\"${source_sha}\",")
endforeach()
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/sqlite-recovery-build.json"
  CONTENT "{\"sqlite_version\":\"${SQLite3_VERSION}\",\"adapter_abi\":1,${provenance}\"implementation\":\"SQLite public recovery API\"}\n")
add_custom_command(TARGET cdeadmin_sqlite_recovery POST_BUILD
  COMMAND "${CMAKE_COMMAND}" "-DLIBRARY=$<TARGET_FILE:cdeadmin_sqlite_recovery>"
    "-DTEMPLATE=${CMAKE_CURRENT_BINARY_DIR}/sqlite-recovery-build.json"
    -P "${CMAKE_CURRENT_SOURCE_DIR}/provenance.cmake" VERBATIM)
install(TARGETS cdeadmin_sqlite_recovery LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
if(WIN32)
  install(FILES "$<TARGET_FILE:cdeadmin_sqlite_recovery>.json" DESTINATION bin)
else()
  install(FILES "$<TARGET_FILE:cdeadmin_sqlite_recovery>.json" DESTINATION lib)
endif()
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/sqlite-recovery-build.json" DESTINATION share/cdeadmin)
