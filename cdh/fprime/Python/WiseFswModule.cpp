// Temporary: the deployment's Python interface, hand-written until fprime-python's autocoder generates it.
// One deployment per process: its component instances are the topology's globals.
#include <pybind11/eigen.h>
#include <pybind11/pybind11.h>

#include "Os/Os.hpp"
#include "cdh/fprime/Top/WiseFswTopology.hpp"

namespace py = pybind11;

namespace {

bool g_setUp = false;
WiseFsw::TopologyState g_state;

Gnc::Vector3 vector3(const Eigen::Vector3d& v) {
    return Gnc::Vector3({v.x(), v.y(), v.z()});
}

}  // namespace

PYBIND11_MODULE(_wise_fsw, m) {
    m.doc() = "The WiseFsw F´ deployment, run inside the simulation's process.";

    m.def(
        "boot",
        [](double mu, const Eigen::Matrix3d& dcm_PB) {
            if (!g_setUp) {
                Os::init();
                WiseFsw::setupTopology(g_state);
                g_setUp = true;
            }
            WiseFsw::tlmCapture.clear();
            WiseFsw::simTime.set(0.0);
            WiseFsw::nav.configure(mu, dcm_PB);
        },
        py::arg("mu"), py::arg("dcm_PB"),
        "Sets the deployment up on first use, and boots it at t = 0 s: telemetry cleared, the dead reckoner idle "
        "with mu (m^3/s^2) and the IMU's mounting [PB].");

    m.def(
        "initialize_nav",
        [](double t, const Eigen::Vector3d& sigma_BN, const Eigen::Vector3d& r_BN_N, const Eigen::Vector3d& v_BN_N) {
            WiseFsw::simTime.set(t);
            WiseFsw::nav.initialize(t, sigma_BN, r_BN_N, v_BN_N);
        },
        py::arg("t"), py::arg("sigma_BN"), py::arg("r_BN_N"), py::arg("v_BN_N"),
        "Gives the dead reckoner its state at t (s). Temporary: the initNavState command replaces it.");

    m.def(
        "step",
        [](double t, const Eigen::Vector3d& angVelPlatform, const Eigen::Vector3d& accelPlatform) {
            WiseFsw::simTime.set(t);
            WiseFsw::simBridge.sendImu(vector3(angVelPlatform), vector3(accelPlatform));
            WiseFsw::simBridge.tick();
        },
        py::arg("t"), py::arg("angVelPlatform"), py::arg("accelPlatform"),
        "Sets the clock to t (s), sends the IMU reading and runs the schedule once.");

    m.def(
        "telemetry",
        []() {
            py::dict latest;
            for (const auto& entry : WiseFsw::tlmCapture.latest()) {
                const Sim::TlmCapture::Sample& sample = entry.second;
                latest[py::int_(entry.first)] = py::make_tuple(
                    sample.time,
                    py::bytes(reinterpret_cast<const char*>(sample.value.data()), sample.value.size()));
            }
            return latest;
        },
        "The latest sample of every channel: channel ID to (time in s, serialized value).");
}
