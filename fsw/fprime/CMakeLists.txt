####
# WiseFsw: the F´ flight software, built as a Python extension the simulation runs in its own process.
# The project root is the repository root (settings.ini), so components live beside the algorithms they port.
####
cmake_minimum_required(VERSION 3.24)
project(WiseFsw C CXX)
# A deprecated CMake command or policy is an error.
set(CMAKE_ERROR_DEPRECATED ON)

include("${CMAKE_CURRENT_LIST_DIR}/lib/fprime/cmake/FPrime.cmake")
# Every module links into one Python extension, so all of it is position independent.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
# F´'s own validation set and every warning gcc offers, as errors, then how it is all compiled and linked; what a kind
# of source does not meet is suppressed by name below. -Wstack-usage is ArduPilot's limit.
fprime_add_validation_flags()
add_compile_options(-Wabi -Walloc-size-larger-than=0 -Walloc-zero -Walloca -Warith-conversion -Warray-bounds=2
    -Wattribute-alias=2 -Wbidi-chars=any,ucn -Wcast-align=strict -Wcast-qual -Wdate-time -Wdisabled-optimization
    -Wduplicated-branches -Wduplicated-cond -Wflex-array-member-not-at-end -Wfloat-equal -Wformat-overflow=2
    -Wformat-signedness -Wformat-truncation=2 -Wformat=2 -Wimplicit-fallthrough=5 -Winit-self -Winline -Winvalid-pch
    -Winvalid-utf8 -Wleading-whitespace=spaces -Wlogical-op -Wlong-long -Wmissing-braces -Wmissing-declarations
    -Wmissing-include-dirs -Wmultichar -Wnormalized=nfkc -Wnull-dereference -Wopenacc-parallelism -Woverlength-strings
    -Wpacked -Wpadded -Wpointer-arith -Wredundant-decls -Wshift-overflow=2 -Wsign-conversion -Wstack-protector
    -Wstack-usage=1300 -Wstrict-aliasing=1 -Wstrict-flex-arrays -Wstrict-overflow=5 -Wstringop-overflow=4
    -Wsuggest-attribute=noreturn -Wswitch-default -Wswitch-enum -Wtrailing-whitespace=any -Wtrampolines
    -Wtrivial-auto-var-init -Wundef -Wunused-const-variable=2 -Wunused-macros -Wunused-parameter -Wuse-after-free=3
    -Wvariadic-macros -Wvector-operation-performance -Wvla -Wwrite-strings
    "$<$<COMPILE_LANGUAGE:CXX>:-Wabi-tag;-Waligned-new=all;-Wcatch-value=3;-Wcomma-subscript;-Wconditionally-supported;-Wctad-maybe-unsupported;-Wctor-dtor-privacy;-Wdangling-reference;-Wdeprecated-copy-dtor;-Wdeprecated-enum-enum-conversion;-Wdeprecated-enum-float-conversion;-Wdeprecated-literal-operator;-Wdeprecated-variadic-comma-omission;-Weffc++;-Wextra-semi;-Wmismatched-tags;-Wnoexcept;-Wnon-virtual-dtor;-Wnrvo;-Woverloaded-virtual=2;-Wplacement-new=2;-Wredundant-tags;-Wregister;-Wsign-promo;-Wstrict-null-sentinel;-Wsuggest-final-methods;-Wsuggest-final-types;-Wsuggest-override;-Wuseless-cast;-Wvirtual-inheritance;-Wvolatile;-Wzero-as-null-pointer-constant>")
add_compile_options(-ffp-contract=off
    -fstack-protector-strong -fstack-clash-protection -fcf-protection=full -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=3
    -D_GLIBCXX_ASSERTIONS -ftrivial-auto-var-init=zero -fstrict-flex-arrays=3 -fzero-init-padding-bits=all
    "$<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions;-fno-rtti;-fno-threadsafe-statics>")
add_link_options(LINKER:--fatal-warnings,--as-needed,--no-copy-dt-needed-entries,--warn-common,-z,relro,-z,now,-z,noexecstack)
fprime_setup_included_code()
# F´'s headers are system headers to what is written and generated here.
include_directories(SYSTEM "${CMAKE_CURRENT_LIST_DIR}/lib/fprime" "${CMAKE_BINARY_DIR}/F-Prime")

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
    # pybind11 turns link-time optimization on unless this is set; it would hold back the warnings optimization finds.
    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF)
    # pybind11 needs all three.
    set_property(TARGET pybind11::pybind11 APPEND PROPERTY INTERFACE_COMPILE_OPTIONS -fexceptions -frtti -fthreadsafe-statics)
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

