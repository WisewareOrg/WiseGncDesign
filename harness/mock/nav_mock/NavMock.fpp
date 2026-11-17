module HarnessMock {

  @ The judge's test mock: it claims SYS901 and writes the nav role's estimate channels
  @ provides: SYS901
  passive component NavMock {

    @ Steps the mock
    sync input port schedIn: Svc.Sched

    @ The deployment's clock
    time get port timeCaller

    @ Telemetry out
    telemetry port tlmOut

    include "../../../fsw/fpp/interfaces/Nav/BodyEci.fppi"

  }

}
