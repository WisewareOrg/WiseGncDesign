module WiseFsw {

  instance simTime: Sim.SimTime base id 0x100
  instance groundLink: Cdh.GroundLink base id 0x200
  instance labBusDriver: Bus.LabBusDriver base id 0x300
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

  @ The CDH: each sensor's bus struct converted to the GNC's struct, and each actuator's GNC struct
  @ to its bus struct; its implementation is generated into the build directory
  instance cdh: Cdh.BusConverter base id 0x700 at "../cdh/BusConverter.hpp"

}
