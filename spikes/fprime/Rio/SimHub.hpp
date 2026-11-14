#ifndef RIO_SIMHUB_HPP
#define RIO_SIMHUB_HPP

#include <vector>

#include "Rio/SimHubComponentAc.hpp"

namespace Rio {

class SimHub final : public SimHubComponentBase {
  public:
    explicit SimHub(const char* compName);

    //! Sends bytes out on busOut[port]; the connected typed port deserializes them. Returns its status.
    Fw::SerializeStatus push(FwIndexType port, const U8* data, FwSizeType size);

    //! Every message received on busIn[port] since the last call, oldest first.
    std::vector<std::vector<U8>> drain(FwIndexType port);

  private:
    void busIn_handler(FwIndexType portNum, Fw::LinearBufferBase& buffer) override;

    std::vector<std::vector<U8>> m_received[NUM_BUSIN_INPUT_PORTS];
};

}  // namespace Rio

#endif
