module SecondMockTwice {

  @ s, the base tick's period
  constant tickPeriod = 1.0

  @ The ticks per run of the mock rate group: every tick
  constant mockDivider = 1

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x6000

  instance mockRateGroup: Svc.PassiveRateGroup base id 0x6100

  instance second: HarnessMock.SecondMock base id 0x6200

  instance other: HarnessMock.SecondMock base id 0x6300

  @ Two instances of the second test mock, which one parameters function cannot tell apart
  topology Gnc {

    instance rateGroupDriver
    instance mockRateGroup
    instance second
    instance other

    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> mockRateGroup.CycleIn
      mockRateGroup.RateGroupMemberOut[0] -> second.schedIn
      mockRateGroup.RateGroupMemberOut[1] -> other.schedIn
    }

    @ The base tick
    port tickIn = rateGroupDriver.CycleIn

  }

}
