module Spike {

  instance simTime: Sim.SimTime base id 0x100
  instance simHub: Rio.SimHub base id 0x200
  instance imuSink: Rio.ImuSink base id 0x300
  instance textLogger: Svc.PassiveTextLogger base id 0x400
  instance cmdDisp: Svc.CommandDispatcher base id 0x500 queue size 10
  instance prmDb: Svc.PrmDb base id 0x600 queue size 10 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    prmDb.configure(state.prmPath);
    prmDb.configureSandbox("/");
    """
    phase Fpp.ToCpp.Phases.readParameters """
    prmDb.readParamFile();
    """
  }
  instance nav: Nav.NavPrm base id 0x1000

  deployment topology Spike {

    instance simTime
    instance simHub
    instance imuSink
    instance textLogger
    instance cmdDisp
    instance prmDb
    instance nav

    time connections instance simTime
    command connections instance cmdDisp
    param connections instance prmDb
    text event connections instance textLogger

    connections Rio {
      simHub.busOut[0] -> imuSink.imuIn
      imuSink.imuEcho -> simHub.busIn[0]
    }

  }

}
