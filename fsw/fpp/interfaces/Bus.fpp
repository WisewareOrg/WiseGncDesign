module Bus {

  @ Basilisk's IMUSensorMsgPayload, field for field; bus_test.py holds it to the real message
  struct ImuSensorMsg {
    dvFramePlatform: [3] F64 @< m/s, accumulated DVs in platform
    accelPlatform: [3] F64 @< m/s2, apparent acceleration of the platform
    drFramePlatform: [3] F64 @< r, accumulated DRs in platform
    angVelPlatform: [3] F64 @< r/s, angular velocity in platform frame
  }

  @ Carries one IMU message
  port ImuSensorMsg(msg: ImuSensorMsg)

  @ Basilisk's ArrayMotorTorqueMsgPayload, field for field; bus_test.py holds it to the real message
  struct ArrayMotorTorqueMsg {
    motorTorque: [36] F64 @< N*m, each wheel's motor torque
  }

  @ Carries one wheel torque message
  port ArrayMotorTorqueMsg(msg: ArrayMotorTorqueMsg)

}
