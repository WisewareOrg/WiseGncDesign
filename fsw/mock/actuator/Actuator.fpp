module MockGnc {

  @ A test mock both builds fly as an actuator: each step it sends one fixed wheel command and
  @ counts the step; a command counts too, so one frame can write the tally twice
  @ provides: SYS901
  passive component Actuator {

    @ Steps the mock
    sync input port schedIn: Svc.Sched

    @ The fixed wheel command it sends each step
    output port wheelOut: Gnc.WheelCommand

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

    @ Counts one, as a step does
    sync command mark

    @ Asks F´'s allocator for memory, which it refuses once the deployment has stepped; the Python
    @ build has no allocator
    sync command allocate

    @ The steps and marks so far
    telemetry tally: U32

  }

}
