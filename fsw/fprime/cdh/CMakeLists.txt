register_fprime_module(
  AUTOCODER_INPUTS
    "${CMAKE_CURRENT_LIST_DIR}/GroundLink.fpp"
  SOURCES
    "${CMAKE_CURRENT_LIST_DIR}/GroundLink.cpp"
  HEADERS
    "${CMAKE_CURRENT_LIST_DIR}/GroundLink.hpp"
  DEPENDS
    fsw_fpp_interfaces
    Os
)

# Cdh.BusConverter's implementation and the lab's test pins on it, generated from FPP by
# fsw.codegen.bus_converter into this build directory whenever the interfaces' FPP or the generator
# changes. F´ requires a module's sources to exist at configure time, so the generated ones join the
# module here, outside the sub-builds, which only gather model information.
if (NOT DEFINED FPRIME_SUB_BUILD_TARGETS)
    file(GLOB WISE_CDH_INPUTS CONFIGURE_DEPENDS
        "${FPRIME_PROJECT_ROOT}/fsw/fpp/interfaces/*.fpp"
        "${FPRIME_PROJECT_ROOT}/fsw/codegen/*.py")
    add_custom_command(
        OUTPUT
            "${CMAKE_CURRENT_BINARY_DIR}/BusConverter.hpp"
            "${CMAKE_CURRENT_BINARY_DIR}/BusConverter.cpp"
            "${CMAKE_CURRENT_BINARY_DIR}/BusConverterPins.hpp"
        COMMAND "${Python_EXECUTABLE}" -m fsw.codegen.bus_converter "${CMAKE_CURRENT_BINARY_DIR}"
        WORKING_DIRECTORY "${FPRIME_PROJECT_ROOT}"
        DEPENDS ${WISE_CDH_INPUTS})
    target_sources(fsw_fprime_cdh PRIVATE
        "${CMAKE_CURRENT_BINARY_DIR}/BusConverter.hpp"
        "${CMAKE_CURRENT_BINARY_DIR}/BusConverter.cpp"
        "${CMAKE_CURRENT_BINARY_DIR}/BusConverterPins.hpp")
endif ()
