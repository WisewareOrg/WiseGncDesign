module HarnessMock {

  @ The harness's first test mock: it claims SYS901, and once commanded to fail its next step raises
  @ provides: SYS901
  passive component FirstMock {

    @ Steps the mock
    sync input port schedIn: Svc.Sched

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

    @ A parameter the ground writes from the case's scenario
    param gain: F64

    @ Makes the next step raise
    sync command fail

  }

}
