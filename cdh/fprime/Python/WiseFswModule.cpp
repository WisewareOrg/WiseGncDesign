// The deployment's Python interface: a hand-written pybind11 module.
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

Gnc::Matrix3 matrix3(const Eigen::Matrix3d& m) {
    return Gnc::Matrix3({Gnc::Vector3({m(0, 0), m(0, 1), m(0, 2)}), Gnc::Vector3({m(1, 0), m(1, 1), m(1, 2)}),
                         Gnc::Vector3({m(2, 0), m(2, 1), m(2, 2)})});
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
            WiseFsw::simTime.set(0U);
            WiseFsw::simBridge.configureNav(mu, matrix3(dcm_PB));
        },
        py::arg("mu"), py::arg("dcm_PB"),
        "Sets the deployment up on first use, and boots it at t = 0 s: telemetry cleared, the dead reckoner idle "
        "with mu (m^3/s^2) and the IMU's mounting [PB].");

    m.def(
        "initialize_nav",
        [](U64 t_ns, const Eigen::Vector3d& sigma_BN, const Eigen::Vector3d& r_BN_N, const Eigen::Vector3d& v_BN_N) {
            WiseFsw::tlmCapture.clear();
            WiseFsw::simTime.set(t_ns);
            WiseFsw::simBridge.initializeNav(vector3(sigma_BN), vector3(r_BN_N), vector3(v_BN_N));
        },
        py::arg("t_ns"), py::arg("sigma_BN"), py::arg("r_BN_N"), py::arg("v_BN_N"),
        "Gives the dead reckoner its state at t_ns (ns); telemetry() then holds what that wrote. Temporary: the "
        "initNavState command replaces it.");

    m.def(
        "step",
        [](U64 t_ns, const Eigen::Vector3d& angVelPlatform, const Eigen::Vector3d& accelPlatform) {
            WiseFsw::tlmCapture.clear();
            WiseFsw::simTime.set(t_ns);
            WiseFsw::simBridge.sendImu(vector3(angVelPlatform), vector3(accelPlatform));
            WiseFsw::simBridge.tick();
        },
        py::arg("t_ns"), py::arg("angVelPlatform"), py::arg("accelPlatform"),
        "Sets the clock to t_ns (ns), sends the IMU reading and runs the schedule once; telemetry() then holds "
        "what that tick wrote.");

    m.def(
        "telemetry",
        []() {
            py::dict latest;
            for (const auto& entry : WiseFsw::tlmCapture.latest()) {
                latest[py::int_(entry.first)] =
                    py::bytes(reinterpret_cast<const char*>(entry.second.data()), entry.second.size());
            }
            return latest;
        },
        "Every channel the last boot, initialize_nav or step wrote: channel ID to serialized value.");
}
