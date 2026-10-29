# Unit tests of the downloader's portable core (no Windows headers). Included by ../CMakeLists.txt and buildable on its
# own, as CI does on Linux: cmake -S launcher/tests -B build-launcher-tests && cmake --build build-launcher-tests
cmake_minimum_required(VERSION 3.20)
project(mxl_launcher_tests LANGUAGES C CXX)

include(${CMAKE_CURRENT_SOURCE_DIR}/../third_party/lzma/lzma.cmake)

set(core ${CMAKE_CURRENT_SOURCE_DIR}/../src/core)
add_executable(launcher_tests core_tests.cpp ${core}/sha256.cpp ${core}/json.cpp ${core}/manifest.cpp ${core}/detect.cpp
               ${core}/paths.cpp ${core}/sevenzip.cpp ${core}/svgpath.cpp ${MXL_LZMA_SOURCES})
target_compile_definitions(launcher_tests PRIVATE MXL_RES_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../res"
                           MXL_TEST_DATA="${CMAKE_CURRENT_SOURCE_DIR}/data")
target_compile_features(launcher_tests PRIVATE cxx_std_20)
target_include_directories(launcher_tests PRIVATE ${MXL_LZMA_INCLUDE})
if(MSVC)
	target_compile_options(launcher_tests PRIVATE $<$<COMPILE_LANGUAGE:CXX>:/W4 /permissive- /EHsc> /utf-8)
else()
	target_compile_options(launcher_tests PRIVATE $<$<COMPILE_LANGUAGE:CXX>:-Wall -Wextra>)
endif()
