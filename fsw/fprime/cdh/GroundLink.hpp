// The ground's side of the deployment: commands up, responses and telemetry packets down.
#ifndef CDH_GROUNDLINK_HPP
#define CDH_GROUNDLINK_HPP

#include <vector>

#include "fsw/fprime/cdh/GroundLinkComponentAc.hpp"

namespace Cdh {

class GroundLink final : public GroundLinkComponentBase {
  public:
    //! One command's response: the ground's context and the Fw::CmdResponse value.
    struct Response {
        U32 context;
        I32 response;
    };

    explicit GroundLink(const char* compName);

    //! Sends one command packet to the dispatcher under the ground's context.
    void uplink(Fw::ComBuffer& packet, U32 context);

    //! The downlinked bytes since the last drain: each packet as a big-endian U32 size, then the packet.
    const std::vector<U8>& downlinked() const { return this->m_downlink; }

    //! Empties the downlink, keeping its storage.
    void drained() { this->m_downlink.clear(); }

    //! The responses since the last call, oldest first.
    std::vector<Response> takeResponses();

  private:
    void cmdResponseIn_handler(FwIndexType portNum, FwOpcodeType opCode, U32 cmdSeq,
                               const Fw::CmdResponse& response) override;
    void downlinkIn_handler(FwIndexType portNum, Fw::ComBuffer& data, U32 context) override;

    std::vector<U8> m_downlink;
    std::vector<Response> m_responses;
};

}  // namespace Cdh

#endif
