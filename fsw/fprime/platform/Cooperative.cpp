#include "fsw/fprime/platform/Cooperative.hpp"

#include <algorithm>
#include <stdexcept>
#include <string>

namespace Sim {

void Cooperative::addTask(Os::Task* task) {
    this->m_tasks.push_back(task);
}

void Cooperative::removeTask(Os::Task* task) {
    this->m_tasks.erase(std::remove(this->m_tasks.begin(), this->m_tasks.end(), task), this->m_tasks.end());
}

void Cooperative::registerQueue(Os::Queue* queue) {
    this->m_queues.push_back(queue);
}

const Os::Queue* Cooperative::pending() const {
    const auto queue = std::find_if(this->m_queues.begin(), this->m_queues.end(),
                                    [](const Os::Queue* q) { return q->getMessagesAvailable() > 0; });
    return queue == this->m_queues.end() ? nullptr : *queue;
}

void Cooperative::pump(int rounds) {
    for (int round = 0; round < rounds; round++) {
        if (this->pending() == nullptr) {
            return;
        }
        for (Os::Task* task : this->m_tasks) {
            task->invokeRoutine();
        }
    }
    const Os::Queue* stuck = this->pending();
    if (stuck != nullptr) {
        throw std::runtime_error("queue " + std::string(stuck->getName().toChar()) + " did not drain: messages left " +
                                 std::to_string(stuck->getMessagesAvailable()) + ", rounds " +
                                 std::to_string(rounds));
    }
}

}  // namespace Sim
