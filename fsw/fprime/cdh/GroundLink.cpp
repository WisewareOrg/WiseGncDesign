#include "fsw/fprime/cdh/GroundLink.hpp"

namespace Cdh {

namespace {

//! The bytes, and the packets, reserved for the downlink at construction.
constexpr std::size_t DOWNLINK_RESERVE = 1U << 20;
constexpr std::size_t PACKETS_RESERVE = 1U << 14;

}  // namespace

GroundLink::GroundLink(const char* compName) : GroundLinkComponentBase(compName) {
    this->m_downlink.reserve(DOWNLINK_RESERVE);
    this->m_sizes.reserve(PACKETS_RESERVE);
}

void GroundLink::uplink(Fw::ComBuffer& packet, U32 context) {
    this->cmdOut_out(0, packet, context);
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

void GroundLink::downlinkIn_handler(FwIndexType portNum, Fw::ComBuffer& data, U32 context) {
    const FwSizeType size = data.getSize();
    this->m_downlink.insert(this->m_downlink.end(), data.getBuffAddr(), data.getBuffAddr() + size);
    this->m_sizes.push_back(static_cast<U32>(size));
}

}  // namespace Cdh
