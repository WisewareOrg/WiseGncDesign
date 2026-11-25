#include "lab/pins/FprimePins.hpp"

#include <stdexcept>

#include "Fw/Types/Assert.hpp"
#include "Os/Os.hpp"
#include "config/FppConstantsAc.hpp"
#define CDH_BUSCONVERTERPINS_FLIGHT
#include "BusConverterPins.hpp"
#include "fsw/fprime/platform/Cooperative.hpp"
#include WISE_FSW_TOPOLOGY_HEADER

namespace Pins {

namespace {

Sim::Cooperative g_cooperative;
bool g_booted = false;
bool g_stepped = false;

//! What the flight downlinked and answered since Python last took it, copied from GroundLink as it fills.
std::vector<U8> g_downlink;
std::vector<U32> g_packetSizes;
std::vector<Response> g_responses;

//! The packets reserved at boot: a performance hint, not a limit.
constexpr std::size_t PACKETS_RESERVE = 4096;

//! Copies GroundLink's closed packets and responses out and empties it.
void drain() {
    Cdh::GroundLink& link = WiseFsw::groundLink;
    g_downlink.insert(g_downlink.end(), link.downlinked(), link.downlinked() + link.downlinkedSize());
    g_packetSizes.insert(g_packetSizes.end(), link.packetSizes(), link.packetSizes() + link.packetCount());
    link.clearDownlink();
    for (FwSizeType i = 0; i < link.responseCount(); i++) {
        g_responses.push_back({link.responses()[i].context, link.responses()[i].response});
    }
    link.clearResponses();
}

//! Refuses a buffer on a port LabBusDriver lacks, on one that has one, or after the first step; the
//! range is checked before the driver is asked about the port.
void checkBufferPort(FwIndexType port, bool (Bus::LabBusDriver::*has)(FwIndexType) const, const char* direction) {
    if (port < 0 || port >= Bus::LabBusDriver::PORTS) {
        throw std::out_of_range("port " + std::to_string(port) + " is past LabBusDriver's " +
                              std::to_string(Bus::LabBusDriver::PORTS) + " ports");
    }
    if ((WiseFsw::labBusDriver.*has)(port)) {
        throw std::runtime_error("port " + std::to_string(port) + " already has a " + direction + " buffer");
    }
    if (g_stepped) {
        throw std::runtime_error(std::string("a ") + direction + " buffer is made at boot, not after the first step");
    }
}

//! Runs the active components for `rounds` rounds, and raises a queue that did not drain, naming it.
void pumpOrRaise(int rounds = Sim::Cooperative::MAX_ROUNDS) {
    const Os::Queue* stuck = g_cooperative.pump(rounds);
    if (stuck != nullptr) {
        throw std::runtime_error("queue " + std::string(stuck->getName().toChar()) + " did not drain: messages left " +
                                 std::to_string(stuck->getMessagesAvailable()) + ", rounds " +
                                 std::to_string(rounds));
    }
}

//! Raises an F´ assert in Python as a std::runtime_error carrying F´'s own text.
class RaisingAssertHook final : public Fw::AssertHook {
  public:
    void printAssert(const CHAR* msg) override { this->m_text = msg; }
    void doAssert() override { throw std::runtime_error(this->m_text); }

  private:
    std::string m_text{};
};

RaisingAssertHook g_assertHook;

}  // namespace

int defaultRounds() {
    return Sim::Cooperative::MAX_ROUNDS;
}

void registerAssertHook() {
    g_assertHook.registerHook();
}

void boot(const std::string& prm_path, const std::vector<U32>& parameter_ids) {
    if (g_booted) {
        throw std::runtime_error("already booted: power-cycle by loading a fresh copy");
    }
    const std::string directory = prm_path.substr(0, prm_path.rfind('/'));
    if (prm_path.empty() || prm_path.front() != '/' || directory.empty()) {
        throw std::invalid_argument("the parameter file " + prm_path +
                                    " is not an absolute path in a directory below the root");
    }
    // F´ resolves every file path in a buffer of FileNameStringSize bytes, its terminator included.
    const std::size_t longest = FileNameStringSize - 1;
    if (prm_path.size() > longest) {
        throw std::invalid_argument("the parameter file " + prm_path + " is " + std::to_string(prm_path.size()) +
                                    " bytes, past F´'s limit of " + std::to_string(longest) +
                                    " (FileNameStringSize less its terminator)");
    }
    g_booted = true;
    g_downlink.reserve(PACKETS_RESERVE * FW_COM_BUFFER_MAX_SIZE);
    g_packetSizes.reserve(PACKETS_RESERVE);
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
    drain();
}

void uplink(const U8* packet, U64 size, U32 context) {
    Fw::ComBuffer buffer;
    if (buffer.setBuff(packet, size) != Fw::FW_SERIALIZE_OK) {
        throw std::invalid_argument("a command packet of " + std::to_string(size) + " bytes exceeds the " +
                                    std::to_string(buffer.getCapacity()) + "-byte buffer");
    }
    WiseFsw::groundLink.uplink(buffer, context);
}

U8* receiveBuffer(I16 port, U64 size) {
    checkBufferPort(port, &Bus::LabBusDriver::hasReceiveBuffer, "receive");
    return WiseFsw::labBusDriver.makeReceiveBuffer(port, size);
}

const U8* transmitBuffer(I16 port, U64 size) {
    checkBufferPort(port, &Bus::LabBusDriver::hasTransmitBuffer, "transmit");
    return WiseFsw::labBusDriver.makeTransmitBuffer(port, size);
}

U32 step(U64 t_ns) {
    g_stepped = true;
    WiseFsw::simTime.set(t_ns);
    pumpOrRaise();
    WiseFsw::labBusDriver.push();
    WiseFsw::simTime.tick();
    drain();
    return WiseFsw::labBusDriver.takeWritten();
}

void pump(int rounds) {
    pumpOrRaise(rounds);
    drain();
}

const std::vector<U8>& downlink() {
    drain();
    WiseFsw::groundLink.flush();
    drain();
    return g_downlink;
}

const std::vector<U32>& packetSizes() {
    return g_packetSizes;
}

void clearDownlink() {
    g_downlink.clear();
    g_packetSizes.clear();
}

const std::vector<Response>& responses() {
    drain();
    return g_responses;
}

void clearResponses() {
    g_responses.clear();
}

}  // namespace Pins
