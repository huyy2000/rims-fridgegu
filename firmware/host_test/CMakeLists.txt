cmake_minimum_required(VERSION 3.16)
project(recording_bean_host_tests CXX C)

enable_testing()

set(COMPONENTS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../components)
set(PLATFORM_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../main/platform)

add_executable(test_door_event_policy
    door_event_policy_tests.cpp
    ${COMPONENTS_DIR}/door_event_policy/door_event_policy.c
)
target_include_directories(test_door_event_policy PRIVATE
    ${COMPONENTS_DIR}/door_event_policy/include
)
add_test(NAME door_event_policy COMMAND test_door_event_policy)

add_executable(test_board_pins
    board_pins_tests.cpp
    ${PLATFORM_DIR}/board_pins.c
)
target_include_directories(test_board_pins PRIVATE ${PLATFORM_DIR})
add_test(NAME board_pins COMMAND test_board_pins)
