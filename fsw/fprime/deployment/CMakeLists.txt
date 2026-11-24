# Builds each configuration's WiseFsw deployment and `_wise_fsw_<configuration>` extension in a
# subdirectory of its own; `python -m fsw.codegen.deployment` picks and renders them.
register_fprime_module(
  fsw_fprime_deployment_instances
  AUTOCODER_INPUTS
    "${CMAKE_CURRENT_LIST_DIR}/instances.fpp"
  INTERFACE
  DEPENDS
    fsw_fprime_platform
    fsw_fprime_cdh
    fsw_fprime_rio
    Svc_CmdDispatcher
    Svc_PrmDb
)

execute_process(
    COMMAND "${Python_EXECUTABLE}" -m fsw.codegen.deployment "${CMAKE_CURRENT_BINARY_DIR}"
    WORKING_DIRECTORY "${FPRIME_PROJECT_ROOT}"
    OUTPUT_VARIABLE WISE_CONFIGURATIONS
    OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY)
string(REPLACE "\n" ";" WISE_CONFIGURATIONS "${WISE_CONFIGURATIONS}")

# `wise_fsw_sealed`: the options that link flight software without an allocator. There is no C++
# library, libc's allocators are wrapped by functions that do not exist, and only the language's own
# support is defined, so a call that can allocate is an undefined reference the linker names.
if (NOT DEFINED FPRIME_SUB_BUILD_TARGETS)
    add_library(wise_fsw_sealed INTERFACE IMPORTED)
    target_link_options(wise_fsw_sealed INTERFACE -nostdlib++ LINKER:-z,defs)
    target_link_libraries(wise_fsw_sealed INTERFACE m)
    foreach (ALLOCATOR IN ITEMS malloc calloc realloc reallocarray aligned_alloc posix_memalign memalign mmap mmap64
            strdup strndup __strdup __strndup asprintf vasprintf __asprintf_chk __vasprintf_chk getline getdelim
            __getdelim fopen fopen64)
        target_link_options(wise_fsw_sealed INTERFACE "LINKER:--wrap=${ALLOCATOR}")
    endforeach ()
    foreach (SUPPORT IN ITEMS __cxa_deleted_virtual __cxa_pure_virtual _ZdlPvm _ZTVN10__cxxabiv117__class_type_infoE
            _ZTVN10__cxxabiv120__si_class_type_infoE _ZTVN10__cxxabiv121__vmi_class_type_infoE)
        target_link_options(wise_fsw_sealed INTERFACE "LINKER:--defsym=${SUPPORT}=0")
    endforeach ()
    # One source, linked as it is and with a line that grows a vector: only the growth may be refused.
    set(WISE_SEAL_SOURCE [[
#include <vector>
std::vector<int> values;
int main() {
#ifdef GROW
    values.push_back(0);
#endif
    return static_cast<int>(values.size());
}
]])
    try_compile(WISE_SEAL_LINKS SOURCE_FROM_VAR seal.cpp WISE_SEAL_SOURCE NO_CACHE
        COMPILE_DEFINITIONS -fno-exceptions LINK_LIBRARIES wise_fsw_sealed OUTPUT_VARIABLE WISE_SEAL_OUTPUT)
    if (NOT WISE_SEAL_LINKS)
        message(FATAL_ERROR "wise_fsw_sealed refuses code that does not allocate:\n${WISE_SEAL_OUTPUT}")
    endif ()
    try_compile(WISE_SEAL_LINKS SOURCE_FROM_VAR seal.cpp WISE_SEAL_SOURCE NO_CACHE
        COMPILE_DEFINITIONS -fno-exceptions -DGROW LINK_LIBRARIES wise_fsw_sealed OUTPUT_VARIABLE WISE_SEAL_OUTPUT)
    if (WISE_SEAL_LINKS OR NOT WISE_SEAL_OUTPUT MATCHES "operator new")
        message(FATAL_ERROR "wise_fsw_sealed does not refuse a vector's growth, naming operator new:\n${WISE_SEAL_OUTPUT}")
    endif ()
endif ()

foreach (WISE_CONFIGURATION IN LISTS WISE_CONFIGURATIONS)
    string(REPLACE "\t" ";" WISE_CONFIGURATION "${WISE_CONFIGURATION}")
    list(GET WISE_CONFIGURATION 0 CONFIGURATION)
    list(GET WISE_CONFIGURATION 1 GNC_SUB_TOPOLOGY)
    if (NOT DEFINED WISE_STUB_CONFIGURATION)
        set(WISE_STUB_CONFIGURATION "${CONFIGURATION}")
    endif ()
    set(RENDERED "${CMAKE_CURRENT_BINARY_DIR}/${CONFIGURATION}")
    foreach (TEMPLATE IN ITEMS FswTopology.cpp FswTopology.hpp FswTopologyDefs.hpp)
        configure_file("${CMAKE_CURRENT_LIST_DIR}/${TEMPLATE}.in" "${RENDERED}/${CONFIGURATION}${TEMPLATE}" @ONLY)
    endforeach ()
    configure_file("${CMAKE_CURRENT_LIST_DIR}/CMakeLists.txt.in" "${RENDERED}/CMakeLists.txt" @ONLY)
    add_subdirectory("${RENDERED}" "${RENDERED}")
endforeach ()

# The `FswExtension` protocol, from the first configuration's extension: every configuration has the same fixed functions.
if (NOT DEFINED FPRIME_SUB_BUILD_TARGETS AND DEFINED WISE_STUB_CONFIGURATION)
    add_custom_command(
        OUTPUT "${FPRIME_PROJECT_ROOT}/lab/fsw_extension.pyi"
        COMMAND "${Python_EXECUTABLE}" -m fsw.codegen.fsw_extension "lab._wise_fsw_${WISE_STUB_CONFIGURATION}"
        WORKING_DIRECTORY "${FPRIME_PROJECT_ROOT}"
        DEPENDS "$<TARGET_FILE:_wise_fsw_${WISE_STUB_CONFIGURATION}>" ${WISE_RENDER_INPUTS}
        COMMENT "Stubbing the FswExtension protocol")
    add_custom_target(wise_fsw_extension_stub DEPENDS "${FPRIME_PROJECT_ROOT}/lab/fsw_extension.pyi")
    add_dependencies(_wise_fsw wise_fsw_extension_stub)
endif ()
