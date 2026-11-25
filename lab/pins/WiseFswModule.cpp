// The deployment's Python interface: a hand-written pybind11 module.
// One deployment per loaded copy: its component instances are the topology's globals.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <string>
#include <vector>

#include "BusConverterPins.hpp"
#include "lab/pins/FprimePins.hpp"

namespace py = pybind11;

PYBIND11_MODULE(WISE_FSW_MODULE, m) {
    m.doc() = "The WiseFsw F´ deployment, run inside the simulation's process; set up by boot, once per copy.";

    Pins::registerAssertHook();
    busConverterPins(m);

    m.def(
        "boot",
        [](const std::string& prm_path, const std::vector<U32>& parameter_ids) { Pins::boot(prm_path, parameter_ids); },
        py::arg("prm_path"), py::arg("parameter_ids"),
        "Sets the topology up and boots it at t = 0 s, every component idle: PrmDb loads prm_path, an absolute "
        "path whose directory is its sandbox. Raises ValueError for a relative path, one in the root directory or "
        "one longer than F´'s file names hold, and RuntimeError naming each of parameter_ids that is not valid once "
        "loaded. A copy boots once: a second boot raises RuntimeError.");

    m.def(
        "uplink",
        [](const py::bytes& packet, U32 context) {
            Pins::uplink(reinterpret_cast<const U8*>(PyBytes_AS_STRING(packet.ptr())), py::len(packet), context);
        },
        py::arg("packet"), py::arg("context"),
        "Queues one F´ command packet at the dispatcher under the ground's context; it runs at the next step.");

    m.def(
        "receive_buffer",
        [](I16 port, U64 size) {
            return py::memoryview::from_memory(Pins::receiveBuffer(port, size), static_cast<py::ssize_t>(size));
        },
        py::arg("port"), py::arg("size"),
        "Makes LabBusDriver.busOut[port]'s receive buffer of size bytes and returns it, writable: each step "
        "pushes its bytes out on the port. Raises IndexError for a port past the driver's, and RuntimeError for "
        "a port that already has one or after the first step.");

    m.def(
        "transmit_buffer",
        [](I16 port, U64 size) {
            return py::memoryview::from_memory(static_cast<const void*>(Pins::transmitBuffer(port, size)),
                                               static_cast<py::ssize_t>(size));
        },
        py::arg("port"), py::arg("size"),
        "Makes LabBusDriver.busIn[port]'s transmit buffer of size bytes and returns it, read-only: it holds the "
        "bytes the GNC last sent the port. Bytes of another size sent the port trip F´'s assert. Raises as "
        "receive_buffer does.");

    m.def(
        "step",
        [](U64 t_ns) { return Pins::step(t_ns); },
        py::arg("t_ns"),
        "Sets the clock to t_ns (ns), runs the queued commands, pushes each receive buffer out on its "
        "LabBusDriver.busOut port in port order and ticks the rate groups once. A buffer the connected port does "
        "not deserialize exactly trips F´'s assert. Returns the transmit buffers the step wrote, bit n for "
        "LabBusDriver.busIn[n].");

    m.def(
        "pump", [](int rounds) { Pins::pump(rounds); }, py::arg("rounds") = Pins::defaultRounds(),
        "Runs the active components until no queue holds a message; raises RuntimeError naming a queue that "
        "still does after `rounds` rounds.");

    m.def(
        "telemetry",
        []() {
            const std::vector<U8>& downlink = Pins::downlink();
            const std::vector<U32>& sizes = Pins::packetSizes();
            py::tuple drained = py::make_tuple(
                py::bytes(reinterpret_cast<const char*>(downlink.data()), downlink.size()),
                py::bytes(reinterpret_cast<const char*>(sizes.data()), sizes.size() * sizeof(U32)));
            Pins::clearDownlink();
            return drained;
        },
        "Every telemetry packet downlinked since the last call, oldest first: (the packets back to back, each "
        "packet's size as native U32).");

    m.def(
        "responses",
        []() {
            py::list responses;
            for (const auto& response : Pins::responses()) {
                responses.append(py::make_tuple(response.context, response.response));
            }
            Pins::clearResponses();
            return responses;
        },
        "Every command response since the last call, oldest first: (context, Fw.CmdResponse value).");
}
