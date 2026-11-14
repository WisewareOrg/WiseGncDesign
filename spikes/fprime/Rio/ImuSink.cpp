#include "Rio/ImuSink.hpp"

namespace Rio {

ImuSink::ImuSink(const char* compName) : ImuSinkComponentBase(compName) {}

void ImuSink::imuIn_handler(FwIndexType portNum, const ImuSensorMsg& msg) {
    this->last = msg;
    this->count++;
    if (this->isConnected_imuEcho_OutputPort(0)) {
        this->imuEcho_out(0, msg);
    }
}

}  // namespace Rio
