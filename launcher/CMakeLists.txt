# D2R-XL 2012 Downloader (docs/launcher.md). One static exe, no runtime to install: WinHTTP, Win32 + GDI+, the LZMA SDK's
# 7z decoder (third_party/lzma).
#   cmake -S launcher -B build/launcher -A x64 && cmake --build build/launcher --config Release
# CI cross-builds it like the plugin: -DCMAKE_TOOLCHAIN_FILE=plugin/cmake/xwin-toolchain.cmake (clang-cl + lld-link).
cmake_minimum_required(VERSION 3.20)
project(mxl_launcher LANGUAGES C CXX RC)

include(third_party/lzma/lzma.cmake)

set(core src/core/sha256.cpp src/core/json.cpp src/core/manifest.cpp src/core/detect.cpp src/core/paths.cpp
         src/core/sevenzip.cpp src/core/svgpath.cpp)
add_executable(mxl_launcher WIN32 src/win/main.cpp src/win/window.cpp src/win/app.cpp src/win/game.cpp src/win/http.cpp src/win/util.cpp ${core} ${MXL_LZMA_SOURCES}
               res/launcher.rc)
set_target_properties(mxl_launcher PROPERTIES OUTPUT_NAME "D2R-XL-2012-Downloader")
target_compile_features(mxl_launcher PRIVATE cxx_std_20)
target_include_directories(mxl_launcher PRIVATE ${MXL_LZMA_INCLUDE})
target_compile_definitions(mxl_launcher PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX _WIN32_WINNT=0x0A00)
set(MXL_LAUNCHER_VERSION "" CACHE STRING "override the downloader version (tests of the self-update); empty: app.h's")
# One version for the code and the exe's version resource (tools/publish_release.py reads the resource): app.h's
# MXL_LAUNCHER_VERSION unless overridden here.
if(MXL_LAUNCHER_VERSION)
	set(launcher_version "${MXL_LAUNCHER_VERSION}")
else()
	file(STRINGS src/win/app.h version_line REGEX "^#define MXL_LAUNCHER_VERSION \"[0-9]+[.][0-9]+[.][0-9]+\"")
	string(REGEX REPLACE ".*\"([0-9.]+)\".*" "\\1" launcher_version "${version_line}")
endif()
if(NOT launcher_version MATCHES "^([0-9]+)[.]([0-9]+)[.]([0-9]+)$")
	message(FATAL_ERROR "downloader version '${launcher_version}' is not x.y.z")
endif()
set_property(SOURCE src/win/app.cpp src/win/main.cpp src/win/window.cpp APPEND PROPERTY COMPILE_DEFINITIONS
             MXL_LAUNCHER_VERSION="${launcher_version}")
set_property(SOURCE res/launcher.rc APPEND PROPERTY COMPILE_DEFINITIONS MXL_LV_STR="${launcher_version}"
             MXL_LV_NUM=${CMAKE_MATCH_1},${CMAKE_MATCH_2},${CMAKE_MATCH_3},0)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS src/win/app.h)  # a new version in app.h reconfigures
message(STATUS "downloader version ${launcher_version}")
# Signing is a separate, later step (docs/launcher.md "Release and signing"): the build leaves the unsigned exe and its
# sha256 side by side.
add_custom_command(TARGET mxl_launcher POST_BUILD
                   COMMAND ${CMAKE_COMMAND} -DEXE=$<TARGET_FILE:mxl_launcher> -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/sha256.cmake
                   VERBATIM)
target_link_libraries(mxl_launcher PRIVATE winhttp comctl32 shell32 ole32 version advapi32 user32 gdi32 wintrust crypt32
                      gdiplus shlwapi dwmapi)
if(MSVC)
	target_compile_options(mxl_launcher PRIVATE $<$<COMPILE_LANGUAGE:CXX>:/W4 /permissive- /EHsc> /utf-8 /O1)
	target_link_options(mxl_launcher PRIVATE /MANIFEST:NO)  # the manifest comes from res/launcher.rc
	set_property(TARGET mxl_launcher PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")  # no VC++ runtime to install
endif()

add_subdirectory(tests)
