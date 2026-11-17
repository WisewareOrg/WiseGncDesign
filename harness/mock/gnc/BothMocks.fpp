module BothMocks {

  @ s, the base tick's period
  constant tickPeriod = 1.0

  @ The ticks per run of the mock rate group: every tick
  constant mockDivider = 1

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x6000

  instance mockRateGroup: Svc.PassiveRateGroup base id 0x6100

  instance first: HarnessMock.FirstMock base id 0x6200

  instance second: HarnessMock.SecondMock base id 0x6300

  @ Both test mocks, claiming SYS901 and SYS902
  topology Gnc {

    instance rateGroupDriver
    instance mockRateGroup
    instance first
    instance second

    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> mockRateGroup.CycleIn
      mockRateGroup.RateGroupMemberOut[0] -> first.schedIn
      mockRateGroup.RateGroupMemberOut[1] -> second.schedIn
    }

    @ The base tick
    port tickIn = rateGroupDriver.CycleIn

  }

}
