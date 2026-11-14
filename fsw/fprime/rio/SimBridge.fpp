module Sim {

  @ The simulation's side of the deployment: feeds sensor readings
  passive component SimBridge {
    @ The IMU reading of this tick
    output port imuOut: Gnc.ImuReading
  }

}
