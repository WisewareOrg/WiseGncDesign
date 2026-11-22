module Gnc {

  @ A test controller that keeps a reaction wheel spinning: each step it commands one constant
  @ motor torque on the first wheel
  @ provides: SYS002
  passive component WheelSpinner {

    @ Steps the spinner
    sync input port schedIn: Svc.Sched

    @ The wheel command it sends each step
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

    @ Parameter reads
    param get port prmGetOut

    @ Parameter saves to PrmDb
    param set port prmSetOut

    @ N*m, the motor torque commanded on the first wheel
    param motorTorque: F64

    @ The motor torque commanded on the first wheel this step
    telemetry wheelTorque: F64 format "{} N*m"

  }

}
