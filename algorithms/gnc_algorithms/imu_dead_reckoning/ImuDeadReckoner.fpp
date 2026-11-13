module Gnc {

  @ Strapdown inertial dead reckoning from one IMU: the F´ build of the notebook's estimator
  passive component ImuDeadReckoner {

    @ Steps the estimate to the current time with the held IMU reading
    sync input port schedIn: Svc.Sched

    @ The IMU's latest reading, held until the next step
    sync input port imuIn: Gnc.ImuReading

    @ Boots the estimator idle with its configuration
    sync input port configureIn: Gnc.NavConfig

    @ Gives the estimator its state at the current time, directly rather than by command
    sync input port initializeIn: Gnc.NavInit

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

    include "../../../cdh/fprime/Interfaces/Nav/InitNavState.fppi"
    include "../../../cdh/fprime/Interfaces/Nav/NavState.fppi"
    include "../../../cdh/fprime/Interfaces/Nav/BodyEci.fppi"

  }

}
