# invtabs D2RLoader plugin (README.md, docs/invtabs.md). Build: cmake -S invtabs -B build/invtabs -A x64
# -DINVTABS_PLUGINSDK_DIR=<sdk> && cmake --build build/invtabs --config Release (tools/build_plugin.ps1 does both).
# Output: build/invtabs/Release/invtabs.dll. Needs only the D2RLoader PluginSDK; nothing of the mod or of mxl2012-core.
cmake_minimum_required(VERSION 3.29)
project(invtabs LANGUAGES CXX RC)

set(INVTABS_PLUGINSDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/PluginSDK" CACHE PATH "D2RLoader PluginSDK source folder")
if(NOT EXISTS "${INVTABS_PLUGINSDK_DIR}/CMakeLists.txt")
	message(FATAL_ERROR "Set INVTABS_PLUGINSDK_DIR to a D2RLoader PluginSDK checkout")
endif()
set(D2RLPLUGIN_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory(${INVTABS_PLUGINSDK_DIR} PluginSDK EXCLUDE_FROM_ALL)

# src/invtabs.rc: the D2RLoader plugin manifest (required, the loader rejects the DLL without it) and the version resource,
# whose numbers come from PluginVersion in src/invtabs.cpp.
add_library(invtabs SHARED src/invtabs.cpp src/mp_protocol.cpp src/pad_route.cpp src/summary.cpp src/invtabs.rc)
file(STRINGS src/invtabs.cpp plugin_version_line REGEX "PluginVersion = \"[0-9]+[.][0-9]+[.][0-9]+\"")
if(NOT plugin_version_line MATCHES "\"([0-9]+)[.]([0-9]+)[.]([0-9]+)\"")
	message(FATAL_ERROR "PluginVersion not found in src/invtabs.cpp")
endif()
set_property(SOURCE src/invtabs.rc APPEND PROPERTY COMPILE_DEFINITIONS
             INVTABS_PV_STR="${CMAKE_MATCH_1}.${CMAKE_MATCH_2}.${CMAKE_MATCH_3}" INVTABS_PV_NUM=${CMAKE_MATCH_1},${CMAKE_MATCH_2},${CMAKE_MATCH_3},0)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS src/invtabs.cpp)
target_link_libraries(invtabs PRIVATE D2RLPlugin::D2RLPlugin)
target_compile_features(invtabs PRIVATE cxx_std_20)
# The default config (one file, its schema in docs/invtabs-data.md); installed as d2rloader/config/invtabs.toml.
set(invtabs_toml "${CMAKE_CURRENT_SOURCE_DIR}/invtabs.toml")
d2rlplugin_embed_config(TARGET invtabs FILE "${invtabs_toml}")
if(MSVC)
	target_compile_options(invtabs PRIVATE /W4 /permissive- /EHsc /utf-8)
	set_property(TARGET invtabs PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")  # no VC++ runtime dependency
endif()

# Unit tests of the pure part (no game, no Windows headers): build/invtabs/tests/Release/invtabs_tests.exe
add_subdirectory(tests)
# The controller tab's route and layout (needs the PluginSDK headers): build/invtabs/Release/invtabs_pad_tests.exe
add_executable(invtabs_pad_tests EXCLUDE_FROM_ALL src/pad_tests.cpp src/pad_route.cpp)
target_link_libraries(invtabs_pad_tests PRIVATE D2RLPlugin::D2RLPlugin)
target_compile_features(invtabs_pad_tests PRIVATE cxx_std_20)
if(MSVC)
	target_compile_options(invtabs_pad_tests PRIVATE /W4 /permissive- /EHsc /utf-8)
endif()
add_dependencies(invtabs_tests invtabs_pad_tests)
# A missing signature turns off only its feature (fake PE image, the summary module as built):
# build/invtabs/Release/invtabs_natives_off_tests.exe
add_executable(invtabs_natives_off_tests EXCLUDE_FROM_ALL tests/natives_off_test.cpp src/summary.cpp)
target_compile_features(invtabs_natives_off_tests PRIVATE cxx_std_20)
if(MSVC)
	target_compile_options(invtabs_natives_off_tests PRIVATE /W4 /permissive- /EHsc /utf-8)
	set_property(TARGET invtabs_natives_off_tests PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
endif()
add_dependencies(invtabs_tests invtabs_natives_off_tests)
