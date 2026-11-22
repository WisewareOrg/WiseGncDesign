// Runs the deployment's active components on the caller's thread.
#ifndef SIM_COOPERATIVE_HPP
#define SIM_COOPERATIVE_HPP

#include <vector>

#include "Os/Queue.hpp"
#include "Os/Task.hpp"

namespace Sim {

//! Registers every task and queue the deployment creates, and runs the tasks one step at a time.
class Cooperative final : public Os::TaskRegistry, public Os::QueueRegistry {
  public:
    //! The rounds pump() runs by default before it gives up on a queue.
    static constexpr int MAX_ROUNDS = 1000;

    //! Adds a task, in start() order.
    void addTask(Os::Task* task) override;
    void removeTask(Os::Task* task) override;
    void registerQueue(Os::Queue* queue) override;

    //! Runs every task's routine, round by round, until no registered queue holds a message.
    //! Throws std::runtime_error naming a queue that still holds messages after `rounds` rounds.
    void pump(int rounds = MAX_ROUNDS);

  private:
    const Os::Queue* pending() const;

    std::vector<Os::Task*> m_tasks;
    std::vector<Os::Queue*> m_queues;
};

}  // namespace Sim

#endif
