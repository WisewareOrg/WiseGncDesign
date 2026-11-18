module MockActuation {

  @ s, the base tick's period
  constant tickPeriod = 1.0

  @ The ticks per run of the actuation rate group: every tick
  constant actuationDivider = 1

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x7000 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    MockActuation::rateGroupDriver.configure(
        Svc::RateGroupDriver::DividerSet{{{MockActuation::actuationDivider, 0}, {0, 0}, {0, 0}}});
    """
  }

  instance actuationRateGroup: Svc.PassiveRateGroup base id 0x7100 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    MockActuation::actuationRateGroup.configure(Svc::PassiveRateGroup::ContextArray(0));
    """
  }

  instance actuator: MockGnc.Actuator base id 0x7200

  @ The test mock flown on the wheel role, in both builds: it takes no sensor role
  topology Gnc {

    instance rateGroupDriver
    instance actuationRateGroup
    instance actuator

    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> actuationRateGroup.CycleIn
      actuationRateGroup.RateGroupMemberOut[0] -> actuator.schedIn
    }

    @ The base tick
    port tickIn = rateGroupDriver.CycleIn
    @ The wheel command of this tick
    port wheelOut = actuator.wheelOut

  }

}
