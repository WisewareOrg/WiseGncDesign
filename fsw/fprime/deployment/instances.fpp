module WiseFsw {

  instance simTime: Sim.SimTime base id 0x100
  instance groundLink: Sim.GroundLink base id 0x200
  instance simBridge: Sim.SimBridge base id 0x300
  instance cmdDisp: Svc.CommandDispatcher base id 0x500 queue size 10

  @ Loads the case's parameter file at boot; its sandbox is the file's directory
  instance prmDb: Svc.PrmDb base id 0x600 queue size 10 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    WiseFsw::prmDb.configure(state.prmPath);
    WiseFsw::prmDb.configureSandbox(state.prmDirectory);
    """
    phase Fpp.ToCpp.Phases.readParameters """
    WiseFsw::prmDb.readParamFile();
    """
  }

}
