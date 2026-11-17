module HarnessMock {

  @ The harness's test mock: it writes a fixed nav state each step, and once commanded to fail its
  @ next step raises
  @ provides: SYS901
  passive component Mock {

    @ Steps the mock
    sync input port schedIn: Svc.Sched
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
    @ A parameter the ground writes from the case's scenario
    param gain: F64

    @ Makes the next step raise
    sync command fail

    include "../fpp/interfaces/Nav/BodyEci.fppi"
    include "../fpp/interfaces/Nav/NavState.fppi"
    include "../fpp/interfaces/Nav/InitNavState.fppi"

  }

}
