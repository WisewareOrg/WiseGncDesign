// The RIO bus driver the lab uses: raw bus bytes from the bus emulator out on serial ports, and the
// bytes of the bus structs sent to its serial inputs held for the lab to drain.
#ifndef BUS_LABBUSDRIVER_HPP
#define BUS_LABBUSDRIVER_HPP

#include <utility>
#include <vector>

#include "fsw/fprime/rio/LabBusDriverComponentAc.hpp"

namespace Bus {

class LabBusDriver final : public LabBusDriverComponentBase {
  public:
    explicit LabBusDriver(const char* compName);

    //! Sends size bytes out on busOut[port]; F´ asserts unless the connected port deserializes them
    //! all.
    void push(FwIndexType port, const U8* data, FwSizeType size);

    //! The (port, bytes) of each bus struct sent to busIn since the last take, in arrival order;
    //! the next take starts afresh.
    std::vector<std::pair<FwIndexType, std::vector<U8>>> take();

  private:
    //! Holds the bytes of a bus struct sent to busIn[portNum].
    void busIn_handler(FwIndexType portNum, Fw::LinearBufferBase& buffer) override;

    std::vector<std::pair<FwIndexType, std::vector<U8>>> m_taken;
};

}  // namespace Bus

#endif
