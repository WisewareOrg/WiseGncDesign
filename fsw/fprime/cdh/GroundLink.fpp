module Sim {

  @ The ground's side of the deployment: commands up, responses and every telemetry write but
  @ health's down
  passive component GroundLink {
    @ Command packets to the dispatcher
    output port cmdOut: Fw.Com
    @ Each command's response, by the ground's context
    sync input port cmdResponseIn: Fw.CmdResponse
    @ Telemetry from every component, health instances' dropped
    sync input port tlmIn: Fw.Tlm
  }

}
