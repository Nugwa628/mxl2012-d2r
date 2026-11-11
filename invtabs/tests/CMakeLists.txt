# Unit tests of invtabs' pure part (src/invtabs_logic.h, src/invtabs_natives.h). Included by ../CMakeLists.txt (target
# invtabs_tests) and buildable on its own without Windows headers: cmake -S invtabs/tests -B build/invtabs-tests.
cmake_minimum_required(VERSION 3.20)
project(invtabs_tests LANGUAGES CXX)

add_executable(invtabs_tests EXCLUDE_FROM_ALL invtabs_test.cpp)
target_compile_features(invtabs_tests PRIVATE cxx_std_20)
if(MSVC)
	target_compile_options(invtabs_tests PRIVATE /W4 /permissive- /EHsc /utf-8)
	target_compile_definitions(invtabs_tests PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()

# The data lane's tab tables, the controller tab's layout and the charm summary's pure parts.
foreach(test IN ITEMS tab_config summary)
	add_executable(invtabs_${test}_tests EXCLUDE_FROM_ALL ${test}_test.cpp)
	target_compile_features(invtabs_${test}_tests PRIVATE cxx_std_20)
	if(MSVC)
		target_compile_options(invtabs_${test}_tests PRIVATE /W4 /permissive- /EHsc /utf-8)
		target_compile_definitions(invtabs_${test}_tests PRIVATE _CRT_SECURE_NO_WARNINGS)
	endif()
	add_dependencies(invtabs_tests invtabs_${test}_tests)
endforeach()

# The TCP/IP protocol's pure part (src/mp_protocol.*; mp/CMakeLists.txt builds the same test on its own).
add_executable(invtabs_mp_tests EXCLUDE_FROM_ALL mp/mp_protocol_test.cpp ../src/mp_protocol.cpp)
target_include_directories(invtabs_mp_tests PRIVATE ../src)
target_compile_features(invtabs_mp_tests PRIVATE cxx_std_20)
if(MSVC)
	target_compile_options(invtabs_mp_tests PRIVATE /W4 /WX /permissive- /EHsc /utf-8)
endif()
add_dependencies(invtabs_tests invtabs_mp_tests)
