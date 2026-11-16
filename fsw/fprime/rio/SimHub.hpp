// The bus driver's stand-in: bytes from the bus out on serial ports.
#ifndef BUS_SIMHUB_HPP
#define BUS_SIMHUB_HPP

#include "fsw/fprime/rio/SimHubComponentAc.hpp"

namespace Bus {

class SimHub final : public SimHubComponentBase {
  public:
    explicit SimHub(const char* compName);

    //! Sends size bytes out on busOut[port]; F´ asserts unless the connected port deserializes them
    //! all.
    void push(FwIndexType port, const U8* data, FwSizeType size);
};

}  // namespace Bus

#endif
