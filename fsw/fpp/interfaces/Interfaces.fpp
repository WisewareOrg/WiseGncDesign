module Gnc {

  @ A 3-vector
  array Vector3 = [3] F64

  @ A quaternion W X Y Z, Hamilton
  array Quaternion = [4] F64

  @ A 3x3 matrix, by rows
  array Matrix3 = [3] Vector3

  @ One IMU reading, in the IMU platform frame P
  struct ImuReading {
    angVelPlatform: Vector3 @< rad/s, the rate of the body frame with respect to ECI, in P
    accelPlatform: Vector3 @< m/s^2, non-gravitational acceleration, in P
  }

  @ Carries one IMU reading
  port ImuReading(reading: ImuReading)

  @ One wheel command: each wheel's motor torque
  struct WheelCommand {
    motorTorque: [36] F64 @< N*m, each wheel's motor torque, about its spin axis
  }

  @ Carries one wheel command
  port WheelCommand($command: WheelCommand)

  @ A command's response: F´'s own enumeration, put in every dictionary
  dictionary type CommandResponse = Fw.CmdResponse

  @ The state of the navigation estimate
  enum NavState {
    idle
    initialized
    propagated
    propagateAndUpdate
  }

}
