# The WiseFsw deployment of each configuration the F´ build builds, into a build subdirectory of its
# own that also compiles its GNC sub-topology and builds the configuration's extension,
# `_wise_fsw_<configuration>`; nothing rendered is in source. `python -m fsw.codegen.deployment`
# picks the configurations, renders each deployment topology with its role wiring, and prints each
# one's name and GNC sub-topology; the C++ templates and CMakeLists.txt.in are rendered here.
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

# A change to anything the render reads reruns it: the contracts' FPP, the template and the renderer;
# the algorithms' FPP joins it beside the algorithms' glob in fsw/fprime/CMakeLists.txt.
file(GLOB WISE_RENDER_INPUTS CONFIGURE_DEPENDS
    "${FPRIME_PROJECT_ROOT}/fsw/fpp/gnc/*.fpp"
    "${FPRIME_PROJECT_ROOT}/fsw/fpp/interfaces/*.fpp"
    "${FPRIME_PROJECT_ROOT}/fsw/mock/*.fpp"
    "${FPRIME_PROJECT_ROOT}/fsw/mock/*/*.fpp"
    "${FPRIME_PROJECT_ROOT}/fsw/codegen/*.py"
    "${CMAKE_CURRENT_LIST_DIR}/Fsw.fpp.in")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${WISE_RENDER_INPUTS})
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
    set(RENDERED "${CMAKE_CURRENT_BINARY_DIR}/${CONFIGURATION}")
    foreach (TEMPLATE IN ITEMS FswTopology.cpp FswTopology.hpp FswTopologyDefs.hpp)
        configure_file("${CMAKE_CURRENT_LIST_DIR}/${TEMPLATE}.in" "${RENDERED}/${CONFIGURATION}${TEMPLATE}" @ONLY)
    endforeach ()
    configure_file("${CMAKE_CURRENT_LIST_DIR}/CMakeLists.txt.in" "${RENDERED}/CMakeLists.txt" @ONLY)
    add_subdirectory("${RENDERED}" "${RENDERED}")
endforeach ()
