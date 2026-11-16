#include "fsw/fprime/rio/SimHub.hpp"

#include "Fw/Types/Assert.hpp"

namespace Bus {

SimHub::SimHub(const char* compName) : SimHubComponentBase(compName) {}

void SimHub::push(FwIndexType port, const U8* data, FwSizeType size) {
    Fw::ExternalSerializeBuffer wrapper(const_cast<U8*>(data), size);
    const Fw::SerializeStatus status = wrapper.setBuffLen(size);
    FW_ASSERT(status == Fw::FW_SERIALIZE_OK, static_cast<FwAssertArgType>(status));
    this->busOut_out(port, wrapper);
    FW_ASSERT(wrapper.getDeserializeSizeLeft() == 0, static_cast<FwAssertArgType>(port),
              static_cast<FwAssertArgType>(wrapper.getDeserializeSizeLeft()));
}

}  // namespace Bus
