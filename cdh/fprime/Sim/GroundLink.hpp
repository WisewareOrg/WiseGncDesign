// The ground's side of the deployment: commands up, responses and every telemetry write down.
#ifndef SIM_GROUNDLINK_HPP
#define SIM_GROUNDLINK_HPP

#include <utility>
#include <vector>

#include "cdh/fprime/Sim/GroundLinkComponentAc.hpp"

namespace Sim {

class GroundLink final : public GroundLinkComponentBase {
  public:
    //! One telemetry write: the channel ID, its F´ time tag in ns and its serialized value.
    struct Write {
        FwChanIdType id;
        U64 ns;
        std::vector<U8> value;
    };
    //! One command's response: the ground's context and the Fw::CmdResponse value.
    using Response = std::pair<U32, I32>;

    explicit GroundLink(const char* compName);

    //! Sends one command packet to the dispatcher under the ground's context.
    void uplink(Fw::ComBuffer& packet, U32 context);

    //! The telemetry writes since the last call, oldest first.
    std::vector<Write> takeWrites();

    //! The responses since the last call, oldest first.
    std::vector<Response> takeResponses();

    //! Forgets every write and response.
    void clear();

  private:
    void cmdResponseIn_handler(FwIndexType portNum, FwOpcodeType opCode, U32 cmdSeq,
                               const Fw::CmdResponse& response) override;
    void tlmIn_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) override;

    std::vector<Write> m_writes;
    std::vector<Response> m_responses;
};

}  // namespace Sim

#endif
