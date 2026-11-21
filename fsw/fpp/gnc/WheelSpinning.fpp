module WheelSpinning {

  @ s, the base tick's period
  constant tickPeriod = 1.0

  @ The ticks per run of the spinner's rate group: the spinner runs every tick
  constant ctrlDivider = 1

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x2000 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    WheelSpinning::rateGroupDriver.configure(
        Svc::RateGroupDriver::DividerSet{{{WheelSpinning::ctrlDivider, 0}, {0, 0}, {0, 0}}});
    """
  }

  instance spinner: Gnc.WheelSpinner base id 0x2100

  instance ctrlRateGroup: Svc.PassiveRateGroup base id 0x2200 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    WheelSpinning::ctrlRateGroup.configure(Svc::PassiveRateGroup::ContextArray(0));
    """
  }

  @ The GNC partition of the wheel spinner's configuration: the spinner, run by its rate group at
  @ ctrlDivider ticks of the base tick; it takes no sensor role
  topology Gnc {

    instance rateGroupDriver
    instance spinner
    instance ctrlRateGroup

    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> ctrlRateGroup.CycleIn
      ctrlRateGroup.RateGroupMemberOut[0] -> spinner.schedIn
    }

    @ The base tick
    port tickIn = rateGroupDriver.CycleIn
    @ The wheel command of this tick
    port wheelOut = spinner.wheelOut

  }

}
