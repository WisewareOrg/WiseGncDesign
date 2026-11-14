// The deployment's Python interface: a hand-written pybind11 module.
// One deployment per loaded copy: its component instances are the topology's globals.
#include <pybind11/eigen.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <stdexcept>
#include <string>
#include <vector>

#include "Fw/Types/Assert.hpp"
#include "Os/Os.hpp"
#include "fsw/fprime/platform/Cooperative.hpp"
#include WISE_FSW_TOPOLOGY_HEADER

namespace py = pybind11;

namespace {

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

}  // namespace

PYBIND11_MODULE(_wise_fsw, m) {
    m.doc() = "The WiseFsw F´ deployment, run inside the simulation's process; set up by boot, once per copy.";

    g_assertHook.registerHook();

    m.def(
        "boot",
        [](const std::string& prm_path, const std::vector<FwPrmIdType>& parameter_ids) {
            if (g_booted) {
                throw std::runtime_error("already booted: power-cycle by loading a fresh copy");
            }
            const std::string directory = prm_path.substr(0, prm_path.rfind('/'));
            if (prm_path.empty() || prm_path.front() != '/' || directory.empty()) {
                throw py::value_error("the parameter file " + prm_path +
                                      " is not an absolute path in a directory below the root");
            }
            g_booted = true;
            Os::init();
            Os::Task::registerTaskRegistry(&g_cooperative);
            Os::Queue::setRegistry(&g_cooperative);
            WiseFsw::setupTopology(WiseFsw::TopologyState{prm_path.c_str(), directory.c_str()});
            std::string invalid;
            for (const FwPrmIdType id : parameter_ids) {
                Fw::ParamBuffer value;
                if (WiseFsw::prmDb.getPrm_handlerBase(0, id, value) != Fw::ParamValid::VALID) {
                    invalid += (invalid.empty() ? "" : ", ") + std::to_string(id);
                }
            }
            if (!invalid.empty()) {
                throw std::runtime_error("parameters " + invalid + " are not valid after loading " + prm_path);
            }
        },
        py::arg("prm_path"), py::arg("parameter_ids"),
        "Sets the topology up and boots it at t = 0 s, the dead reckoner idle: PrmDb loads prm_path, an absolute "
        "path whose directory is its sandbox. Raises ValueError for a relative path or one in the root directory, "
        "and RuntimeError naming each of parameter_ids that is not valid once loaded. A copy boots once: a second "
        "boot raises RuntimeError.");

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
