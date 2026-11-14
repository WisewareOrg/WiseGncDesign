module Gnc {
  @ nav runs every tick
  constant navDivider = 1
  @ ctrl every 10th tick
  constant ctrlDivider = 10
  constant tickHz = 100
  constant gain = 2.5
  constant name = "gnc"

  port Sched(ctx: U32)

  @ Rate group driver stand-in
  @ provides: SYS001
  passive component RateGroup {
    sync input port CycleIn: Sched
    output port RateGroupMemberOut: [3] Sched
  }

  @ A navigation component
  @ provides: SRS010 free text, with spaces
  passive component Nav {
    sync input port schedIn: Sched
    output port dummyOut: Sched
  }

  passive component Ctrl {
    sync input port schedIn: Sched
  }

  passive component Log {
    sync input port schedIn: Sched
  }

  @ pre-annotation on instance
  instance nav: Nav base id 0x1000 \
    @< post-annotation on instance nav
  instance ctrl: Ctrl base id 0x2000
  instance log: Log base id 0x3000
  instance rg: RateGroup base id 0x4000

  @ GNC sub-topology
  @ provides: SYS002
  topology Gnc {
    instance nav
    instance ctrl
    instance log
    instance rg
    connections Rates {
      rg.RateGroupMemberOut[0] -> nav.schedIn
      rg.RateGroupMemberOut[1] -> ctrl.schedIn
      rg.RateGroupMemberOut[2] -> log.schedIn
    }
  }
}
