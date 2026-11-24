// The deployment's Python interface: a hand-written pybind11 module.
// One deployment per loaded copy: its component instances are the topology's globals.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "Fw/Types/Assert.hpp"
#include "config/FppConstantsAc.hpp"
#include "config/MemoryAllocation.hpp"
#include "fsw/fprime/cdh/BusConverterPins.hpp"
#include WISE_FSW_TOPOLOGY_HEADER

namespace py = pybind11;

namespace {

bool g_booted = false;

//! The memory of LabBusDriver's buffers, by port.
std::array<std::vector<U8>, Bus::LabBusDriver::PORTS> g_receive;
std::array<std::vector<U8>, Bus::LabBusDriver::PORTS> g_transmit;

//! The memory of GroundLink's downlink: its packets, and each one's size.
std::unique_ptr<U8[]> g_packets;
std::unique_ptr<U32[]> g_packetSizes;

//! Gives GroundLink the memory for `frames` ticks of telemetry, each channel written once a tick.
void makeDownlink(const std::vector<FwSizeType>& channel_sizes, FwSizeType frames) {
    FwSizeType bytes = 0;
    for (const FwSizeType size : channel_sizes) {
        bytes += frames * (sizeof(FwChanIdType) + Fw::Time::SERIALIZED_SIZE + size);
    }
    // A packet closes only when the next entry does not fit, so two neighbours carry more than one packet's payload.
    const FwSizeType payload = FW_COM_BUFFER_MAX_SIZE - sizeof(FwPacketDescriptorType);
    const FwSizeType packets = 2 * bytes / payload + 2;
    // Uninitialized, so a page no packet reaches costs nothing.
    g_packets.reset(new U8[packets * FW_COM_BUFFER_MAX_SIZE]);
    g_packetSizes.reset(new U32[packets]);
    WiseFsw::groundLink.setDownlink(g_packets.get(), g_packetSizes.get(), packets);
}

//! Refuses a buffer on a port LabBusDriver lacks, on one that has one, or after the first step; the
//! range is checked before the driver is asked about the port.
void checkBufferPort(FwIndexType port, bool (Bus::LabBusDriver::*has)(FwIndexType) const, const char* direction) {
    if (port < 0 || port >= Bus::LabBusDriver::PORTS) {
        throw py::index_error("port " + std::to_string(port) + " is past LabBusDriver's " +
                              std::to_string(Bus::LabBusDriver::PORTS) + " ports");
    }
    if ((WiseFsw::labBusDriver.*has)(port)) {
        throw std::runtime_error("port " + std::to_string(port) + " already has a " + direction + " buffer");
    }
    if (Fw::MemoryAllocation::InitAllocator::instance().closed()) {
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
        [](const std::string& prm_path, const std::vector<FwPrmIdType>& parameter_ids,
           const std::vector<FwSizeType>& channel_sizes, FwSizeType frames) {
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
            makeDownlink(channel_sizes, frames);
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
        py::arg("prm_path"), py::arg("parameter_ids"), py::arg("channel_sizes"), py::arg("frames"),
        "Sets the topology up and boots it at t = 0 s, every component idle: PrmDb loads prm_path, an absolute "
        "path whose directory is its sandbox, and the downlink holds frames ticks of telemetry undrained, each of "
        "the channels, whose values are channel_sizes bytes, written once a tick; telemetry past it trips F´'s "
        "assert. Raises ValueError for a relative path, one in the root directory or "
        "one longer than F´'s file names hold, and RuntimeError naming each of parameter_ids that is not valid once "
        "loaded. A copy boots once: a second boot raises RuntimeError.");

    m.def(
        "uplink",
        [](const py::bytes& packet, U32 context) {
            const auto* data = reinterpret_cast<const U8*>(PyBytes_AS_STRING(packet.ptr()));
            const FwSizeType size = py::len(packet);
            Fw::ComBuffer buffer;
            if (buffer.setBuff(data, size) != Fw::FW_SERIALIZE_OK) {
                throw py::value_error("a command packet of " + std::to_string(size) + " bytes exceeds the " +
                                      std::to_string(buffer.getCapacity()) + "-byte buffer");
            }
            WiseFsw::groundLink.uplink(buffer, context);
        },
        py::arg("packet"), py::arg("context"),
        "Queues one F´ command packet at the dispatcher under the ground's context; it runs at the next step.");

    m.def(
        "receive_buffer",
        [](FwIndexType port, FwSizeType size) {
            checkBufferPort(port, &Bus::LabBusDriver::hasReceiveBuffer, "receive");
            std::vector<U8>& buffer = g_receive[port];
            buffer.assign(size, 0);
            WiseFsw::labBusDriver.setReceiveBuffer(port, buffer.data(), size);
            return py::memoryview::from_memory(buffer.data(), static_cast<py::ssize_t>(size));
        },
        py::arg("port"), py::arg("size"),
        "Makes LabBusDriver.busOut[port]'s receive buffer of size bytes and returns it, writable: each step "
        "pushes its bytes out on the port. Raises IndexError for a port past the driver's, and RuntimeError for "
        "a port that already has one or after the first step.");

    m.def(
        "transmit_buffer",
        [](FwIndexType port, FwSizeType size) {
            checkBufferPort(port, &Bus::LabBusDriver::hasTransmitBuffer, "transmit");
            std::vector<U8>& buffer = g_transmit[port];
            buffer.assign(size, 0);
            WiseFsw::labBusDriver.setTransmitBuffer(port, buffer.data(), size);
            return py::memoryview::from_memory(static_cast<const void*>(buffer.data()),
                                               static_cast<py::ssize_t>(size));
        },
        py::arg("port"), py::arg("size"),
        "Makes LabBusDriver.busIn[port]'s transmit buffer of size bytes and returns it, read-only: it holds the "
        "bytes the GNC last sent the port. Bytes of another size sent the port trip F´'s assert. Raises as "
        "receive_buffer does.");

    m.def(
        "step", &WiseFsw::step, py::arg("t_ns"),
        "Sets the clock to t_ns (ns), runs the queued commands, pushes each receive buffer out on its "
        "LabBusDriver.busOut port in port order and ticks the rate groups once. A buffer the connected port does "
        "not deserialize exactly trips F´'s assert. Returns the transmit buffers the step wrote, bit n for "
        "LabBusDriver.busIn[n].");

    m.def(
        "pump",
        [](int rounds) {
            const Os::Queue* stuck = WiseFsw::cooperative.pump(rounds);
            if (stuck != nullptr) {
                throw std::runtime_error("queue " + std::string(stuck->getName().toChar()) +
                                         " did not drain: messages left " +
                                         std::to_string(stuck->getMessagesAvailable()) + ", rounds " +
                                         std::to_string(rounds));
            }
        },
        py::arg("rounds") = int{Sim::Cooperative::MAX_ROUNDS},
        "Runs the active components until no queue holds a message; raises RuntimeError naming a queue that "
        "still does after `rounds` rounds.");

    m.def(
        "telemetry",
        []() {
            WiseFsw::groundLink.flush();
            py::tuple drained = py::make_tuple(
                py::bytes(reinterpret_cast<const char*>(WiseFsw::groundLink.downlink()),
                          WiseFsw::groundLink.downlinkSize()),
                py::bytes(reinterpret_cast<const char*>(WiseFsw::groundLink.packetSizes()),
                          WiseFsw::groundLink.packets() * sizeof(U32)));
            WiseFsw::groundLink.clearDownlink();
            return drained;
        },
        "Every telemetry packet downlinked since the last call, oldest first: (the packets back to back, each "
        "packet's size as native U32).");

    m.def(
        "responses",
        []() {
            py::list responses;
            for (FwSizeType i = 0; i < WiseFsw::groundLink.responseCount(); i++) {
                const Cdh::GroundLink::Response& response = WiseFsw::groundLink.responses()[i];
                responses.append(py::make_tuple(response.context, response.response));
            }
            WiseFsw::groundLink.clearResponses();
            return responses;
        },
        "Every command response since the last call, oldest first: (context, Fw.CmdResponse value).");
}
