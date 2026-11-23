// The deployment's Python interface: a hand-written pybind11 module.
// One deployment per loaded copy: its component instances are the topology's globals.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <stdexcept>
#include <string>
#include <vector>

#include "Fw/Types/Assert.hpp"
#include "Os/Os.hpp"
#include "config/FppConstantsAc.hpp"
#include "fsw/fprime/cdh/BusConverterPins.hpp"
#include "fsw/fprime/platform/Cooperative.hpp"
#include WISE_FSW_TOPOLOGY_HEADER

namespace py = pybind11;

namespace {

Sim::Cooperative g_cooperative;
bool g_booted = false;
bool g_stepped = false;

//! Refuses a buffer on a port LabBusDriver lacks, on one that has one, or after the first step.
void checkBufferPort(FwIndexType port, bool made, const char* direction) {
    if (port < 0 || port >= Bus::LabBusDriver::PORTS) {
        throw py::index_error("port " + std::to_string(port) + " is past LabBusDriver's " +
                              std::to_string(Bus::LabBusDriver::PORTS) + " ports");
    }
    if (made) {
        throw std::runtime_error("port " + std::to_string(port) + " already has a " + direction + " buffer");
    }
    if (g_stepped) {
        throw std::runtime_error(std::string("a ") + direction + " buffer is made at boot, not after the first step");
    }
}

//! Raises an F´ assert in Python as a std::runtime_error carrying F´'s own text.
class RaisingAssertHook final : public Fw::AssertHook {
  public:
    void printAssert(const CHAR* msg) override { this->m_text = msg; }
    void doAssert() override { throw std::runtime_error(this->m_text); }

  private:
    std::string m_text;
};

RaisingAssertHook g_assertHook;

}  // namespace

