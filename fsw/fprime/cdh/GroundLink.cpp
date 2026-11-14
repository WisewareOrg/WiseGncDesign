#include "fsw/fprime/cdh/GroundLink.hpp"

namespace Sim {

namespace {

constexpr U64 NS_PER_S = 1000000000U;
constexpr U64 NS_PER_US = 1000U;

}  // namespace

GroundLink::GroundLink(const char* compName) : GroundLinkComponentBase(compName) {}

void GroundLink::uplink(Fw::ComBuffer& packet, U32 context) {
    this->cmdOut_out(0, packet, context);
}

std::vector<GroundLink::Write> GroundLink::takeWrites() {
    std::vector<Write> writes;
    writes.swap(this->m_writes);
    return writes;
}

std::vector<GroundLink::Response> GroundLink::takeResponses() {
    std::vector<Response> responses;
    responses.swap(this->m_responses);
    return responses;
}

void GroundLink::clear() {
    this->m_writes.clear();
    this->m_responses.clear();
}

void GroundLink::cmdResponseIn_handler(FwIndexType portNum, FwOpcodeType opCode, U32 cmdSeq,
                                       const Fw::CmdResponse& response) {
    // The dispatcher returns the uplink's context in place of its own sequence number.
    this->m_responses.push_back({cmdSeq, static_cast<I32>(response.e)});
}

void GroundLink::tlmIn_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) {
    const U64 ns = timeTag.getSeconds() * NS_PER_S + timeTag.getUSeconds() * NS_PER_US;
    const U8* data = val.getBuffAddr();
    this->m_writes.push_back({id, ns, std::vector<U8>(data, data + val.getSize())});
}

}  // namespace Sim
