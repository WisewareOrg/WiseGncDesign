#include "cdh/fprime/Sim/SimTask.hpp"

#include "Fw/Types/Assert.hpp"
#include "Os/Delegate.hpp"

namespace Sim {

void SimTask::onStart() {}

Os::TaskInterface::Status SimTask::join() {
    return Status::OP_OK;
}

void SimTask::suspend(SuspensionType suspensionType) {}

void SimTask::resume() {}

Os::TaskInterface::Status SimTask::_delay(const Fw::TimeInterval& interval) {
    FW_ASSERT(false);
    return Status::NOT_SUPPORTED;
}

bool SimTask::isCooperative() {
    return true;
}

Os::TaskHandle* SimTask::getHandle() {
    return nullptr;
}

Os::TaskInterface::Status SimTask::start(const Arguments& arguments) {
    return Status::OP_OK;
}

}  // namespace Sim

namespace Os {

//! Makes SimTask the deployment's Os::Task, chosen at link time.
TaskInterface* TaskInterface::getDelegate(TaskHandleStorage& aligned_new_memory) {
    return Os::Delegate::makeDelegate<TaskInterface, Sim::SimTask>(aligned_new_memory);
}

}  // namespace Os
