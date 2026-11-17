module HarnessMock {

  @ A test mock that claims no capability
  passive component UnclaimedMock {

    @ Steps the mock
    sync input port schedIn: Svc.Sched

  }

}
