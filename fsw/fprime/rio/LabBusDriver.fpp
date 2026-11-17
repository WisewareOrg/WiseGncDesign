module Bus {

  @ The RIO bus driver the lab uses: it receives raw bus bytes from the bus emulator and delivers
  @ them on serial ports to the typed bus ports they connect to. It is in module Bus because F´'s
  @ topology autocoder names a connected port's serializer in the component's own namespace, and
  @ every bus port is declared in Bus.
  passive component LabBusDriver {
    @ Bus messages into the deployment, held in reserve: each connects to one typed bus input
    @ port, so an added sensor takes an unconnected one.
    output port busOut: [8] serial
  }

}
