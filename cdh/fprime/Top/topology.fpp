module WiseFsw {

  instance simTime: Sim.SimTime base id 0x100
  instance groundLink: Sim.GroundLink base id 0x200
  instance simBridge: Sim.SimBridge base id 0x300
  instance cmdDisp: Svc.CommandDispatcher base id 0x500 queue size 10
  instance nav: Gnc.ImuDeadReckoner base id 0x1000

  @ The flight software run inside the simulation: the dead reckoner, fed and ticked by the simulation,
  @ commanded and read by the ground
  deployment topology WiseFsw {

    instance simTime
    instance groundLink
    instance simBridge
    instance cmdDisp
    instance nav

    time connections instance simTime

    command connections instance cmdDisp

    telemetry connections instance groundLink

    connections Simulation {
      simBridge.navConfigOut -> nav.configureIn
      simBridge.navInitOut -> nav.initializeIn
      simBridge.imuOut -> nav.imuIn
      simBridge.schedOut[0] -> nav.schedIn
    }

    connections Ground {
      groundLink.cmdOut -> cmdDisp.seqCmdBuff[0]
      cmdDisp.seqCmdStatus[0] -> groundLink.cmdResponseIn
    }

  }

}
