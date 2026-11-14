#include "Rio/SimHub.hpp"

#include <utility>

namespace Rio {

SimHub::SimHub(const char* compName) : SimHubComponentBase(compName) {}

Fw::SerializeStatus SimHub::push(FwIndexType port, const U8* data, FwSizeType size) {
    Fw::ExternalSerializeBuffer wrapper(const_cast<U8*>(data), size);
    const Fw::SerializeStatus status = wrapper.setBuffLen(size);
    if (status != Fw::FW_SERIALIZE_OK) {
        return status;
    }
    return this->busOut_out(port, wrapper);
}

std::vector<std::vector<U8>> SimHub::drain(FwIndexType port) {
    return std::exchange(this->m_received[port], {});
}

void SimHub::busIn_handler(FwIndexType portNum, Fw::LinearBufferBase& buffer) {
    const U8* data = buffer.getBuffAddr();
    this->m_received[portNum].emplace_back(data, data + buffer.getSize());
}

}  // namespace Rio
