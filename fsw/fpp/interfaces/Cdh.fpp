module Cdh {

  @ Converts each sensor role's bus struct to the GNC's FPP type: a role's port pair, its stem the
  @ role, its input typed by the bus struct and its output by the GNC struct
  passive component BusConverter {

    @ The IMU's message, as the bus carries it
    sync input port imuIn: Bus.ImuSensorMsg

    @ The IMU's reading, as the GNC takes it
    output port imuOut: Gnc.ImuReading

  }

}
