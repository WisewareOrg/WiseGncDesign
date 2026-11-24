#include "fsw/fprime/platform/Cooperative.hpp"

#include <algorithm>

#include "Fw/Types/Assert.hpp"

namespace Sim {

void Cooperative::addTask(Os::Task* task) {
    FW_ASSERT(this->m_taskCount < CAPACITY);
    this->m_tasks[this->m_taskCount++] = task;
}

void Cooperative::removeTask(Os::Task* task) {
    const auto end = this->m_tasks.begin() + this->m_taskCount;
    this->m_taskCount = static_cast<FwSizeType>(std::remove(this->m_tasks.begin(), end, task) - this->m_tasks.begin());
}

void Cooperative::registerQueue(Os::Queue* queue) {
    FW_ASSERT(this->m_queueCount < CAPACITY);
    this->m_queues[this->m_queueCount++] = queue;
}

const Os::Queue* Cooperative::pending() const {
    const auto end = this->m_queues.begin() + this->m_queueCount;
    const auto queue =
        std::find_if(this->m_queues.begin(), end, [](const Os::Queue* q) { return q->getMessagesAvailable() > 0; });
    return queue == end ? nullptr : *queue;
}

const Os::Queue* Cooperative::pump(int rounds) {
    for (int round = 0; round < rounds; round++) {
        if (this->pending() == nullptr) {
            return nullptr;
        }
        for (FwSizeType task = 0; task < this->m_taskCount; task++) {
            this->m_tasks[task]->invokeRoutine();
        }
    }
    return this->pending();
}

}  // namespace Sim
