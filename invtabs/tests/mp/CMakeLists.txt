# Standalone tests for invtabs/src/mp_protocol.* (pure code, no D2RLoader SDK).
#   cmake -S invtabs/tests/mp -B work/build/invtabs-mp-tests && cmake --build work/build/invtabs-mp-tests --config Release
#   ctest --test-dir work/build/invtabs-mp-tests -C Release --output-on-failure
cmake_minimum_required(VERSION 3.20)
project(invtabs_mp_tests CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(INVTABS_SRC ${CMAKE_CURRENT_LIST_DIR}/../../src)
add_executable(mp_protocol_test mp_protocol_test.cpp ${INVTABS_SRC}/mp_protocol.cpp)
target_include_directories(mp_protocol_test PRIVATE ${INVTABS_SRC})
if (MSVC)
	target_compile_options(mp_protocol_test PRIVATE /W4 /WX /permissive-)
endif()

enable_testing()
add_test(NAME mp_protocol COMMAND mp_protocol_test)
