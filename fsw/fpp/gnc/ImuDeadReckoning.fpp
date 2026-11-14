module ImuDeadReckoning {

  @ The ticks per run of nav's rate group: nav runs every tick
  constant navDivider = 1

  instance nav: Gnc.ImuDeadReckoner base id 0x1000
  instance navRateGroup: Svc.PassiveRateGroup base id Ids.healthBase + 0x100

  @ The GNC partition of the dead reckoner's configuration: nav, run by its rate group
  topology Gnc {

    instance nav
    instance navRateGroup

    connections RateGroups {
      navRateGroup.RateGroupMemberOut[0] -> nav.schedIn
    }

  }

}
