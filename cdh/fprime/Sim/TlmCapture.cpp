#include "cdh/fprime/Sim/TlmCapture.hpp"

namespace Sim {

TlmCapture::TlmCapture(const char* compName) : TlmCaptureComponentBase(compName) {}

const std::map<FwChanIdType, TlmCapture::Sample>& TlmCapture::latest() const {
    return this->m_latest;
}

void TlmCapture::clear() {
    this->m_latest.clear();
}

void TlmCapture::TlmRecv_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) {
    const U8* data = val.getBuffAddr();
    const F64 time = static_cast<F64>(timeTag.getSeconds()) + static_cast<F64>(timeTag.getUSeconds()) * 1e-6;
    this->m_latest[id] = Sample{time, std::vector<U8>(data, data + val.getSize())};
}

}  // namespace Sim
