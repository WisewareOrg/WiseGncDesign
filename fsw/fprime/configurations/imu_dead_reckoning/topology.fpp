module WiseFsw {

  instance simTime: Sim.SimTime base id 0x100
  instance groundLink: Sim.GroundLink base id 0x200
  instance simBridge: Sim.SimBridge base id 0x300
  instance rateGroupDriver: Svc.RateGroupDriver base id 0x400
  instance cmdDisp: Svc.CommandDispatcher base id 0x500 queue size 10

  @ The flight software run inside the simulation: the dead reckoner, fed and ticked by the simulation,
  @ commanded and read by the ground
  deployment topology WiseFsw {

    import ImuDeadReckoning.Gnc

    instance simTime
    instance groundLink
    instance simBridge
    instance rateGroupDriver
    instance cmdDisp

    time connections instance simTime

    command connections instance cmdDisp

    telemetry connections instance groundLink { cmdDisp, ImuDeadReckoning.nav }

    connections RateGroups {
      simTime.CycleOut -> rateGroupDriver.CycleIn
      rateGroupDriver.CycleOut[0] -> ImuDeadReckoning.navRateGroup.CycleIn
    }

    connections Simulation {
      simBridge.navConfigOut -> ImuDeadReckoning.nav.configureIn
      simBridge.imuOut -> ImuDeadReckoning.nav.imuIn
    }

    connections Ground {
      groundLink.cmdOut -> cmdDisp.seqCmdBuff[0]
      cmdDisp.seqCmdStatus[0] -> groundLink.cmdResponseIn
    }

  }

}
