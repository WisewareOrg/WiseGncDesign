#include "fsw/fprime/cdh/GroundLink.hpp"

#include "Fw/Types/Assert.hpp"

namespace Cdh {

namespace {

//! The packets reserved for the downlink at construction: a performance hint, not a limit.
constexpr std::size_t PACKETS_RESERVE = 2048;

}  // namespace

GroundLink::GroundLink(const char* compName) : GroundLinkComponentBase(compName) {
    this->m_downlink.reserve(PACKETS_RESERVE * FW_COM_BUFFER_MAX_SIZE);
    this->m_sizes.reserve(PACKETS_RESERVE);
    this->resetPacket();
}

void GroundLink::uplink(Fw::ComBuffer& packet, U32 context) {
    this->cmdOut_out(0, packet, context);
}

void GroundLink::flush() {
    if (this->m_packet.getNumEntries() == 0) {
        return;
    }
    const Fw::ComBuffer& buffer = this->m_packet.getBuffer();
    this->m_downlink.insert(this->m_downlink.end(), buffer.getBuffAddr(), buffer.getBuffAddr() + buffer.getSize());
    this->m_sizes.push_back(static_cast<U32>(buffer.getSize()));
    this->resetPacket();
}

void GroundLink::resetPacket() {
    const Fw::SerializeStatus status = this->m_packet.resetPktSer();
    FW_ASSERT(status == Fw::FW_SERIALIZE_OK, static_cast<FwAssertArgType>(status));
}

std::vector<GroundLink::Response> GroundLink::takeResponses() {
    std::vector<Response> responses;
    responses.swap(this->m_responses);
    return responses;
}

void GroundLink::cmdResponseIn_handler(FwIndexType portNum, FwOpcodeType opCode, U32 cmdSeq,
                                       const Fw::CmdResponse& response) {
    // The dispatcher returns the uplink's context in place of its own sequence number.
    this->m_responses.push_back({cmdSeq, static_cast<I32>(response.e)});
}

void GroundLink::tlmIn_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) {
    Fw::SerializeStatus status = this->m_packet.addValue(id, timeTag, val);
    if (status == Fw::FW_SERIALIZE_NO_ROOM_LEFT) {
        this->flush();
        status = this->m_packet.addValue(id, timeTag, val);
    }
    FW_ASSERT(status == Fw::FW_SERIALIZE_OK, static_cast<FwAssertArgType>(status));
}

}  // namespace Cdh
