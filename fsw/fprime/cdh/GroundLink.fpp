module Cdh {

  @ The ground's side of the deployment: commands up, responses and every telemetry write down, packed in telemetry packets
  passive component GroundLink {
    @ Command packets to the dispatcher
    output port cmdOut: Fw.Com
    @ Each command's response, by the ground's context
    sync input port cmdResponseIn: Fw.CmdResponse
    @ Telemetry from every component
    sync input port tlmIn: Fw.Tlm
  }

}
