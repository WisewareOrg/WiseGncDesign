module Bus {

  @ Basilisk's IMUSensorMsgPayload, field for field; bus_test.py holds it to the real message
  struct ImuSensorMsg {
    dvFramePlatform: [3] F64 @< m/s, accumulated DVs in platform
    accelPlatform: [3] F64 @< m/s2, apparent acceleration of the platform
    drFramePlatform: [3] F64 @< r, accumulated DRs in platform
    angVelPlatform: [3] F64 @< r/s, angular velocity in platform frame
  }

}
