module MockGnc {

  @ A value one mock algorithm passes the other
  struct Sample {
    value: F64
  }

  @ Carries one sample
  port Sample(sample: Sample)

  @ The mock algorithm that runs first: each step it sends a sample, and a command sets its level
  passive component Source {

    @ Steps the mock
    sync input port schedIn: Svc.Sched

    @ The sample it sends each step
    output port sampleOut: Sample

    @ The deployment's clock
    time get port timeCaller

    @ Telemetry out
    telemetry port tlmOut

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

    @ The factor each sample's level is scaled by
    param gain: F64

    @ Sets the level each later sample carries
    sync command setLevel(level: F64)

    @ Writes nothing
    sync command reset

    @ The level each sample carries
    telemetry level: F64

  }

  @ The mock algorithm that runs second: it receives the source's sample
  passive component Sink {

    @ Steps the mock
    sync input port schedIn: Svc.Sched

    @ The source's latest sample, held until the next step
    sync input port sampleIn: Sample

    @ The deployment's clock
    time get port timeCaller

    @ Telemetry out
    telemetry port tlmOut

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

    @ What each received sample is offset by
    param offset: F64

    @ The sample received, offset
    telemetry received: F64

  }

}
