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
# Everything the deployment's render reads, so an edit to one reruns it: every algorithm's FPP, an
# F´ component or not, the contracts' FPP and lists, the template and the renderer, its tests aside.
# The render rewrites a deployment topology only when its text changes.
file(GLOB WISE_RENDER_INPUTS CONFIGURE_DEPENDS
    "${FPRIME_PROJECT_ROOT}/algorithms/*/*.fpp"
    "${FPRIME_PROJECT_ROOT}/fsw/fpp/gnc/*.fpp"
    "${FPRIME_PROJECT_ROOT}/fsw/fpp/interfaces/*.fpp"
    "${FPRIME_PROJECT_ROOT}/fsw/mock/*.fpp"
    "${FPRIME_PROJECT_ROOT}/fsw/mock/*/*.fpp"
    "${FPRIME_PROJECT_ROOT}/fsw/mock/__init__.py"
    "${FPRIME_PROJECT_ROOT}/fsw/codegen/*.py"
    "${CMAKE_CURRENT_LIST_DIR}/deployment/Fsw.fpp.in")
list(FILTER WISE_RENDER_INPUTS EXCLUDE REGEX "_test\\.py$")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${WISE_RENDER_INPUTS})
# The test mock's F´ component, MockGnc.Actuator, which the test mock configuration MockActuation flies.
add_fprime_subdirectory("${FPRIME_PROJECT_ROOT}/fsw/mock/actuator")
# pybind11, for the hand-written module that hosts each configuration's deployment in the
# simulation's process, and `_wise_fsw`, the target building every configuration's extension and
# dictionary. The F´ sub-builds only gather model information and compile nothing.
if (NOT DEFINED FPRIME_SUB_BUILD_TARGETS)
    set(PYBIND11_FINDPYTHON ON)
    execute_process(COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
        OUTPUT_VARIABLE WISE_PYBIND11_CMAKEDIR OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
    find_package(pybind11 CONFIG REQUIRED PATHS "${WISE_PYBIND11_CMAKEDIR}")
    add_custom_target(_wise_fsw)
endif()
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/deployment")
