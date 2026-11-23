// The RIO bus driver the lab uses: a fixed receive buffer per bus port, which the lab writes and the
// driver pushes out on its serial port each step, and a fixed transmit buffer per port, which holds
// the bytes of the bus struct last sent to its serial input for the lab to read.
#ifndef BUS_LABBUSDRIVER_HPP
#define BUS_LABBUSDRIVER_HPP

#include <array>
#include <vector>

#include "fsw/fprime/rio/LabBusDriverComponentAc.hpp"

namespace Bus {

class LabBusDriver final : public LabBusDriverComponentBase {
  public:
    //! The serial ports each way, as LabBusDriver.fpp declares them.
    static constexpr FwIndexType PORTS = NUM_BUSOUT_OUTPUT_PORTS;
    static_assert(NUM_BUSOUT_OUTPUT_PORTS == NUM_BUSIN_INPUT_PORTS, "a port number names both directions");

    explicit LabBusDriver(const char* compName);

    //! Makes busOut[port]'s receive buffer of size bytes, once, before the first push; returns its
    //! memory, which the lab writes.
    U8* makeReceiveBuffer(FwIndexType port, FwSizeType size);

    //! Makes busIn[port]'s transmit buffer of size bytes, once, before the first push; returns its
    //! memory, which the lab reads.
    const U8* makeTransmitBuffer(FwIndexType port, FwSizeType size);

    //! Whether port has a receive buffer, and a transmit buffer.
    bool hasReceiveBuffer(FwIndexType port) const;
    bool hasTransmitBuffer(FwIndexType port) const;

    //! Sends each receive buffer out on its busOut port, in port order; F´ asserts unless the
    //! connected port deserializes all its bytes.
    void push();

    //! The transmit buffers written since the last take, a bit per port; the next take starts afresh.
    U32 takeWritten();

  private:
    //! Copies the bus struct sent to busIn[portNum] into its transmit buffer, asserting its size.
    void busIn_handler(FwIndexType portNum, Fw::LinearBufferBase& buffer) override;

    std::array<std::vector<U8>, PORTS> m_receive;
    std::array<std::vector<U8>, PORTS> m_transmit;
    U32 m_written = 0;
};

}  // namespace Bus

#endif
