module Gnc {

  @ A 3-vector
  array Vector3 = [3] F64

  @ One IMU reading, in the IMU platform frame P
  port ImuReading(
    angVelPlatform: Vector3 @< rad/s, the rate of the body frame with respect to ECI, in P
    accelPlatform: Vector3 @< m/s^2, non-gravitational acceleration, in P
  )

  @ The state of the navigation estimate
  enum NavState {
    idle
    initialized
    propagated
    propagateAndUpdate
  }

}
