register_fprime_module(
  AUTOCODER_INPUTS
    "${CMAKE_CURRENT_LIST_DIR}/ImuDeadReckoning.fpp"
  DEPENDS
    algorithms_imu_dead_reckoning
    Svc_PassiveRateGroup
)
