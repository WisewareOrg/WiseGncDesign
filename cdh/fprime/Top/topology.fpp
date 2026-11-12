module WiseFsw {

  instance simTime: Sim.SimTime base id 0x100
  instance tlmCapture: Sim.TlmCapture base id 0x200
  instance simBridge: Sim.SimBridge base id 0x300
  instance nav: Gnc.ImuDeadReckoner base id 0x1000

  @ The flight software run inside the simulation: the dead reckoner, fed and ticked by the simulation
  deployment topology WiseFsw {

    instance simTime
    instance tlmCapture
    instance simBridge
    instance nav

    time connections instance simTime

    telemetry connections instance tlmCapture

    connections Simulation {
      simBridge.imuOut -> nav.imuIn
      simBridge.schedOut[0] -> nav.schedIn
    }

  }

}
