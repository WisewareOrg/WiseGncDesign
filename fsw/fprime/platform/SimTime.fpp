module Sim {

  @ The deployment's clock and its tick: set to the simulation's time before each tick, it then
  @ drives the rate groups
  passive component SimTime {
    import Svc.Time
    import Drv.Tick
  }

}