# F´'s code: each warning it does not meet, and what it does instead. F´ adds -Wno-unused-parameter and -Wno-vla, and
# -Wno-type-limits in FrameAccumulator.
set(WISE_FPRIME_GENERATED "${CMAKE_BINARY_DIR}/F-Prime")
set(WISE_FPRIME_OPTIONS
    -Wvla                               # F´ turns it off for async serializable ports
    -Wno-cast-align                     # Os delegates are cast from their storage
    -Wno-long-long                      # StringToNumber reads long long
    -Wno-missing-declarations           # free functions with no header
    -Wno-padded                         # unpadded structs
    -Wno-stack-usage                    # PrmDb's frames pass the limit
    -Wno-switch-enum                    # switches with a default
    -Wno-trailing-whitespace            # in FPP's and F´'s text
    -Wno-unused-const-variable          # FilePathUtils
    -Wno-unused-macros                  # libcrc
    -Wstrict-aliasing=2                 # Os delegates
    "$<$<COMPILE_LANGUAGE:CXX>:-Wno-deprecated-copy-dtor>"              # Os::RawTime
    "$<$<COMPILE_LANGUAGE:CXX>:-Wno-deprecated-enum-enum-conversion>"   # FPP's port sizes
    "$<$<COMPILE_LANGUAGE:CXX>:-Wno-effc++>"                            # members set in the constructor's body
    "$<$<COMPILE_LANGUAGE:CXX>:-Wno-extra-semi>"                        # after a function's body
    "$<$<COMPILE_LANGUAGE:CXX>:-Wno-redundant-tags>"                    # FPP's class keywords
    "$<$<COMPILE_LANGUAGE:CXX>:-Wno-suggest-final-methods>"             # no final
    "$<$<COMPILE_LANGUAGE:CXX>:-Wno-suggest-final-types>"               # no final
    "$<$<COMPILE_LANGUAGE:CXX>:-Wno-suggest-override>"                  # FPP writes virtual
    "$<$<COMPILE_LANGUAGE:CXX>:-Wno-useless-cast>")                     # FPP's casts
# FPP's output for what is written here: the same, and what it does not meet.
set(WISE_FPP_OPTIONS
    -Wvla                               # F´ turns it off for async serializable ports
    -Wno-effc++                         # members set in the constructor's body
    -Wno-float-equal                    # operator== compares floats
    -Wno-padded                         # unpadded structs
    -Wno-redundant-tags                 # class keywords
    -Wno-suggest-final-methods          # no final
    -Wno-suggest-final-types            # no final
    -Wno-suggest-override               # FPP writes virtual
    -Wno-useless-cast)                  # FPP's casts
# What is written here, our generators' output included, takes back what F´ turns off.
set(WISE_WRITTEN_OPTIONS "-isystem${CMAKE_BINARY_DIR}" -Wunused-parameter -Wvla)
function(wise_source_options DIRECTORY)
    get_property(TARGETS DIRECTORY "${DIRECTORY}" PROPERTY BUILDSYSTEM_TARGETS)
    foreach (TARGET IN LISTS TARGETS)
        get_target_property(SOURCES "${TARGET}" SOURCES)
        foreach (SOURCE IN LISTS SOURCES)
            cmake_path(ABSOLUTE_PATH SOURCE BASE_DIRECTORY "${DIRECTORY}")
            cmake_path(IS_PREFIX FPRIME_PROJECT_ROOT "${SOURCE}" OURS)
            cmake_path(IS_PREFIX CMAKE_BINARY_DIR "${SOURCE}" BUILT)
            cmake_path(IS_PREFIX FPRIME_FRAMEWORK_PATH "${SOURCE}" FRAMEWORK)
            cmake_path(IS_PREFIX WISE_FPRIME_GENERATED "${SOURCE}" FPRIME_GENERATED)
            if (NOT SOURCE MATCHES "\\.(c|cpp)$")
                continue()
            elseif (FRAMEWORK OR FPRIME_GENERATED)
                set(OPTIONS ${WISE_FPRIME_OPTIONS})
            elseif (SOURCE MATCHES "Ac\\.cpp$")
                set(OPTIONS ${WISE_FPP_OPTIONS})
            elseif (OURS AND NOT BUILT OR SOURCE MATCHES "(FswTopology|/BusConverter|/BusConverterPins)\\.cpp$")
                set(OPTIONS ${WISE_WRITTEN_OPTIONS})
                # The pins hold what a flight wrote, in memory that grows, and pybind11 allocates in a module Python loads.
                get_target_property(TYPE "${TARGET}" TYPE)
                if (SOURCE MATCHES "/lab/pins/|/BusConverterPins\\.cpp$" OR TYPE STREQUAL "MODULE_LIBRARY")
                    list(APPEND OPTIONS -Wno-alloc-size-larger-than)
                endif ()
            else ()
                continue()
            endif ()
            set_source_files_properties("${SOURCE}" TARGET_DIRECTORY "${TARGET}" PROPERTIES COMPILE_OPTIONS "${OPTIONS}")
        endforeach ()
    endforeach ()
    get_property(CHILDREN DIRECTORY "${DIRECTORY}" PROPERTY SUBDIRECTORIES)
    foreach (CHILD IN LISTS CHILDREN)
        wise_source_options("${CHILD}")
    endforeach ()
endfunction()
wise_source_options("${CMAKE_CURRENT_SOURCE_DIR}")
