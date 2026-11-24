#include "fsw/fprime/cdh/GroundLink.hpp"

#include <cstring>

#include "Fw/Types/Assert.hpp"

namespace Cdh {

GroundLink::GroundLink(const char* compName) : GroundLinkComponentBase(compName) {
    this->resetPacket();
}

void GroundLink::uplink(Fw::ComBuffer& packet, U32 context) {
    this->cmdOut_out(0, packet, context);
}

void GroundLink::setDownlink(U8* packets, U32* sizes, FwSizeType capacity) {
    this->m_downlink = packets;
    this->m_sizes = sizes;
    this->m_capacity = capacity;
}

void GroundLink::flush() {
    if (this->m_packet.getNumEntries() == 0) {
        return;
    }
    FW_ASSERT(this->m_packets < this->m_capacity, static_cast<FwAssertArgType>(this->m_packets));
    const Fw::ComBuffer& buffer = this->m_packet.getBuffer();
    (void)std::memcpy(&this->m_downlink[this->m_bytes], buffer.getBuffAddr(), buffer.getSize());
    this->m_bytes += buffer.getSize();
    this->m_sizes[this->m_packets++] = static_cast<U32>(buffer.getSize());
    this->resetPacket();
}

void GroundLink::resetPacket() {
    const Fw::SerializeStatus status = this->m_packet.resetPktSer();
    FW_ASSERT(status == Fw::FW_SERIALIZE_OK, static_cast<FwAssertArgType>(status));
}

void GroundLink::cmdResponseIn_handler(FwIndexType portNum, FwOpcodeType opCode, U32 cmdSeq,
                                       const Fw::CmdResponse& response) {
    FW_ASSERT(this->m_responseCount < RESPONSES, static_cast<FwAssertArgType>(cmdSeq));
    // The dispatcher returns the uplink's context in place of its own sequence number.
    this->m_responses[this->m_responseCount++] = {cmdSeq, static_cast<I32>(response.e)};
}

void GroundLink::tlmIn_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) {
    Fw::SerializeStatus status = this->m_packet.addValue(id, timeTag, val);
    if (status == Fw::FW_SERIALIZE_NO_ROOM_LEFT) {
        FW_ASSERT(this->m_packets + 1 < this->m_capacity, static_cast<FwAssertArgType>(this->m_packets));
        this->flush();
        status = this->m_packet.addValue(id, timeTag, val);
    }
    FW_ASSERT(status == Fw::FW_SERIALIZE_OK, static_cast<FwAssertArgType>(status));
}

}  // namespace Cdh
