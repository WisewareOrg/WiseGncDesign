module ImuDeadReckoning {

  @ The ticks per run of nav's rate group: nav runs every tick
  constant navDivider = 1

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x400 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    ImuDeadReckoning::rateGroupDriver.configure(
        Svc::RateGroupDriver::DividerSet{{{ImuDeadReckoning::navDivider, 0}, {0, 0}, {0, 0}}});
    """
  }

  instance nav: Gnc.ImuDeadReckoner base id 0x1000

  instance navRateGroup: Svc.PassiveRateGroup base id 0x1100 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    ImuDeadReckoning::navRateGroup.configure(Svc::PassiveRateGroup::ContextArray(0));
    """
  }

  @ The GNC partition of the dead reckoner's configuration: nav, run by its rate group at
  @ navDivider ticks of the base tick
  topology Gnc {

    instance rateGroupDriver
    instance nav
    instance navRateGroup

    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> navRateGroup.CycleIn
      navRateGroup.RateGroupMemberOut[0] -> nav.schedIn
    }

    @ The base tick
    port tickIn = rateGroupDriver.CycleIn
    @ The IMU reading of this tick
    port imuIn = nav.imuIn

  }

}
