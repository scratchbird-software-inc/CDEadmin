cmake_minimum_required(VERSION 3.20)
project(cdeadmin_sqlite_preupdate LANGUAGES C)
# Owner direction 2026-10-29: SQLite from the 3.35.0 floor; the helper
# refuses at load time any runtime older than the headers it was built with.
find_package(SQLite3 3.35.0 REQUIRED)
add_library(cdeadmin_sqlite_preupdate SHARED api.c)
target_link_libraries(cdeadmin_sqlite_preupdate PRIVATE SQLite::SQLite3)
target_compile_definitions(cdeadmin_sqlite_preupdate PRIVATE SQLITE_CORE SQLITE_ENABLE_PREUPDATE_HOOK)
# An API newer than the build headers must fail the build, not leave an
# unresolved symbol (or an int-sized pointer) for load time.
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(cdeadmin_sqlite_preupdate PRIVATE -Werror=implicit-function-declaration -Werror=int-conversion)
endif()
set_target_properties(cdeadmin_sqlite_preupdate PROPERTIES C_STANDARD 99 WINDOWS_EXPORT_ALL_SYMBOLS ON)
if(WIN32)
  target_compile_definitions(cdeadmin_sqlite_preupdate PRIVATE "SQLITE_API=__declspec(dllimport)")
endif()
if(APPLE)
  set_target_properties(cdeadmin_sqlite_preupdate PROPERTIES INSTALL_RPATH "@loader_path")
elseif(UNIX)
  set_target_properties(cdeadmin_sqlite_preupdate PROPERTIES INSTALL_RPATH "$ORIGIN")
endif()
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/sqlite-preupdate-build.json"
  CONTENT "{\"adapter_abi\":1,\"sqlite_version\":\"${SQLite3_VERSION}\",\"implementation\":\"SQLite public native preupdate APIs\"}\n")
add_custom_command(TARGET cdeadmin_sqlite_preupdate POST_BUILD
  COMMAND "${CMAKE_COMMAND}" "-DLIBRARY=$<TARGET_FILE:cdeadmin_sqlite_preupdate>"
    "-DTEMPLATE=${CMAKE_CURRENT_BINARY_DIR}/sqlite-preupdate-build.json"
    -P "${CMAKE_CURRENT_SOURCE_DIR}/../sqlite_recovery/provenance.cmake" VERBATIM)
install(TARGETS cdeadmin_sqlite_preupdate LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
if(WIN32)
  install(FILES "$<TARGET_FILE:cdeadmin_sqlite_preupdate>.json" DESTINATION bin)
else()
  install(FILES "$<TARGET_FILE:cdeadmin_sqlite_preupdate>.json" DESTINATION lib)
endif()
