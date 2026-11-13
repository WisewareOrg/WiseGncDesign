#include "cdh/fprime/Sim/TlmCapture.hpp"

namespace Sim {

TlmCapture::TlmCapture(const char* compName) : TlmCaptureComponentBase(compName) {}

const std::map<FwChanIdType, std::vector<U8>>& TlmCapture::latest() const {
    return this->m_latest;
}

void TlmCapture::clear() {
    this->m_latest.clear();
}

void TlmCapture::TlmRecv_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) {
    const U8* data = val.getBuffAddr();
    this->m_latest[id] = std::vector<U8>(data, data + val.getSize());
}

}  // namespace Sim
