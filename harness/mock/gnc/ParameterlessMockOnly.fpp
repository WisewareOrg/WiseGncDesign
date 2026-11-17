module Parameterless {

  @ s, the base tick's period
  constant tickPeriod = 1.0

  @ The ticks per run of the mock rate group: every tick
  constant mockDivider = 1

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x6000

  instance mockRateGroup: Svc.PassiveRateGroup base id 0x6100

  instance parameterless: HarnessMock.ParameterlessMock base id 0x6200

  @ A test mock with a parameter and no parameters function
  topology Gnc {

    instance rateGroupDriver
    instance mockRateGroup
    instance parameterless

    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> mockRateGroup.CycleIn
      mockRateGroup.RateGroupMemberOut[0] -> parameterless.schedIn
    }

    @ The base tick
    port tickIn = rateGroupDriver.CycleIn

  }

}
