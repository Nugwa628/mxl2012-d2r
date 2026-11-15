# D2R Advanced Stats: the Stat Book D2RLoader plugin (statbook.dll). Build (Windows x64, MSVC):
#   cmake -S . -B build -A x64
#   cmake --build build --config Release --target statbook statbook_all_tests
#   ctest --test-dir build -C Release
# Output: build/Release/statbook.dll. The D2RLoader PluginSDK (MIT) is fetched from GitHub at the pinned commit below;
# -DSTATBOOK_PLUGINSDK_DIR=<folder> uses a local checkout instead (no download).
cmake_minimum_required(VERSION 3.29)
project(statbook LANGUAGES CXX RC)

set(STATBOOK_PLUGINSDK_DIR "" CACHE PATH "A local D2RLoader PluginSDK checkout (empty: fetch STATBOOK_PLUGINSDK_COMMIT)")
set(STATBOOK_PLUGINSDK_GIT "https://github.com/D2RLoader/PluginSDK.git" CACHE STRING "The PluginSDK repository to fetch")
set(STATBOOK_PLUGINSDK_COMMIT "717f727a0ec52912d1558764345f8fa3453a2bd6" CACHE STRING "The PluginSDK commit (SDK 0.3.0, plugin ABI 4)")
set(D2RLPLUGIN_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)   # the SDK's own tests; this project's tests are below
if(STATBOOK_PLUGINSDK_DIR)
	if(NOT EXISTS "${STATBOOK_PLUGINSDK_DIR}/CMakeLists.txt")
		message(FATAL_ERROR "STATBOOK_PLUGINSDK_DIR (${STATBOOK_PLUGINSDK_DIR}) is not a PluginSDK checkout")
	endif()
	add_subdirectory(${STATBOOK_PLUGINSDK_DIR} PluginSDK EXCLUDE_FROM_ALL)
else()
	include(FetchContent)
	FetchContent_Declare(d2rlpluginsdk GIT_REPOSITORY ${STATBOOK_PLUGINSDK_GIT} GIT_TAG ${STATBOOK_PLUGINSDK_COMMIT} EXCLUDE_FROM_ALL)
	FetchContent_MakeAvailable(d2rlpluginsdk)
endif()

# src/statbook.rc: the D2RLoader plugin manifest and the version resource (numbers from PluginVersion in src/statbook.cpp).
add_library(statbook SHARED src/statbook.cpp src/sheet_resist.cpp src/advstats.cpp src/sheet_host.cpp src/shared/panel_shared.cpp
            src/statbook.rc)
file(STRINGS src/statbook.cpp plugin_version_line REGEX "PluginVersion = \"[0-9]+[.][0-9]+[.][0-9]+\"")
if(NOT plugin_version_line MATCHES "\"([0-9]+)[.]([0-9]+)[.]([0-9]+)\"")
	message(FATAL_ERROR "PluginVersion not found in src/statbook.cpp")
endif()
set_property(SOURCE src/statbook.rc APPEND PROPERTY COMPILE_DEFINITIONS
             STATBOOK_PV_STR="${CMAKE_MATCH_1}.${CMAKE_MATCH_2}.${CMAKE_MATCH_3}" STATBOOK_PV_NUM=${CMAKE_MATCH_1},${CMAKE_MATCH_2},${CMAKE_MATCH_3},0)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS src/statbook.cpp src/default_book.inc)
target_include_directories(statbook PRIVATE src src/shared)
target_link_libraries(statbook PRIVATE D2RLPlugin::D2RLPlugin)
target_compile_features(statbook PRIVATE cxx_std_20)
d2rlplugin_embed_config(TARGET statbook FILE "${CMAKE_CURRENT_SOURCE_DIR}/statbook.toml")
if(MSVC)
	target_compile_options(statbook PRIVATE /W4 /permissive- /EHsc /utf-8)
	target_compile_definitions(statbook PRIVATE _CRT_SECURE_NO_WARNINGS)
	set_property(TARGET statbook PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")  # no VC++ runtime dependency
endif()

# Unit tests of the pure parts (no Windows headers, no game): target statbook_all_tests, then ctest.
add_subdirectory(tests)
enable_testing()
foreach(t statbook_tests statbook_config_tests statbook_sheetres_tests statbook_advstats_tests statbook_sheethost_tests)
	add_test(NAME ${t} COMMAND ${t})
endforeach()
