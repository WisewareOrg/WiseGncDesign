// The RIO bus driver the lab uses: a fixed receive buffer per bus port, which the lab writes and the
// driver pushes out on its serial port each step, and a fixed transmit buffer per port, which holds
// the bytes of the bus struct last sent to its serial input for the lab to read.
#ifndef BUS_LABBUSDRIVER_HPP
#define BUS_LABBUSDRIVER_HPP

#include "fsw/fprime/rio/LabBusDriverComponentAc.hpp"

namespace Bus {

class LabBusDriver final : public LabBusDriverComponentBase {
  public:
    //! The serial ports each way, as LabBusDriver.fpp declares them.
    static constexpr FwIndexType PORTS = NUM_BUSOUT_OUTPUT_PORTS;
    static_assert(PORTS == FwIndexType{NUM_BUSIN_INPUT_PORTS}, "a port number names both directions");
    static_assert(PORTS <= 32, "takeWritten gives each port a bit of a U32");

    explicit LabBusDriver(const char* compName);

    //! Gives busOut[port] the lab's memory as its receive buffer, once, before the first push; the lab writes it.
    void setReceiveBuffer(FwIndexType port, U8* memory, FwSizeType size);

    //! Gives busIn[port] the lab's memory as its transmit buffer, once, before the first push; the lab reads it.
    void setTransmitBuffer(FwIndexType port, U8* memory, FwSizeType size);

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

    //! A port's buffer; no memory until the lab gives it.
    struct Buffer {
        U8* memory = nullptr;
        FwSizeType size = 0;
    };

    Buffer m_receive[PORTS];
    Buffer m_transmit[PORTS];
    U32 m_written = 0;
};

}  // namespace Bus

#endif
