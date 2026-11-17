module HarnessMock {

  @ A test mock with a parameter, whose notebook gives no parameters function
  @ provides: SYS901
  passive component ParameterlessMock {

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

    @ A parameter no function gives
    param gain: F64

  }

}
