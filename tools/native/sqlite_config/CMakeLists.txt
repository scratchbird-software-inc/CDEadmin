cmake_minimum_required(VERSION 3.20)
project(cdeadmin_sqlite_configuration LANGUAGES C)
find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(SQLite3 3.53.0 REQUIRED)
# Build with the reference headers for every named signature. Only public
# functions present at the3.35.0 runtime floor are linked; newer opcodes are
# queried natively and may be unavailable on older runtimes.
Python3_add_library(_cdeadmin_dbconfig MODULE WITH_SOABI api.c)
target_link_libraries(_cdeadmin_dbconfig PRIVATE SQLite::SQLite3)
target_compile_definitions(_cdeadmin_dbconfig PRIVATE SQLITE_CORE)
target_compile_features(_cdeadmin_dbconfig PRIVATE c_std_11)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(_cdeadmin_dbconfig PRIVATE -Wall -Wextra -Werror=implicit-function-declaration -Werror=int-conversion)
endif()
if(WIN32)
  target_compile_definitions(_cdeadmin_dbconfig PRIVATE "SQLITE_API=__declspec(dllimport)")
endif()
if(APPLE)
  set_target_properties(_cdeadmin_dbconfig PROPERTIES INSTALL_RPATH "@loader_path")
elseif(UNIX)
  set_target_properties(_cdeadmin_dbconfig PROPERTIES INSTALL_RPATH "$ORIGIN")
endif()
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/sqlite-config-build.json"
 CONTENT "{\"adapter_abi\":1,\"native_configuration_revision\":1,\"minimum_runtime\":\"3.35.0\",\"header_version\":\"${SQLite3_VERSION}\",\"python_version\":\"${Python3_VERSION}\",\"python_soabi\":\"${Python3_SOABI}\",\"implementation\":\"public SQLite db_config; staged original native open\"}\n")
add_custom_command(TARGET _cdeadmin_dbconfig POST_BUILD
 COMMAND "${CMAKE_COMMAND}" "-DLIBRARY=$<TARGET_FILE:_cdeadmin_dbconfig>"
 "-DTEMPLATE=${CMAKE_CURRENT_BINARY_DIR}/sqlite-config-build.json"
 -P "${CMAKE_CURRENT_SOURCE_DIR}/../sqlite_recovery/provenance.cmake" VERBATIM)
install(TARGETS _cdeadmin_dbconfig LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
if(WIN32)
 install(FILES "$<TARGET_FILE:_cdeadmin_dbconfig>.json" DESTINATION bin)
else()
 install(FILES "$<TARGET_FILE:_cdeadmin_dbconfig>.json" DESTINATION lib)
endif()
