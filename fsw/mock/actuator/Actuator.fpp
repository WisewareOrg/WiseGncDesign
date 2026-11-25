module MockGnc {

  @ Values that fill most of a telemetry packet
  array Wide = [50] F64

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

    @ Counts one, as a step does, and writes `wide`
    sync command mark

    @ The steps and marks so far
    telemetry tally: U32

    @ Each mark's tally in thousands plus the element's index; written by a mark, not by a step
    telemetry wide: Wide

  }

}
