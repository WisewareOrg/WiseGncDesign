module Mock {

  enum Mode {
    slow
    fast
  }

  passive component Mock {

    @ Sets the mock
    sync command setMock(
      gain: F32
      enabled: bool
      mode: Mode
      offset: Gnc.Vector3
      mounting: Gnc.Matrix3
      count: U8
    )

    sync command label(note: string)
    sync command setMode(mode: Mode)
    sync command setOffset(offset: Gnc.Vector3, gain: F32)

    telemetry gain: F32 format "{} rad"
    telemetry enabled: bool
    telemetry mode: Mode
    telemetry count: U8
    telemetry offset: Gnc.Vector3 format "{} m"
    telemetry mounting: Gnc.Matrix3

    include "Extra.fppi"

    time get port timeCaller
    telemetry port tlmOut
    command reg port cmdRegOut
    command recv port cmdIn
    command resp port cmdResponseOut

  }

}
