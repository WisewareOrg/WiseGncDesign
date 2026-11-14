module Top {
  passive component Driver {
    output port tickOut: Gnc.Sched
  }
  instance drv: Driver base id 0x100
  @ deployment
  @ provides: SYS003
  topology Deploy {
    import Gnc.Gnc
    instance drv
    connections Tick {
      drv.tickOut -> Gnc.rg.CycleIn
    }
  }
}
