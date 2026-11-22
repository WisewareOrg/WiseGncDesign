module Bus {

  @ The RIO bus driver the lab uses: it receives raw bus bytes from the bus emulator and delivers
  @ them on serial ports to the typed bus ports they connect to, and takes typed bus structs back
  @ as bytes on serial ports, which the lab drains. It is in module Bus because F´'s topology
  @ autocoder names a connected port's serializer in the component's own namespace, and every bus
  @ port is declared in Bus.
  passive component LabBusDriver {
    @ Bus messages into the deployment, held in reserve: each connects to one typed bus input
    @ port, so an added sensor takes an unconnected one.
    output port busOut: [8] serial

    @ Bus messages out of the deployment, held in reserve: each is fed by one typed bus output
    @ port, so an added actuator takes an unconnected one.
    sync input port busIn: [8] serial
  }

}
