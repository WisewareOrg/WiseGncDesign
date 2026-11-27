// Runs the deployment's active components on the caller's thread.
#ifndef SIM_COOPERATIVE_HPP
#define SIM_COOPERATIVE_HPP

#include <array>

#include "Os/Queue.hpp"
#include "Os/Task.hpp"

namespace Sim {

//! Registers every task and queue the deployment creates, and runs the tasks one step at a time.
class Cooperative final : public Os::TaskRegistry, public Os::QueueRegistry {
  public:
    //! The rounds pump() runs by default before it gives up on a queue.
    static constexpr int MAX_ROUNDS = 1000;

    //! The tasks and the queues a deployment may have; one more asserts.
    static constexpr FwSizeType CAPACITY = 64;

    //! Adds a task, in start() order.
    void addTask(Os::Task* task) override;
    void removeTask(Os::Task* task) override;
    void registerQueue(Os::Queue* queue) override;

    //! Runs every task's routine, round by round, until no registered queue holds a message.
    //! Returns a queue that still holds messages after `rounds` rounds, else nullptr.
    const Os::Queue* pump(int rounds = MAX_ROUNDS);

  private:
    const Os::Queue* pending() const;

    std::array<Os::Task*, CAPACITY> m_tasks{};
    std::array<Os::Queue*, CAPACITY> m_queues{};
    FwSizeType m_taskCount = 0;
    FwSizeType m_queueCount = 0;
};

}  // namespace Sim

#endif
