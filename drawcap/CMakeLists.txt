# drawcap D2RLoader plugin (README.md). Build: cmake -S drawcap -B build/drawcap -A x64 -DDRAWCAP_PLUGINSDK_DIR=<sdk> &&
# cmake --build build/drawcap --config Release (tools/build_plugin.ps1 does both). Output: build/drawcap/Release/drawcap.dll.
# Needs only the D2RLoader PluginSDK; nothing of the mod or of mxl2012-core.
cmake_minimum_required(VERSION 3.29)
project(drawcap LANGUAGES CXX RC)

set(DRAWCAP_PLUGINSDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/PluginSDK" CACHE PATH "D2RLoader PluginSDK source folder")
if(NOT EXISTS "${DRAWCAP_PLUGINSDK_DIR}/CMakeLists.txt")
	message(FATAL_ERROR "Set DRAWCAP_PLUGINSDK_DIR to a D2RLoader PluginSDK checkout")
endif()
set(D2RLPLUGIN_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory(${DRAWCAP_PLUGINSDK_DIR} PluginSDK EXCLUDE_FROM_ALL)

# src/drawcap.rc: the D2RLoader plugin manifest (required, the loader rejects the DLL without it) and the version resource,
# whose numbers come from PluginVersion in src/drawcap.cpp.
add_library(drawcap SHARED src/drawcap.cpp src/drawcap.rc)
file(STRINGS src/drawcap.cpp plugin_version_line REGEX "PluginVersion = \"[0-9]+[.][0-9]+[.][0-9]+\"")
if(NOT plugin_version_line MATCHES "\"([0-9]+)[.]([0-9]+)[.]([0-9]+)\"")
	message(FATAL_ERROR "PluginVersion not found in src/drawcap.cpp")
endif()
set_property(SOURCE src/drawcap.rc APPEND PROPERTY COMPILE_DEFINITIONS
             DRAWCAP_PV_STR="${CMAKE_MATCH_1}.${CMAKE_MATCH_2}.${CMAKE_MATCH_3}" DRAWCAP_PV_NUM=${CMAKE_MATCH_1},${CMAKE_MATCH_2},${CMAKE_MATCH_3},0)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS src/drawcap.cpp)
target_link_libraries(drawcap PRIVATE D2RLPlugin::D2RLPlugin)
target_compile_features(drawcap PRIVATE cxx_std_20)
d2rlplugin_embed_config(TARGET drawcap FILE "${CMAKE_CURRENT_SOURCE_DIR}/drawcap.toml")
if(MSVC)
	target_compile_options(drawcap PRIVATE /W4 /permissive- /EHsc /utf-8)
	set_property(TARGET drawcap PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")  # no VC++ runtime dependency
endif()

# Unit tests of the pure part (no game, no Windows headers): build/drawcap/tests/Release/drawcap_tests.exe
add_subdirectory(tests)
