#include "fsw/fprime/rio/LabBusDriver.hpp"

#include <cstring>

#include "Fw/Types/Assert.hpp"

namespace Bus {

LabBusDriver::LabBusDriver(const char* compName) : LabBusDriverComponentBase(compName) {}

void LabBusDriver::setReceiveBuffer(FwIndexType port, U8* memory, FwSizeType size) {
    FW_ASSERT(port >= 0 && port < PORTS, static_cast<FwAssertArgType>(port));
    this->m_receive[port] = {memory, size};
}

void LabBusDriver::setTransmitBuffer(FwIndexType port, U8* memory, FwSizeType size) {
    FW_ASSERT(port >= 0 && port < PORTS, static_cast<FwAssertArgType>(port));
    this->m_transmit[port] = {memory, size};
}

bool LabBusDriver::hasReceiveBuffer(FwIndexType port) const {
    FW_ASSERT(port >= 0 && port < PORTS, static_cast<FwAssertArgType>(port));
    return this->m_receive[port].memory != nullptr;
}

bool LabBusDriver::hasTransmitBuffer(FwIndexType port) const {
    FW_ASSERT(port >= 0 && port < PORTS, static_cast<FwAssertArgType>(port));
    return this->m_transmit[port].memory != nullptr;
}

void LabBusDriver::push() {
    for (FwIndexType port = 0; port < PORTS; port++) {
        const Buffer& receive = this->m_receive[port];
        if (receive.memory == nullptr) {
            continue;
        }
        Fw::ExternalSerializeBuffer wrapper(receive.memory, receive.size);
        const Fw::SerializeStatus status = wrapper.setBuffLen(receive.size);
        FW_ASSERT(status == Fw::FW_SERIALIZE_OK, static_cast<FwAssertArgType>(status));
        this->busOut_out(port, wrapper);
        FW_ASSERT(wrapper.getDeserializeSizeLeft() == 0, static_cast<FwAssertArgType>(port),
                  static_cast<FwAssertArgType>(wrapper.getDeserializeSizeLeft()));
    }
}

U32 LabBusDriver::takeWritten() {
    const U32 written = this->m_written;
    this->m_written = 0;
    return written;
}

void LabBusDriver::busIn_handler(FwIndexType portNum, Fw::LinearBufferBase& buffer) {
    const Buffer& transmit = this->m_transmit[portNum];
    FW_ASSERT(buffer.getSize() == transmit.size, static_cast<FwAssertArgType>(portNum),
              static_cast<FwAssertArgType>(buffer.getSize()), static_cast<FwAssertArgType>(transmit.size));
    std::memcpy(transmit.memory, buffer.getBuffAddr(), transmit.size);
    this->m_written |= 1U << portNum;
}

}  // namespace Bus
