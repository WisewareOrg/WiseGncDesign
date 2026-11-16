module Bus {

  @ The bus driver's stand-in: bytes from the bus, as the bus emulator writes them, delivered on
  @ serial ports to the typed bus ports they connect to. It is in module Bus because F´'s topology
  @ autocoder names a connected port's serializer in the component's own namespace, and every bus
  @ port is declared in Bus
  passive component SimHub {
    @ Bus messages into the deployment, held in reserve: each connects to one typed bus input
    @ port, so an added sensor takes an unconnected one
    output port busOut: [8] serial
  }

}
