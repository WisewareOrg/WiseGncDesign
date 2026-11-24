####
# WiseFsw: the F´ flight software, built as a Python extension the simulation runs in its own process.
# The project root is the repository root (settings.ini), so components live beside the algorithms they port.
####
cmake_minimum_required(VERSION 3.25)
project(WiseFsw C CXX)
# A deprecated CMake command or policy is an error.
set(CMAKE_ERROR_DEPRECATED ON)

include("${CMAKE_CURRENT_LIST_DIR}/lib/fprime/cmake/FPrime.cmake")
# Every module links into one Python extension, so all of it is position independent.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
# F´'s own validation set, warnings as errors, over F´ and everything here, then how it is all compiled and
# linked, stated so that every host compiles the same code.
fprime_add_validation_flags()
add_compile_options(-ffp-contract=off
    -fno-stack-protector -fno-stack-clash-protection -fcf-protection=none -U_FORTIFY_SOURCE
    "$<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions;-fno-threadsafe-statics>")
add_link_options(LINKER:--fatal-warnings,-z,relro,-z,now,-z,noexecstack)
fprime_setup_included_code()
# What is written and generated here meets more. F´'s headers are system headers to it.
include_directories(SYSTEM "${CMAKE_CURRENT_LIST_DIR}/lib/fprime" "${CMAKE_BINARY_DIR}/F-Prime")
add_compile_options(-Walloca -Warith-conversion -Warray-bounds=2 -Wcast-align=strict -Wcast-qual -Wdate-time
    -Wduplicated-branches -Wduplicated-cond -Wfloat-equal -Wformat=2 -Wformat-overflow=2 -Wformat-signedness
    -Wformat-truncation=2 -Wimplicit-fallthrough=5 -Wlogical-op -Wmissing-declarations -Wmissing-include-dirs
    -Wnull-dereference -Wredundant-decls -Wsign-conversion -Wstack-usage=65536 -Wstrict-overflow=2
    -Wstringop-overflow=4 -Wswitch-default -Wswitch-enum -Wtrampolines -Wundef -Wunused-const-variable=2
    "$<$<COMPILE_LANGUAGE:CXX>:-Wcatch-value=3;-Wctor-dtor-privacy;-Wdeprecated-copy-dtor;-Wextra-semi;-Wnon-virtual-dtor;-Woverloaded-virtual=2;-Wzero-as-null-pointer-constant>")

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

add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/config-overrides")
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
    # The modules Python loads are test equipment, and pybind11 needs both.
    set_property(TARGET pybind11::pybind11 APPEND PROPERTY INTERFACE_COMPILE_OPTIONS -fexceptions -fthreadsafe-statics)
    add_custom_target(_wise_fsw)
    # Every algorithm utility with C++: the directories under algorithms/utils/ with a CMakeLists.txt,
    # each building `_<name>`, the extension its tests reach the C++ through.
    file(GLOB WISE_UTILITIES CONFIGURE_DEPENDS "${FPRIME_PROJECT_ROOT}/algorithms/utils/*/CMakeLists.txt")
    foreach (WISE_UTILITY IN LISTS WISE_UTILITIES)
        get_filename_component(WISE_UTILITY_DIR "${WISE_UTILITY}" DIRECTORY)
        get_filename_component(WISE_UTILITY_NAME "${WISE_UTILITY_DIR}" NAME)
        add_subdirectory("${WISE_UTILITY_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/utils/${WISE_UTILITY_NAME}")
        add_dependencies(_wise_fsw "_${WISE_UTILITY_NAME}")
        # Its type stub, written beside it; stubgen's exit code fails the build, which it does not by default.
        add_custom_command(
            OUTPUT "${WISE_UTILITY_DIR}/_${WISE_UTILITY_NAME}.pyi"
            COMMAND "${CMAKE_COMMAND}" -E env "PYTHONPATH=${WISE_UTILITY_DIR}"
                "${Python_EXECUTABLE}" -m pybind11_stubgen "_${WISE_UTILITY_NAME}"
                --exit-code -o "${WISE_UTILITY_DIR}"
            DEPENDS "$<TARGET_FILE:_${WISE_UTILITY_NAME}>"
            COMMENT "Stubbing _${WISE_UTILITY_NAME}")
        add_custom_target("_${WISE_UTILITY_NAME}_stub" DEPENDS "${WISE_UTILITY_DIR}/_${WISE_UTILITY_NAME}.pyi")
        add_dependencies(_wise_fsw "_${WISE_UTILITY_NAME}_stub")
    endforeach ()
    # The stub of `fsw.codegen.fpp_types`, which a type checker cannot read from the module's imports.
    add_custom_command(
        OUTPUT "${FPRIME_PROJECT_ROOT}/fsw/codegen/fpp_types.pyi"
        COMMAND "${Python_EXECUTABLE}" -m fsw.codegen.fpp_types_stub
        WORKING_DIRECTORY "${FPRIME_PROJECT_ROOT}"
        DEPENDS ${WISE_RENDER_INPUTS}
        COMMENT "Stubbing fsw.codegen.fpp_types")
    add_custom_target(wise_fpp_types_stub DEPENDS "${FPRIME_PROJECT_ROOT}/fsw/codegen/fpp_types.pyi")
    add_dependencies(_wise_fsw wise_fpp_types_stub)
endif()
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/deployment")

# FPP's generated sources compare a struct's or array's floats for equality.
function(wise_generated_options DIRECTORY)
    get_property(TARGETS DIRECTORY "${DIRECTORY}" PROPERTY BUILDSYSTEM_TARGETS)
    foreach (TARGET IN LISTS TARGETS)
        get_target_property(SOURCES "${TARGET}" SOURCES)
        list(FILTER SOURCES INCLUDE REGEX "Ac\\.cpp$")
        if (SOURCES)
            set_source_files_properties(${SOURCES} TARGET_DIRECTORY "${TARGET}" PROPERTIES COMPILE_OPTIONS -Wno-float-equal)
        endif ()
    endforeach ()
    get_property(CHILDREN DIRECTORY "${DIRECTORY}" PROPERTY SUBDIRECTORIES)
    foreach (CHILD IN LISTS CHILDREN)
        wise_generated_options("${CHILD}")
    endforeach ()
endfunction()
wise_generated_options("${CMAKE_CURRENT_SOURCE_DIR}")
