// The deployment's Python interface: a hand-written pybind11 module.
// One deployment per loaded copy: its component instances are the topology's globals.
#include <pybind11/eigen.h>
#include <pybind11/pybind11.h>

#include <stdexcept>
#include <string>

#include "Fw/Types/Assert.hpp"
#include "Os/Os.hpp"
#include "fsw/fprime/platform/Cooperative.hpp"
#include WISE_FSW_TOPOLOGY_HEADER

namespace py = pybind11;

namespace {

WiseFsw::TopologyState g_state;
Sim::Cooperative g_cooperative;
bool g_booted = false;

//! Raises an F´ assert in Python as a std::runtime_error carrying F´'s own text.
class RaisingAssertHook final : public Fw::AssertHook {
  public:
    void printAssert(const CHAR* msg) override { this->m_text = msg; }
    void doAssert() override { throw std::runtime_error(this->m_text); }

  private:
    std::string m_text;
};

RaisingAssertHook g_assertHook;

Gnc::Vector3 vector3(const Eigen::Vector3d& v) {
    return Gnc::Vector3({v.x(), v.y(), v.z()});
}

Gnc::Matrix3 matrix3(const Eigen::Matrix3d& m) {
    return Gnc::Matrix3({Gnc::Vector3({m(0, 0), m(0, 1), m(0, 2)}), Gnc::Vector3({m(1, 0), m(1, 1), m(1, 2)}),
                         Gnc::Vector3({m(2, 0), m(2, 1), m(2, 2)})});
}

}  // namespace

PYBIND11_MODULE(_wise_fsw, m) {
    m.doc() = "The WiseFsw F´ deployment, run inside the simulation's process; set up by boot, once per copy.";

    g_assertHook.registerHook();

    m.def(
        "boot",
        [](double mu, const Eigen::Matrix3d& dcm_PB, const std::string& prm_path) {
            if (g_booted) {
                throw std::runtime_error("already booted: power-cycle by loading a fresh copy");
            }
            g_booted = true;
            Os::init();
            Os::Task::registerTaskRegistry(&g_cooperative);
            Os::Queue::setRegistry(&g_cooperative);
            WiseFsw::setupTopology(g_state);
            WiseFsw::simBridge.configureNav(mu, matrix3(dcm_PB));
        },
        py::kw_only(), py::arg("mu"), py::arg("dcm_PB"), py::arg("prm_path") = std::string(),
        "Sets the topology up and boots it at t = 0 s, the dead reckoner idle with mu (m^3/s^2) and the IMU's "
        "mounting [PB]; prm_path is unused. A copy boots once: a second boot raises RuntimeError.");

    m.def(
        "uplink",
        [](const py::bytes& packet, U32 context) {
            const std::string data = packet;
            Fw::ComBuffer buffer;
            if (buffer.setBuff(reinterpret_cast<const U8*>(data.data()), static_cast<FwSizeType>(data.size())) !=
                Fw::FW_SERIALIZE_OK) {
                throw py::value_error("a command packet of " + std::to_string(data.size()) + " bytes exceeds the " +
                                      std::to_string(buffer.getCapacity()) + "-byte buffer");
            }
            WiseFsw::groundLink.uplink(buffer, context);
        },
        py::arg("packet"), py::arg("context"),
        "Queues one F´ command packet at the dispatcher under the ground's context; it runs at the next step.");

    m.def(
        "step",
        [](U64 t_ns, const Eigen::Vector3d& angVelPlatform, const Eigen::Vector3d& accelPlatform) {
            WiseFsw::simTime.set(t_ns);
            g_cooperative.pump();
            WiseFsw::simBridge.sendImu(vector3(angVelPlatform), vector3(accelPlatform));
            WiseFsw::simTime.tick();
        },
        py::arg("t_ns"), py::arg("angVelPlatform"), py::arg("accelPlatform"),
        "Sets the clock to t_ns (ns), runs the queued commands, sends the IMU reading and ticks the rate groups "
        "once.");

    m.def(
        "pump", [](int rounds) { g_cooperative.pump(rounds); }, py::arg("rounds") = int{Sim::Cooperative::MAX_ROUNDS},
        "Runs the active components until no queue holds a message; raises RuntimeError naming a queue that "
        "still does after `rounds` rounds.");

    m.def(
        "telemetry",
        []() {
            py::list writes;
            for (const auto& write : WiseFsw::groundLink.takeWrites()) {
                writes.append(py::make_tuple(
                    write.id, write.ns,
                    py::bytes(reinterpret_cast<const char*>(write.value.data()), write.value.size())));
            }
            return writes;
        },
        "Every telemetry write since the last call, oldest first: (channel ID, F´ time tag in ns, serialized "
        "value).");

    m.def(
        "responses",
        []() {
            py::list responses;
            for (const auto& response : WiseFsw::groundLink.takeResponses()) {
                responses.append(py::make_tuple(response.context, response.response));
            }
            return responses;
        },
        "Every command response since the last call, oldest first: (context, Fw.CmdResponse value).");
}
