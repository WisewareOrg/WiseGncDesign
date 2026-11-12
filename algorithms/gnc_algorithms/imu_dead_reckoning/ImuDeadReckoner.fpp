module Gnc {

  @ Strapdown inertial dead reckoning from one IMU: the F´ build of the notebook's estimator
  passive component ImuDeadReckoner {

    @ Steps the estimate to the current time with the held IMU reading
    sync input port schedIn: Svc.Sched

    @ The IMU's latest reading, held until the next step
    sync input port imuIn: Gnc.ImuReading

    @ Boots the estimator idle with its configuration
    sync input port configureIn: Gnc.NavConfig

    @ Gives the estimator its state at the current time. Temporary: the initNavState command replaces it.
    sync input port initializeIn: Gnc.NavInit

    @ The deployment's clock
    time get port timeCaller

    @ Telemetry out
    telemetry port tlmOut

    @ The state of the estimate
    telemetry navState: Gnc.NavState

    @ Position of the body in ECI, x
    telemetry bodyEciPosX: F64 format "{} m"
    @ Position of the body in ECI, y
    telemetry bodyEciPosY: F64 format "{} m"
    @ Position of the body in ECI, z
    telemetry bodyEciPosZ: F64 format "{} m"

    @ Velocity of the body in ECI, x
    telemetry bodyEciVelX: F64 format "{} m/s"
    @ Velocity of the body in ECI, y
    telemetry bodyEciVelY: F64 format "{} m/s"
    @ Velocity of the body in ECI, z
    telemetry bodyEciVelZ: F64 format "{} m/s"

    @ Attitude quaternion taking body vectors into ECI, scalar part, W >= 0
    telemetry bodyEciAttitudeW: F64
    @ Attitude quaternion taking body vectors into ECI, x
    telemetry bodyEciAttitudeX: F64
    @ Attitude quaternion taking body vectors into ECI, y
    telemetry bodyEciAttitudeY: F64
    @ Attitude quaternion taking body vectors into ECI, z
    telemetry bodyEciAttitudeZ: F64

  }

}
