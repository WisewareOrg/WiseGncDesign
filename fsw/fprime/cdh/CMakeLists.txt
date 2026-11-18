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

# fsw.codegen.bus_converter generates Cdh.BusConverter and its test pins into this build directory.
# F´ requires a module's sources to exist at configure time, so they join it outside the sub-builds.
if (NOT DEFINED FPRIME_SUB_BUILD_TARGETS)
    file(GLOB WISE_CDH_INPUTS CONFIGURE_DEPENDS
        "${FPRIME_PROJECT_ROOT}/fsw/fpp/interfaces/*.fpp"
        "${FPRIME_PROJECT_ROOT}/fsw/codegen/*.py")
    list(FILTER WISE_CDH_INPUTS EXCLUDE REGEX "_test\\.py$")
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
