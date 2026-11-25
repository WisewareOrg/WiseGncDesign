// The ground's side of the deployment: commands up, responses and every telemetry write down, packed into
// F´'s telemetry packets.
#ifndef CDH_GROUNDLINK_HPP
#define CDH_GROUNDLINK_HPP

#include "Fw/Tlm/TlmPacket.hpp"
#include "fsw/fprime/cdh/GroundLinkComponentAc.hpp"

namespace Cdh {

class GroundLink final : public GroundLinkComponentBase {
  public:
    //! The command responses one step can give, between drains: each is a command's, and the dispatcher's queue
    //! holds the commands. One more asserts.
    static constexpr FwSizeType RESPONSES = 10;

    //! The telemetry packets one step can close, between drains, the drain's own included: a tick and each of
    //! RESPONSES commands writing every channel once. One more asserts.
    static constexpr FwSizeType PACKETS = 32;

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

    //! The packets downlinked since the last drain, back to back, oldest first, and their bytes.
    const U8* downlinked() const { return this->m_downlink; }
    FwSizeType downlinkedSize() const { return this->m_bytes; }

    //! Each downlinked packet's size in bytes, in the order of `downlinked`, and their count.
    const U32* packetSizes() const { return this->m_sizes; }
    FwSizeType packetCount() const { return this->m_packetCount; }

    //! Empties the downlink.
    void clearDownlink() {
        this->m_bytes = 0;
        this->m_packetCount = 0;
    }

    //! The responses since the last clear, oldest first, and their count.
    const Response* responses() const { return this->m_responses; }
    FwSizeType responseCount() const { return this->m_responseCount; }

    //! Empties the responses.
    void clearResponses() { this->m_responseCount = 0; }

  private:
    void cmdResponseIn_handler(FwIndexType portNum, FwOpcodeType opCode, U32 cmdSeq,
                               const Fw::CmdResponse& response) override;
    void tlmIn_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) override;

    void resetPacket();

    Fw::TlmPacket m_packet{};
    U8 m_downlink[PACKETS * FW_COM_BUFFER_MAX_SIZE]{};
    FwSizeType m_bytes = 0;
    U32 m_sizes[PACKETS]{};
    FwSizeType m_packetCount = 0;
    Response m_responses[RESPONSES]{};
    FwSizeType m_responseCount = 0;
};

}  // namespace Cdh

#endif
