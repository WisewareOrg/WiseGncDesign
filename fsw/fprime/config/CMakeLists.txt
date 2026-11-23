# The deployment's F´ configuration where it differs from the framework's default.
register_fprime_config(
    wise_config
  INTERFACE
  CONFIGURATION_OVERRIDES
    "${CMAKE_CURRENT_LIST_DIR}/TlmChanImplCfg.hpp"
)
