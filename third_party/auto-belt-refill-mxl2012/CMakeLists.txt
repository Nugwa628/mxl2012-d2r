# Release build of Auto Belt Refill (jaycachou-svg, https://github.com/jaycachou-svg/auto-belt-refill) for D2R-XL 2012:
# the author's source, patched by tools/build_beltrefill.ps1, against the project's PluginSDK. The author's own CMakeLists.txt
# lists the sources next to it while the repo keeps them in src/, so this one stands in for it with the same settings.
cmake_minimum_required(VERSION 3.28)
project(AutoBeltRefill VERSION 0.35.9 LANGUAGES CXX RC)

# Static CRT (/MT): players do not have the VC++ redistributable installed.
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")
set(ABR_SRC "" CACHE PATH "the patched src folder of the author's Auto-belt-refill-v0.35.9-EN")
set(ABR_SDK "" CACHE PATH "the D2RLoader PluginSDK checkout")

set(D2RLPLUGIN_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
add_subdirectory("${ABR_SDK}" "${CMAKE_CURRENT_BINARY_DIR}/_sdk")

add_library(AutoBeltRefill SHARED "${ABR_SRC}/auto_belt_refill_plugin.cpp" "${ABR_SRC}/auto_belt_refill_plugin.rc")
target_link_libraries(AutoBeltRefill PRIVATE D2RLPlugin::D2RLPlugin)
# belt_match_logic.h (0004) finds the game data of the counts with the repo's signature scan, invtabs/src/invtabs_logic.h.
set(ABR_SCAN "${CMAKE_CURRENT_SOURCE_DIR}/../../invtabs/src")
target_include_directories(AutoBeltRefill PRIVATE "${ABR_SCAN}")
set_target_properties(AutoBeltRefill PROPERTIES
	CXX_STANDARD 20
	CXX_STANDARD_REQUIRED TRUE
	CXX_EXTENSIONS FALSE
	OUTPUT_NAME "d2rl-auto-belt-refill")
target_compile_options(AutoBeltRefill PRIVATE $<$<COMPILE_LANGUAGE:CXX>:/W4 /permissive- /EHsc /utf-8>)

# Unit tests of our additions' pure logic (belt_match_logic.h, added by 0003, signatures by 0004; belt_natives.h, 0005): tools/build_beltrefill.ps1
# builds and runs them; with env D2R_DUMP (a memory-layout dump of D2R 93847, tools/dump_image.py) they also resolve the
# signatures in the real image.
add_executable(BeltMatchTests tests/belt_match_tests.cpp)
target_include_directories(BeltMatchTests PRIVATE "${ABR_SRC}" "${ABR_SCAN}")
set_target_properties(BeltMatchTests PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED TRUE CXX_EXTENSIONS FALSE)
target_compile_options(BeltMatchTests PRIVATE /W4 /permissive- /EHsc /utf-8)
