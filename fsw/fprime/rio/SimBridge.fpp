module Sim {

  @ The simulation's side of the deployment: feeds sensor readings
  passive component SimBridge {
    @ The navigation filter's configuration
    output port navConfigOut: Gnc.NavConfig
    @ The IMU reading of this tick
    output port imuOut: Gnc.ImuReading
  }

}
