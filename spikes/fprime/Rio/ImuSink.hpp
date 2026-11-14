#ifndef RIO_IMUSINK_HPP
#define RIO_IMUSINK_HPP

#include "Rio/ImuSinkComponentAc.hpp"

namespace Rio {

class ImuSink final : public ImuSinkComponentBase {
  public:
    explicit ImuSink(const char* compName);

    ImuSensorMsg last;
    U32 count = 0;

  private:
    void imuIn_handler(FwIndexType portNum, const ImuSensorMsg& msg) override;
};

}  // namespace Rio

#endif
