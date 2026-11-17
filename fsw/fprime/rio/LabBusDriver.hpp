// The RIO bus driver the lab uses: raw bus bytes from the bus emulator out on serial ports.
#ifndef BUS_LABBUSDRIVER_HPP
#define BUS_LABBUSDRIVER_HPP

#include "fsw/fprime/rio/LabBusDriverComponentAc.hpp"

namespace Bus {

class LabBusDriver final : public LabBusDriverComponentBase {
  public:
    explicit LabBusDriver(const char* compName);

    //! Sends size bytes out on busOut[port]; F´ asserts unless the connected port deserializes them
    //! all.
    void push(FwIndexType port, const U8* data, FwSizeType size);
};

}  // namespace Bus

#endif
