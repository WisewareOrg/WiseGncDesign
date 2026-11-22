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
