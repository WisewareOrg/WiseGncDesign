module HarnessMock {

  @ The harness's second test mock: it claims SYS902, and has no parameter
  @ provides: SYS902
  passive component SecondMock {

    @ Steps the mock
    sync input port schedIn: Svc.Sched

  }

}
