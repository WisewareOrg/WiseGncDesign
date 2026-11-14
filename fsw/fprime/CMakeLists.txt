####
# WiseFsw: the F´ flight software, built as a Python extension the simulation runs in its own process.
# The project root is the repository root (settings.ini), so components live beside the algorithms they port.
####
cmake_minimum_required(VERSION 3.24)
project(WiseFsw C CXX)

include("${CMAKE_CURRENT_LIST_DIR}/lib/fprime/cmake/FPrime.cmake")
# Every module links into one Python extension, so all of it is position independent.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
fprime_setup_included_code()

# Eigen, header-only, fetched by git tag into lib/, outside the build cache, so a regenerated cache keeps it.
include(FetchContent)
set(FETCHCONTENT_BASE_DIR "${CMAKE_CURRENT_LIST_DIR}/lib/fetchcontent")
FetchContent_Declare(eigen
    GIT_REPOSITORY https://gitlab.com/libeigen/eigen.git
    GIT_TAG 5.0.1
    GIT_SHALLOW TRUE
    SOURCE_SUBDIR do-not-add-eigen-build)
FetchContent_MakeAvailable(eigen)
add_library(wise_eigen INTERFACE)
target_include_directories(wise_eigen SYSTEM INTERFACE "${eigen_SOURCE_DIR}")

add_fprime_subdirectory("${FPRIME_PROJECT_ROOT}/fsw/fpp/interfaces")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/platform")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/cdh")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/rio")
# Every algorithm with an F´ component: the directories under algorithms/ with a CMakeLists.txt.
file(GLOB WISE_ALGORITHMS CONFIGURE_DEPENDS "${FPRIME_PROJECT_ROOT}/algorithms/*/CMakeLists.txt")
foreach (WISE_ALGORITHM IN LISTS WISE_ALGORITHMS)
    get_filename_component(WISE_ALGORITHM_DIR "${WISE_ALGORITHM}" DIRECTORY)
    add_fprime_subdirectory("${WISE_ALGORITHM_DIR}")
endforeach ()
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/deployment")

# The hand-written pybind11 module that hosts the deployment in the simulation's process.
# The F´ sub-builds only gather model information and compile nothing.
if (NOT DEFINED FPRIME_SUB_BUILD_TARGETS)
    set(PYBIND11_FINDPYTHON ON)
    execute_process(COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
        OUTPUT_VARIABLE WISE_PYBIND11_CMAKEDIR OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
    find_package(pybind11 CONFIG REQUIRED PATHS "${WISE_PYBIND11_CMAKEDIR}")
    pybind11_add_module(_wise_fsw "${FPRIME_PROJECT_ROOT}/lab/pins/WiseFswModule.cpp")
    # The one configuration the extension flies.
    target_link_libraries(_wise_fsw PRIVATE fsw_fprime_deployment_ImuDeadReckoning wise_eigen)
    target_compile_definitions(_wise_fsw PRIVATE
        WISE_FSW_TOPOLOGY_HEADER="fsw/fprime/deployment/ImuDeadReckoning/ImuDeadReckoningFswTopology.hpp")
    # The platform implementations (Os and the like) F´ chooses at link time, as for a deployment.
    # Its Os::Task has no thread, so the tick runs the active components.
    fprime_target_implementations(_wise_fsw Os_Task_Sim Os_RawTime_Stub)
    set_target_properties(_wise_fsw PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${FPRIME_PROJECT_ROOT}/lab")
    # The dictionary ships beside the extension: Python names and decodes the telemetry with it.
    # A target without outputs runs on every build, so the copy tracks the dictionary the build just wrote.
    add_custom_target(wise_fsw_dictionary
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${CMAKE_BINARY_DIR}/fsw/fprime/deployment/ImuDeadReckoning/ImuDeadReckoningFswTopologyDictionary.json"
            "${FPRIME_PROJECT_ROOT}/lab/WiseFswTopologyDictionary.json"
        DEPENDS fsw_fprime_deployment_ImuDeadReckoning_dictionary)
    add_dependencies(_wise_fsw wise_fsw_dictionary)
endif()
