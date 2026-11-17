#include "fsw/fprime/rio/LabBusDriver.hpp"

#include "Fw/Types/Assert.hpp"

namespace Bus {

LabBusDriver::LabBusDriver(const char* compName) : LabBusDriverComponentBase(compName) {}

void LabBusDriver::push(FwIndexType port, const U8* data, FwSizeType size) {
    Fw::ExternalSerializeBuffer wrapper(const_cast<U8*>(data), size);
    const Fw::SerializeStatus status = wrapper.setBuffLen(size);
    FW_ASSERT(status == Fw::FW_SERIALIZE_OK, static_cast<FwAssertArgType>(status));
    this->busOut_out(port, wrapper);
    FW_ASSERT(wrapper.getDeserializeSizeLeft() == 0, static_cast<FwAssertArgType>(port),
              static_cast<FwAssertArgType>(wrapper.getDeserializeSizeLeft()));
}

}  // namespace Bus
