// The ground's side of the deployment: commands up, responses and every telemetry write down, packed into
// F´'s telemetry packets.
#ifndef CDH_GROUNDLINK_HPP
#define CDH_GROUNDLINK_HPP

#include <vector>

#include "Fw/Tlm/TlmPacket.hpp"
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

    //! Closes the packet being filled, so the downlink holds every write so far.
    void flush();

    //! The packets downlinked since the last drain, back to back, oldest first.
    const std::vector<U8>& downlinked() const { return this->m_downlink; }

    //! Each downlinked packet's size in bytes, in the order of `downlinked`.
    const std::vector<U32>& packetSizes() const { return this->m_sizes; }

    //! Empties the downlink, keeping its storage.
    void clearDownlink() {
        this->m_downlink.clear();
        this->m_sizes.clear();
    }

    //! The responses since the last call, oldest first.
    std::vector<Response> takeResponses();

  private:
    void cmdResponseIn_handler(FwIndexType portNum, FwOpcodeType opCode, U32 cmdSeq,
                               const Fw::CmdResponse& response) override;
    void tlmIn_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) override;

    void resetPacket();

    Fw::TlmPacket m_packet{};
    std::vector<U8> m_downlink{};
    std::vector<U32> m_sizes{};
    std::vector<Response> m_responses{};
};

}  // namespace Cdh

#endif
