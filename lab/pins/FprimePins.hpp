// The pins' half that meets the flight software, in plain types. It is compiled as flight code is, with the exceptions
// the assert hook raises in Python; the pybind11 half includes no F´ class.
#ifndef LAB_PINS_FPRIMEPINS_HPP
#define LAB_PINS_FPRIMEPINS_HPP

#include <string>
#include <vector>

#include "Fw/FPrimeBasicTypes.h"

namespace Pins {

//! One command's response: the ground's context and the Fw::CmdResponse value.
struct Response {
    U32 context;
    I32 response;
};

//! The rounds pump() runs by default before it gives up on a queue.
int defaultRounds();

//! Raises an F´ assert in Python as a std::runtime_error carrying F´'s own text.
void registerAssertHook();

//! The pins of the same names, whose docstrings say what they do; a bad argument throws as it raises in Python.
void boot(const std::string& prm_path, const std::vector<FwPrmIdType>& parameter_ids);
void uplink(const U8* packet, FwSizeType size, U32 context);
U8* receiveBuffer(FwIndexType port, FwSizeType size);
const U8* transmitBuffer(FwIndexType port, FwSizeType size);
U32 step(U64 t_ns);
void pump(int rounds);

//! Closes the packet being filled, so the downlink holds every write so far.
void closePacket();

//! What the flight downlinked and answered since the last clear, oldest first: the packets back to back, each one's
//! size, and the responses.
const std::vector<U8>& downlink();
const std::vector<U32>& packetSizes();
void clearDownlink();
const std::vector<Response>& responses();
void clearResponses();

}  // namespace Pins

#endif
