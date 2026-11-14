module Rio {

  @ Spike bus struct mirroring the fields of Basilisk's IMUSensorMsgPayload that today's IMU path reads,
  @ plus a U64 time tag so the check covers mixed widths
  struct ImuSensorMsg {
    timeTag: U64 @< ns
    AngVelPlatform: [3] F64 @< rad/s, in P
    AccelPlatform: [3] F64 @< m/s^2, in P
  }

  @ One IMU bus message
  port ImuBus(msg: ImuSensorMsg)

  @ The bus driver stand-in: bytes from the bus emulator out on serial ports, and back
  passive component SimHub {
    @ Bus messages into the deployment; each connects to a typed bus input port
    output port busOut: [2] serial

    @ Bus messages out of the deployment; any typed bus output port connects here
    sync input port busIn: [2] serial
  }

  @ Receives the IMU bus message and echoes it back out
  passive component ImuSink {
    sync input port imuIn: ImuBus
    output port imuEcho: ImuBus
  }

}
