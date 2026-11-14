# Every configuration's GNC sub-topology; fsw/fprime/deployment renders a deployment for each.
file(GLOB GNC_SUB_TOPOLOGIES CONFIGURE_DEPENDS "${CMAKE_CURRENT_LIST_DIR}/*.fpp")
register_fprime_module(
  AUTOCODER_INPUTS
    ${GNC_SUB_TOPOLOGIES}
  DEPENDS
    algorithms_imu_dead_reckoning
    Svc_PassiveRateGroup
    Svc_RateGroupDriver
)
