module WiseFsw {

  instance simTime: Sim.SimTime base id 0x100
  instance groundLink: Sim.GroundLink base id 0x200
  instance simBridge: Sim.SimBridge base id 0x300
  instance cmdDisp: Svc.CommandDispatcher base id 0x500 queue size 10

}
