// Spike pins for #52: boot(prm_path), SimHub push/drain, F´'s own serialization of the bus struct, nav's parameters.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <string>

#include "Os/Os.hpp"
#include "Sim/Cooperative.hpp"
#include "Top/SpikeTopology.hpp"

namespace py = pybind11;

namespace {

Sim::Cooperative g_cooperative;
bool g_booted = false;

py::bytes toBytes(const U8* data, FwSizeType size) {
    return py::bytes(reinterpret_cast<const char*>(data), size);
}

}  // namespace

PYBIND11_MODULE(_spike_fsw, m) {
    m.doc() = "Spike deployment; nothing is set up until boot(prm_path).";

    m.def(
        "boot",
        [](const std::string& prmPath) {
            if (g_booted) {
                throw std::runtime_error("already booted: power-cycle by loading a fresh copy");
            }
            Os::init();
            Os::Task::registerTaskRegistry(&g_cooperative);
            Os::Queue::setRegistry(&g_cooperative);
            Spike::setupTopology(Spike::TopologyState{prmPath.c_str()});
            g_cooperative.pump();
            g_booted = true;
        },
        py::arg("prm_path"),
        "Sets up the topology: PrmDb reads prm_path, every component loads its parameters, tasks start.");

    m.def(
        "push",
        [](FwIndexType port, const py::bytes& data) {
            const std::string raw = data;
            return static_cast<int>(
                Spike::simHub.push(port, reinterpret_cast<const U8*>(raw.data()), static_cast<FwSizeType>(raw.size())));
        },
        py::arg("port"), py::arg("data"), "Pushes bytes out SimHub.busOut[port]; returns the Fw::SerializeStatus.");

    m.def(
        "drain",
        [](FwIndexType port) {
            py::list out;
            for (const auto& msg : Spike::simHub.drain(port)) {
                out.append(toBytes(msg.data(), msg.size()));
            }
            return out;
        },
        py::arg("port"), "Every message SimHub.busIn[port] received since the last call.");

    m.def("imu_received", []() {
        const Rio::ImuSensorMsg& msg = Spike::imuSink.last;
        std::array<F64, 3> w{}, a{};
        for (FwSizeType i = 0; i < 3; i++) {
            w[i] = msg.get_AngVelPlatform()[i];
            a[i] = msg.get_AccelPlatform()[i];
        }
        return py::make_tuple(Spike::imuSink.count, msg.get_timeTag(), w, a);
    });

    m.def(
        "serialize_imu",
        [](U64 timeTag, const std::array<F64, 3>& w, const std::array<F64, 3>& a) {
            Rio::ImuSensorMsg msg;
            msg.set_timeTag(timeTag);
            for (FwSizeType i = 0; i < 3; i++) {
                msg.get_AngVelPlatform()[i] = w[i];
                msg.get_AccelPlatform()[i] = a[i];
            }
            U8 storage[Rio::ImuSensorMsg::SERIALIZED_SIZE];
            Fw::ExternalSerializeBuffer buffer(storage, sizeof(storage));
            FW_ASSERT(msg.serializeTo(buffer) == Fw::FW_SERIALIZE_OK);
            return toBytes(buffer.getBuffAddr(), buffer.getSize());
        },
        "F´'s own serialization (ImuSensorMsg::serializeTo) of the bus struct.");

    m.attr("IMU_SERIALIZED_SIZE") = static_cast<int>(Rio::ImuSensorMsg::SERIALIZED_SIZE);

    m.def("nav_params", []() {
        Fw::ParamValid muValid, dcmValid;
        const F64 mu = Spike::nav.mu(muValid);
        const Nav::Matrix3 dcm = Spike::nav.dcm_PB(dcmValid);
        std::array<std::array<F64, 3>, 3> rows{};
        for (FwSizeType r = 0; r < 3; r++) {
            for (FwSizeType c = 0; c < 3; c++) {
                rows[r][c] = dcm[r][c];
            }
        }
        return py::make_tuple(mu, muValid == Fw::ParamValid::VALID, rows,
                              dcmValid == Fw::ParamValid::VALID, Spike::nav.loadedCount);
    });
}
