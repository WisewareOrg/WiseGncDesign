module MockFlight {

  @ s, the base tick's period
  constant tickPeriod = 1.0

  @ The ticks per run of the mock rate group: every tick
  constant mockDivider = 1

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x6000
  instance mockRateGroup: Svc.PassiveRateGroup base id 0x6100
  instance nav: HarnessMock.Mock base id 0x6200

  @ The test mock flown as the nav role, which the analyzers read
  topology Gnc {

    instance rateGroupDriver
    instance mockRateGroup
    instance nav

    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> mockRateGroup.CycleIn
      mockRateGroup.RateGroupMemberOut[0] -> nav.schedIn
    }

    @ The base tick
    port tickIn = rateGroupDriver.CycleIn

  }

}
