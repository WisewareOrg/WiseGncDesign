module Sim {

  @ The simulation's side of the deployment: feeds sensor readings and drives the schedule
  passive component SimBridge {
    @ The navigation filter's configuration
    output port navConfigOut: Gnc.NavConfig
    @ The IMU reading of this tick
    output port imuOut: Gnc.ImuReading
    @ The schedule, standing in for a timer and rate group
    output port schedOut: [1] Svc.Sched
  }

}
