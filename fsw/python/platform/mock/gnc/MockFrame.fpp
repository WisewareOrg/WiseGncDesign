module MockFrame {

  @ s, the base tick's period
  constant tickPeriod = 0.5

  @ The ticks per run of the fast rate group: every tick
  constant fastDivider = 1

  @ The ticks per run of the slow rate group: every second tick
  constant slowDivider = 2

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x5000

  instance source: MockGnc.Source base id 0x5100

  instance sink: MockGnc.Sink base id 0x5200

  instance fastRateGroup: Svc.PassiveRateGroup base id 0x5300

  instance slowRateGroup: Svc.PassiveRateGroup base id 0x5400

  @ The mock GNC: the source, run every tick, feeding the sink, run every second tick
  topology Gnc {

    instance rateGroupDriver
    instance source
    instance sink
    instance fastRateGroup
    instance slowRateGroup

    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> fastRateGroup.CycleIn
      rateGroupDriver.CycleOut[1] -> slowRateGroup.CycleIn
      fastRateGroup.RateGroupMemberOut[0] -> source.schedIn
      slowRateGroup.RateGroupMemberOut[0] -> sink.schedIn
    }

    connections Data {
      source.sampleOut -> sink.sampleIn
    }

    @ The base tick
    port tickIn = rateGroupDriver.CycleIn

  }

}
