# Stat Book D2RLoader plugin (docs/statbook.md). Build: cmake -S statbook -B build/statbook -A x64
# -DSTATBOOK_PLUGINSDK_DIR=<sdk> && cmake --build build/statbook --config Release (tools/build_plugin.ps1 does both).
# Output: build/statbook/Release/statbook.dll. Shares panel_shared.cpp and block_rate_logic.h with mxl2012-core (../plugin/src).
cmake_minimum_required(VERSION 3.29)
project(statbook LANGUAGES CXX RC)

set(STATBOOK_PLUGINSDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/PluginSDK" CACHE PATH "D2RLoader PluginSDK source folder")
if(NOT EXISTS "${STATBOOK_PLUGINSDK_DIR}/CMakeLists.txt")
	message(FATAL_ERROR "Set STATBOOK_PLUGINSDK_DIR to a D2RLoader PluginSDK checkout")
endif()
set(D2RLPLUGIN_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory(${STATBOOK_PLUGINSDK_DIR} PluginSDK EXCLUDE_FROM_ALL)

# src/statbook.rc: the D2RLoader plugin manifest and the version resource (numbers from PluginVersion in src/statbook.cpp).
add_library(statbook SHARED src/statbook.cpp src/sheet_resist.cpp src/advstats.cpp src/sheet_host.cpp ../plugin/src/panel_shared.cpp src/statbook.rc)
file(STRINGS src/statbook.cpp plugin_version_line REGEX "PluginVersion = \"[0-9]+[.][0-9]+[.][0-9]+\"")
if(NOT plugin_version_line MATCHES "\"([0-9]+)[.]([0-9]+)[.]([0-9]+)\"")
	message(FATAL_ERROR "PluginVersion not found in src/statbook.cpp")
endif()
set_property(SOURCE src/statbook.rc APPEND PROPERTY COMPILE_DEFINITIONS
             STATBOOK_PV_STR="${CMAKE_MATCH_1}.${CMAKE_MATCH_2}.${CMAKE_MATCH_3}" STATBOOK_PV_NUM=${CMAKE_MATCH_1},${CMAKE_MATCH_2},${CMAKE_MATCH_3},0)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS src/statbook.cpp src/default_book.inc)
target_include_directories(statbook PRIVATE src ../plugin/src)
target_link_libraries(statbook PRIVATE D2RLPlugin::D2RLPlugin)
target_compile_features(statbook PRIVATE cxx_std_20)
d2rlplugin_embed_config(TARGET statbook FILE "${CMAKE_CURRENT_SOURCE_DIR}/statbook.toml")
if(MSVC)
	target_compile_options(statbook PRIVATE /W4 /permissive- /EHsc /utf-8)
	target_compile_definitions(statbook PRIVATE _CRT_SECURE_NO_WARNINGS)
	set_property(TARGET statbook PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")  # no VC++ runtime dependency
endif()

# Test builds only (tools/build_plugin.ps1 builds them into build/statbook-test, never packaged): the cut-down test harness
# of D2R-Legacy169 so game_ctl.py can drive plain D2R without mxl2012-core. Off in the player build.
option(STATBOOK_TEST_HARNESS "Build the test harness into statbook.dll (dev only)" OFF)
if(STATBOOK_TEST_HARNESS)
	target_sources(statbook PRIVATE src/testharness.cpp)
	target_compile_definitions(statbook PRIVATE STATBOOK_TEST_HARNESS)
endif()

add_subdirectory(tests)
