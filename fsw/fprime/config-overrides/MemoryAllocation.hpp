// F´'s memory for what it sizes at initialization: one static arena, closed when initialization ends.
#ifndef CONFIG_MEMORY_ALLOCATION_HPP
#define CONFIG_MEMORY_ALLOCATION_HPP

#include <cstddef>

#include <Fw/Types/Assert.hpp>
#include <Fw/Types/MemAllocator.hpp>

namespace Fw {
namespace MemoryAllocation {

//! F´'s one allocator: memory from its arena until `close`, after which an allocation asserts. Never freed.
class InitAllocator final : public Fw::MemAllocator {
  public:
    using Fw::MemAllocator::allocate;

    //! The allocator F´ registers for every use.
    static InitAllocator& instance() {
        return static_cast<InitAllocator&>(
            Fw::MemAllocatorRegistry::getInstance().getAllocator(MemoryAllocatorType::SYSTEM));
    }

    void* allocate(const FwEnumStoreType identifier,
                   FwSizeType& size,
                   bool& recoverable,
                   FwSizeType alignment) override {
        FW_ASSERT(alignment <= alignof(std::max_align_t), static_cast<FwAssertArgType>(alignment));
        FW_ASSERT(!this->m_closed, static_cast<FwAssertArgType>(identifier), static_cast<FwAssertArgType>(size));
        const FwSizeType start = (this->m_used + alignment - 1) / alignment * alignment;
        FW_ASSERT(start <= ARENA && size <= ARENA - start, static_cast<FwAssertArgType>(identifier),
                  static_cast<FwAssertArgType>(size), static_cast<FwAssertArgType>(this->m_used));
        this->m_used = start + size;
        recoverable = false;
        return &this->m_arena[start];
    }

    void deallocate(const FwEnumStoreType identifier, void* ptr) override {}

    //! Ends initialization.
    void close() { this->m_closed = true; }

    //! Whether initialization has ended.
    bool closed() const { return this->m_closed; }

  private:
    //! The arena's size in bytes.
    static constexpr FwSizeType ARENA = 256 * 1024;

    alignas(std::max_align_t) U8 m_arena[ARENA];
    FwSizeType m_used = 0;
    bool m_closed = false;
};

using DefaultMemoryAllocatorType = InitAllocator;

}  // namespace MemoryAllocation
}  // namespace Fw

#endif
