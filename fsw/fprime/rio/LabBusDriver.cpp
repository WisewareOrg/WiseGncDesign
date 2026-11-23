#include "fsw/fprime/rio/LabBusDriver.hpp"

#include <cstring>

#include "Fw/Types/Assert.hpp"

namespace Bus {

LabBusDriver::LabBusDriver(const char* compName) : LabBusDriverComponentBase(compName) {}

U8* LabBusDriver::makeReceiveBuffer(FwIndexType port, FwSizeType size) {
    this->m_receive[port].assign(size, 0);
    return this->m_receive[port].data();
}

const U8* LabBusDriver::makeTransmitBuffer(FwIndexType port, FwSizeType size) {
    this->m_transmit[port].assign(size, 0);
    return this->m_transmit[port].data();
}

bool LabBusDriver::hasReceiveBuffer(FwIndexType port) const {
    return !this->m_receive[port].empty();
}

bool LabBusDriver::hasTransmitBuffer(FwIndexType port) const {
    return !this->m_transmit[port].empty();
}

void LabBusDriver::push() {
    for (FwIndexType port = 0; port < PORTS; port++) {
        std::vector<U8>& receive = this->m_receive[port];
        if (receive.empty()) {
            continue;
        }
        Fw::ExternalSerializeBuffer wrapper(receive.data(), receive.size());
        const Fw::SerializeStatus status = wrapper.setBuffLen(receive.size());
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
    std::vector<U8>& transmit = this->m_transmit[portNum];
    FW_ASSERT(buffer.getSize() == transmit.size(), static_cast<FwAssertArgType>(portNum),
              static_cast<FwAssertArgType>(buffer.getSize()), static_cast<FwAssertArgType>(transmit.size()));
    std::memcpy(transmit.data(), buffer.getBuffAddr(), transmit.size());
    this->m_written |= 1U << portNum;
}

}  // namespace Bus
