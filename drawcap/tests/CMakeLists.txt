# Unit tests of drawcap's pure part (src/drawcap_logic.h). Included by ../CMakeLists.txt (target drawcap_tests) and buildable
# on its own without Windows headers, as CI does on Linux: cmake -S drawcap/tests -B build/drawcap-tests.
cmake_minimum_required(VERSION 3.20)
project(drawcap_tests LANGUAGES CXX)

add_executable(drawcap_tests EXCLUDE_FROM_ALL drawcap_test.cpp)
target_compile_features(drawcap_tests PRIVATE cxx_std_20)
if(MSVC)
	target_compile_options(drawcap_tests PRIVATE /W4 /permissive- /EHsc /utf-8)
	target_compile_definitions(drawcap_tests PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()
