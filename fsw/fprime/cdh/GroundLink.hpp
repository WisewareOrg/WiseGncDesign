// The ground's side of the deployment: commands up, responses and every telemetry write down, packed into
// F´'s telemetry packets.
#ifndef CDH_GROUNDLINK_HPP
#define CDH_GROUNDLINK_HPP

#include <array>

#include "Fw/Tlm/TlmPacket.hpp"
#include "fsw/fprime/cdh/GroundLinkComponentAc.hpp"

namespace Cdh {

class GroundLink final : public GroundLinkComponentBase {
  public:
    //! The command responses held between drains; one more asserts.
    static constexpr FwSizeType RESPONSES = 256;

    //! One command's response: the ground's context and the Fw::CmdResponse value.
    struct Response {
        U32 context;
        I32 response;
    };

    explicit GroundLink(const char* compName);

    //! Sends one command packet to the dispatcher under the ground's context.
    void uplink(Fw::ComBuffer& packet, U32 context);

    //! Gives the link the lab's memory for `capacity` packets of FW_COM_BUFFER_MAX_SIZE bytes and for their sizes,
    //! before the first telemetry write. The last packet is the drain's: telemetry that would fill it asserts.
    void setDownlink(U8* packets, U32* sizes, FwSizeType capacity);

    //! Closes the packet being filled, so the downlink holds every write so far.
    void flush();

    //! The packets downlinked since the last drain, back to back, oldest first, and their bytes.
    const U8* downlink() const { return this->m_downlink; }
    FwSizeType downlinkSize() const { return this->m_bytes; }

    //! Each downlinked packet's size in bytes, in the order of `downlink`, and their count.
    const U32* packetSizes() const { return this->m_sizes; }
    FwSizeType packetCount() const { return this->m_packetCount; }

    //! Empties the downlink.
    void clearDownlink() {
        this->m_bytes = 0;
        this->m_packetCount = 0;
    }

    //! The responses since the last clear, oldest first, and their count.
    const Response* responses() const { return this->m_responses.data(); }
    FwSizeType responseCount() const { return this->m_responseCount; }

    //! Empties the responses.
    void clearResponses() { this->m_responseCount = 0; }

  private:
    void cmdResponseIn_handler(FwIndexType portNum, FwOpcodeType opCode, U32 cmdSeq,
                               const Fw::CmdResponse& response) override;
    void tlmIn_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) override;

    void resetPacket();

    Fw::TlmPacket m_packet;
    U8* m_downlink = nullptr;
    U32* m_sizes = nullptr;
    FwSizeType m_capacity = 0;
    FwSizeType m_bytes = 0;
    FwSizeType m_packetCount = 0;
    std::array<Response, RESPONSES> m_responses;
    FwSizeType m_responseCount = 0;
};

}  // namespace Cdh

#endif
