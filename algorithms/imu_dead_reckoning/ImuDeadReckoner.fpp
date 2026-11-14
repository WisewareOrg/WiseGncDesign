module Gnc {

  @ Strapdown inertial dead reckoning from one IMU: the F´ build of the notebook's estimator
  passive component ImuDeadReckoner {

    @ Steps the estimate to the current time with the held IMU reading
    sync input port schedIn: Svc.Sched

    @ The IMU's latest reading, held until the next step
    sync input port imuIn: Gnc.ImuReading

    @ The deployment's clock
    time get port timeCaller

    @ Telemetry out
    telemetry port tlmOut

    @ Command registration
    command reg port cmdRegOut

    @ Command input
    command recv port cmdIn

    @ Command responses
    command resp port cmdResponseOut

    @ Parameter reads
    param get port prmGetOut

    @ Parameter saves to PrmDb
    param set port prmSetOut

    @ m^3/s^2, the central body's gravitational parameter
    param mu: F64

    @ The IMU's mounting [PB], v_P = [PB] v_B
    param dcm_PB: Gnc.Matrix3

    include "../../fsw/fpp/interfaces/Nav/InitNavState.fppi"
    include "../../fsw/fpp/interfaces/Nav/NavState.fppi"
    include "../../fsw/fpp/interfaces/Nav/BodyEci.fppi"

  }

}
