# mxl2012-core D2RLoader plugin. Build: cmake -S plugin -B build/plugin -A x64 && cmake --build build/plugin --config Release
# (or tools/build_plugin.ps1). tools/install_mod.py copies build/plugin/Release/mxl2012-core.dll into the mod.
cmake_minimum_required(VERSION 3.29)
project(mxl2012_core LANGUAGES CXX RC)

# The D2RLoader PluginSDK: the submodule third_party/PluginSDK, or another checkout (-DMXL2012_PLUGINSDK_DIR=path).
set(MXL2012_PLUGINSDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/PluginSDK" CACHE PATH "D2RLoader PluginSDK source folder")
set(D2RLPLUGIN_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory(${MXL2012_PLUGINSDK_DIR} PluginSDK EXCLUDE_FROM_ALL)

# The skeleton and the ported parts of Median XL 2012 (docs/plugin-plan.md): client do 113 (client_skills), the empty missile
# slot stubs (missile_stubs), the Whirlwind rule D2R changed (whirlwind), the second `useitem` cube output (cube_dupe), item levels above 99 (item_level), the Great Runes' letters (rune_letters), the skill tooltip labels (skill_text), the mercenary weapon rules (merc_equip), the worn items' durability on the client (dur_sync), the crash guards (sound_guard, translation_guard), the legacy level-up buttons (lvlup_ui), the pet-warp spread (pet_spread), Baal's laugh chat line cooldown (vo_chat), the unit reassign guard (reassign_guard).
add_library(mxl2012_core SHARED src/mxl2012_core.cpp src/d2r.cpp src/build_guard.cpp src/client_skills.cpp src/item_effect.cpp src/missile_stubs.cpp src/skill_remove.cpp src/dodge_list.cpp src/state_lists.cpp src/melt_trail.cpp src/orig_asserts.cpp src/whirlwind.cpp src/cube_dupe.cpp src/item_level.cpp src/rune_letters.cpp src/skill_text.cpp src/merc_equip.cpp src/dur_sync.cpp
            src/sound_guard.cpp src/translation_guard.cpp src/lvlup_ui.cpp src/pet_spread.cpp src/apple_use.cpp src/vo_chat.cpp src/reassign_guard.cpp
            src/mxl2012_core.rc)
# MXL_RELEASE (player releases, tools/package_release.py): the test harness is not compiled in; its entry points are no-ops
# (testharness_release.cpp). Off by default: dev builds keep the harness (off unless mxl2012-testharness.txt exists).
option(MXL_RELEASE "Release build for players: no test harness" OFF)
if(MXL_RELEASE)
	target_sources(mxl2012_core PRIVATE src/testharness_release.cpp)
	target_compile_definitions(mxl2012_core PRIVATE MXL_RELEASE=1)
else()
	target_sources(mxl2012_core PRIVATE src/testharness.cpp src/harness_cmds.cpp)  # test harness and its gameplay commands
endif()
# The DLL's version resource (src/mxl2012_core.rc) carries PluginVersion of mxl2012_core.cpp.
file(STRINGS src/mxl2012_core.cpp plugin_version_line REGEX "PluginVersion = \"[0-9]+[.][0-9]+[.][0-9]+\"")
if(NOT plugin_version_line MATCHES "\"([0-9]+)[.]([0-9]+)[.]([0-9]+)\"")
	message(FATAL_ERROR "PluginVersion not found in src/mxl2012_core.cpp")
endif()
set_property(SOURCE src/mxl2012_core.rc APPEND PROPERTY COMPILE_DEFINITIONS
             MXL_PV_STR="${CMAKE_MATCH_1}.${CMAKE_MATCH_2}.${CMAKE_MATCH_3}" MXL_PV_NUM=${CMAKE_MATCH_1},${CMAKE_MATCH_2},${CMAKE_MATCH_3},0)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS src/mxl2012_core.cpp)
target_link_libraries(mxl2012_core PRIVATE D2RLPlugin::D2RLPlugin)
set_target_properties(mxl2012_core PROPERTIES OUTPUT_NAME "mxl2012-core")
if(MSVC)
	target_compile_options(mxl2012_core PRIVATE /W4 /permissive- /EHsc /utf-8)
	set_property(TARGET mxl2012_core PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")  # no VC++ runtime dependency
endif()

# Unit tests for the pure parts (not in the plugin DLL): tests/CMakeLists.txt
add_subdirectory(tests)