PYBIND11_MODULE(WISE_FSW_MODULE, m) {
    m.doc() = "The WiseFsw F´ deployment, run inside the simulation's process; set up by boot, once per copy.";

    g_assertHook.registerHook();
    busConverterPins(m);

    m.def(
        "boot",
        [](const std::string& prm_path, const std::vector<FwPrmIdType>& parameter_ids) {
            if (g_booted) {
                throw std::runtime_error("already booted: power-cycle by loading a fresh copy");
            }
            const std::string directory = prm_path.substr(0, prm_path.rfind('/'));
            if (prm_path.empty() || prm_path.front() != '/' || directory.empty()) {
                throw py::value_error("the parameter file " + prm_path +
                                      " is not an absolute path in a directory below the root");
            }
            // F´ resolves every file path in a buffer of FileNameStringSize bytes, its terminator included.
            const std::size_t longest = FileNameStringSize - 1;
            if (prm_path.size() > longest) {
                throw py::value_error("the parameter file " + prm_path + " is " + std::to_string(prm_path.size()) +
                                      " bytes, past F´'s limit of " + std::to_string(longest) +
                                      " (FileNameStringSize less its terminator)");
            }
            g_booted = true;
            Os::init();
            Os::Task::registerTaskRegistry(&g_cooperative);
            Os::Queue::setRegistry(&g_cooperative);
            WiseFsw::setupTopology(WiseFsw::TopologyState{prm_path.c_str(), directory.c_str()});
            std::string invalid;
            for (const FwPrmIdType id : parameter_ids) {
                Fw::ParamBuffer value;
                if (WiseFsw::prmDb.getPrm_handlerBase(0, id, value) != Fw::ParamValid::VALID) {
                    invalid += (invalid.empty() ? "" : ", ") + std::to_string(id);
                }
            }
            if (!invalid.empty()) {
                throw std::runtime_error("parameters " + invalid + " are not valid after loading " + prm_path);
            }
        },
        py::arg("prm_path"), py::arg("parameter_ids"),
        "Sets the topology up and boots it at t = 0 s, every component idle: PrmDb loads prm_path, an absolute "
        "path whose directory is its sandbox. Raises ValueError for a relative path, one in the root directory or "
        "one longer than F´'s file names hold, and RuntimeError naming each of parameter_ids that is not valid once "
        "loaded. A copy boots once: a second boot raises RuntimeError.");

    m.def(
        "uplink",
        [](const py::bytes& packet, U32 context) {
            const std::string data = packet;
            Fw::ComBuffer buffer;
            if (buffer.setBuff(reinterpret_cast<const U8*>(data.data()), static_cast<FwSizeType>(data.size())) !=
                Fw::FW_SERIALIZE_OK) {
                throw py::value_error("a command packet of " + std::to_string(data.size()) + " bytes exceeds the " +
                                      std::to_string(buffer.getCapacity()) + "-byte buffer");
            }
            WiseFsw::groundLink.uplink(buffer, context);
        },
        py::arg("packet"), py::arg("context"),
        "Queues one F´ command packet at the dispatcher under the ground's context; it runs at the next step.");

    m.def(
        "receive_buffer",
        [](FwIndexType port, FwSizeType size) {
            checkBufferPort(port, WiseFsw::labBusDriver.hasReceiveBuffer(port), "receive");
            return py::memoryview::from_memory(WiseFsw::labBusDriver.makeReceiveBuffer(port, size),
                                               static_cast<py::ssize_t>(size));
        },
        py::arg("port"), py::arg("size"),
        "Makes LabBusDriver.busOut[port]'s receive buffer of size bytes and returns it, writable: each step "
        "pushes its bytes out on the port. Raises IndexError for a port past the driver's, and RuntimeError for "
        "a port that already has one or after the first step.");

    m.def(
        "transmit_buffer",
        [](FwIndexType port, FwSizeType size) {
            checkBufferPort(port, WiseFsw::labBusDriver.hasTransmitBuffer(port), "transmit");
            return py::memoryview::from_memory(static_cast<const void*>(WiseFsw::labBusDriver.makeTransmitBuffer(port, size)),
                                               static_cast<py::ssize_t>(size));
        },
        py::arg("port"), py::arg("size"),
        "Makes LabBusDriver.busIn[port]'s transmit buffer of size bytes and returns it, read-only: it holds the "
        "bytes the GNC last sent the port. Bytes of another size sent the port trip F´'s assert. Raises as "
        "receive_buffer does.");

    m.def(
        "step",
        [](U64 t_ns) {
            g_stepped = true;
            WiseFsw::simTime.set(t_ns);
            g_cooperative.pump();
            WiseFsw::labBusDriver.push();
            WiseFsw::simTime.tick();
            return WiseFsw::labBusDriver.takeWritten();
        },
        py::arg("t_ns"),
        "Sets the clock to t_ns (ns), runs the queued commands, pushes each receive buffer out on its "
        "LabBusDriver.busOut port in port order and ticks the rate groups once. A buffer the connected port does "
        "not deserialize exactly trips F´'s assert. Returns the transmit buffers the step wrote, bit n for "
        "LabBusDriver.busIn[n].");

    m.def(
        "pump", [](int rounds) { g_cooperative.pump(rounds); }, py::arg("rounds") = int{Sim::Cooperative::MAX_ROUNDS},
        "Runs the active components until no queue holds a message; raises RuntimeError naming a queue that "
        "still does after `rounds` rounds.");

    m.def(
        "telemetry",
        []() {
            py::list writes;
            for (const auto& write : WiseFsw::groundLink.takeWrites()) {
                writes.append(py::make_tuple(
                    write.id, write.ns,
                    py::bytes(reinterpret_cast<const char*>(write.value.data()), write.value.size())));
            }
            return writes;
        },
        "Every telemetry write since the last call, oldest first: (channel ID, F´ time tag in ns, serialized "
        "value).");

    m.def(
        "responses",
        []() {
            py::list responses;
            for (const auto& response : WiseFsw::groundLink.takeResponses()) {
                responses.append(py::make_tuple(response.context, response.response));
            }
            return responses;
        },
        "Every command response since the last call, oldest first: (context, Fw.CmdResponse value).");
}
