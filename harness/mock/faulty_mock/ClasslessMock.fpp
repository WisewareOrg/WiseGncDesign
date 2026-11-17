module HarnessMock {

  @ A test mock whose notebook defines no class for it
  @ provides: SYS901
  passive component ClasslessMock {

    @ Steps the mock
    sync input port schedIn: Svc.Sched

  }

}
