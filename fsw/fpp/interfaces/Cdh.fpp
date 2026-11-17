module Cdh {

  @ Converts each role's struct between the bus and the GNC: a role's port pair, its stem the role,
  @ an input `<role>In` and an output `<role>Out`. A sensor's input is typed by the bus struct and
  @ its output by the GNC struct; an actuator's the reverse. A configuration takes a sensor role at
  @ its GNC sub-topology's port `<role>In` and an actuator role at its port `<role>Out`
  passive component BusConverter {

    @ The IMU's message, as the bus carries it
    sync input port imuIn: Bus.ImuSensorMsg

    @ The IMU's reading, as the GNC takes it
    output port imuOut: Gnc.ImuReading

    @ The wheel's command, as the GNC sends it
    sync input port wheelIn: Gnc.WheelCommand

    @ The wheel's torque message, as the bus carries it
    output port wheelOut: Bus.ArrayMotorTorqueMsg

  }

}
