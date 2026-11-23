module Cdh {

  @ The ground's side of the deployment: commands up, responses and telemetry packets down
  passive component GroundLink {
    @ Command packets to the dispatcher
    output port cmdOut: Fw.Com
    @ Each command's response, by the ground's context
    sync input port cmdResponseIn: Fw.CmdResponse
    @ Telemetry packets from the telemetry database, once a frame
    sync input port downlinkIn: Fw.Com
  }

}
