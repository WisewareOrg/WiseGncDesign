module MockGnc {

  @ A test mock both builds fly as an actuator: each step it sends one fixed wheel command
  @ provides: SYS901
  passive component Actuator {

    @ Steps the mock
    sync input port schedIn: Svc.Sched

    @ The fixed wheel command it sends each step
    output port wheelOut: Gnc.WheelCommand

  }

}
