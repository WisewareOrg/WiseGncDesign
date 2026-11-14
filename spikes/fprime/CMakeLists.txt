####
# Spike deployment for #52: SimHub on F´ serial ports (check A), PrmDb loading a fprime-prm-write .dat (check B).
# Self-contained: project root is this folder; only the framework comes from the main tree's F´ clone.
####
cmake_minimum_required(VERSION 3.24)
project(SpikeFsw C CXX)

include("${FPRIME_FRAMEWORK_PATH}/cmake/FPrime.cmake")
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
fprime_setup_included_code()

add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/Sim")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/Rio")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/Nav")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/Top")

if (NOT DEFINED FPRIME_SUB_BUILD_TARGETS)
    set(PYBIND11_FINDPYTHON ON)
    execute_process(COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
        OUTPUT_VARIABLE SPIKE_PYBIND11_CMAKEDIR OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
    find_package(pybind11 CONFIG REQUIRED PATHS "${SPIKE_PYBIND11_CMAKEDIR}")
    pybind11_add_module(_spike_fsw "${CMAKE_CURRENT_LIST_DIR}/Python/SpikeModule.cpp")
    target_link_libraries(_spike_fsw PRIVATE Top)
    fprime_target_implementations(_spike_fsw Os_Task_Sim)
    set_target_properties(_spike_fsw PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/python")
    add_custom_target(spike_dictionary
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${CMAKE_BINARY_DIR}/Top/SpikeTopologyDictionary.json"
            "${CMAKE_BINARY_DIR}/python/SpikeTopologyDictionary.json"
        DEPENDS Top_dictionary)
    add_dependencies(_spike_fsw spike_dictionary)
endif()
