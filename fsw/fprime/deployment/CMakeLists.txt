# The WiseFsw deployment of each configuration, rendered from the templates here for each GNC
# sub-topology in fsw/fpp/gnc/, into a build subdirectory of its own that also compiles that
# sub-topology; nothing rendered is in source.
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

file(GLOB GNC_SUB_TOPOLOGIES CONFIGURE_DEPENDS "${FPRIME_PROJECT_ROOT}/fsw/fpp/gnc/*.fpp")
foreach (GNC_SUB_TOPOLOGY IN LISTS GNC_SUB_TOPOLOGIES)
    get_filename_component(CONFIGURATION "${GNC_SUB_TOPOLOGY}" NAME_WE)
    set(RENDERED "${CMAKE_CURRENT_BINARY_DIR}/${CONFIGURATION}")
    foreach (TEMPLATE IN ITEMS Fsw.fpp FswTopology.cpp FswTopology.hpp FswTopologyDefs.hpp)
        configure_file("${CMAKE_CURRENT_LIST_DIR}/${TEMPLATE}.in" "${RENDERED}/${CONFIGURATION}${TEMPLATE}" @ONLY)
    endforeach ()
    configure_file("${CMAKE_CURRENT_LIST_DIR}/CMakeLists.txt.in" "${RENDERED}/CMakeLists.txt" @ONLY)
    add_subdirectory("${RENDERED}" "${RENDERED}")
endforeach ()
