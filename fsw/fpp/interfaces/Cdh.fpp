module Cdh {

  @ Converts each sensor role's bus struct to the GNC's FPP type: a role's port pair, its stem the
  @ role, its input `<role>In` typed by the bus struct and its output `<role>Out` by the GNC struct;
  @ a configuration takes the role at its GNC sub-topology's port `<role>In`
  passive component BusConverter {

    @ The IMU's message, as the bus carries it
    sync input port imuIn: Bus.ImuSensorMsg

    @ The IMU's reading, as the GNC takes it
    output port imuOut: Gnc.ImuReading

  }

}
