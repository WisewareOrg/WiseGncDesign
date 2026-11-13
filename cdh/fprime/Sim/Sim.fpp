module Sim {

  @ The deployment's clock, set to the simulation's time before each tick
  passive component SimTime {
    import Svc.Time
  }

  @ The ground's side of the deployment: commands up, responses and every telemetry write down
  passive component GroundLink {
    @ Command packets to the dispatcher
    output port cmdOut: Fw.Com
    @ Each command's response, by the ground's context
    sync input port cmdResponseIn: Fw.CmdResponse
    @ Telemetry from every component
    sync input port tlmIn: Fw.Tlm
  }

  @ The simulation's side of the deployment: feeds sensor readings and drives the schedule
  passive component SimBridge {
    @ The navigation filter's configuration
    output port navConfigOut: Gnc.NavConfig
    @ The navigation state to start from, given directly rather than by command
    output port navInitOut: Gnc.NavInit
    @ The IMU reading of this tick
    output port imuOut: Gnc.ImuReading
    @ The schedule, standing in for a timer and rate group
    output port schedOut: [1] Svc.Sched
  }

}
