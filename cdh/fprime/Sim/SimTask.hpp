// An Os::Task with no thread: start() launches nothing, and Sim::Cooperative runs its routine.
#ifndef SIM_SIMTASK_HPP
#define SIM_SIMTASK_HPP

#include "Os/Task.hpp"

namespace Sim {

class SimTask final : public Os::TaskInterface {
  public:
    void onStart() override;
    Status join() override;
    void suspend(SuspensionType suspensionType) override;
    void resume() override;
    //! Asserts: a cooperative task never sleeps.
    Status _delay(const Fw::TimeInterval& interval) override;
    bool isCooperative() override;
    Os::TaskHandle* getHandle() override;
    Status start(const Arguments& arguments) override;
};

}  // namespace Sim

#endif
