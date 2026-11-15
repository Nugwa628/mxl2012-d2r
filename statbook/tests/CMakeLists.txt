# Unit tests of the Stat Book's pure parts: the book (src/book_logic.h, the plain D2R book), the config and gamepad rule
# (src/statbook_config.h), the sheet's resistance rows (src/sheet_resist_logic.h) and the grouped Advanced Stats
# (src/advstats_logic.h, src/advstats_table.h) and the sheet host (src/sheet_host_logic.h). Included by ../CMakeLists.txt (target statbook_all_tests) and buildable on its
# own without Windows headers: cmake -S statbook/tests -B build/statbook-tests.
cmake_minimum_required(VERSION 3.20)
project(statbook_tests LANGUAGES CXX)

add_executable(statbook_tests EXCLUDE_FROM_ALL book_test.cpp)
add_executable(statbook_config_tests EXCLUDE_FROM_ALL config_test.cpp)
add_executable(statbook_sheetres_tests EXCLUDE_FROM_ALL sheet_resist_test.cpp)
add_executable(statbook_advstats_tests EXCLUDE_FROM_ALL advstats_test.cpp)
add_executable(statbook_sheethost_tests EXCLUDE_FROM_ALL sheet_host_test.cpp)
set(names statbook_tests statbook_config_tests statbook_sheetres_tests statbook_advstats_tests statbook_sheethost_tests)
add_custom_target(statbook_all_tests DEPENDS ${names})
foreach(t ${names})
	target_compile_features(${t} PRIVATE cxx_std_20)
	if(MSVC)
		target_compile_options(${t} PRIVATE /W4 /permissive- /EHsc /utf-8)
		target_compile_definitions(${t} PRIVATE _CRT_SECURE_NO_WARNINGS)
	else()
		target_compile_options(${t} PRIVATE -Wall -Wextra)
	endif()
endforeach()
