# Two throw-away D2RLoader test plugins for the game-wide plugin folder (docs/testing.md "Lane globalplugins"); never shipped.
#   gp-probe-log.dll   only writes log lines (where it loaded from, the active mod) and adds the console command `gpprobe`.
#   gp-probe-hook.dll  also hooks two D2R functions the way a third-party plugin would: a control function mxl2012-core leaves
#                      alone (0x373890) and the item requirement test mxl2012-core hooks (0x36bc50, merc_equip.cpp). It logs
#                      what D2RLoader answers. Every hook only calls the original. Console command `gpprobehook`.
# Build: cmake -S tools/gp_probe -B build/gp_probe -A x64 -DMXL2012_PLUGINSDK_DIR=<PluginSDK> && cmake --build build/gp_probe --config Release
cmake_minimum_required(VERSION 3.29)
project(gp_probe LANGUAGES CXX RC)
set(MXL2012_PLUGINSDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/PluginSDK" CACHE PATH "D2RLoader PluginSDK source folder")
set(D2RLPLUGIN_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory(${MXL2012_PLUGINSDK_DIR} PluginSDK EXCLUDE_FROM_ALL)
foreach(kind log hook)
	add_library(gp_probe_${kind} SHARED gp_probe.cpp gp_probe.rc)
	target_link_libraries(gp_probe_${kind} PRIVATE D2RLPlugin::D2RLPlugin)
	set_target_properties(gp_probe_${kind} PROPERTIES OUTPUT_NAME "gp-probe-${kind}" MSVC_RUNTIME_LIBRARY "MultiThreaded")
	target_compile_options(gp_probe_${kind} PRIVATE /W4 /permissive- /EHsc /utf-8)
endforeach()
target_compile_definitions(gp_probe_hook PRIVATE GP_PROBE_HOOK=1)
