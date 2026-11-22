// `_rk4`, Rk4.hpp's step on a Python right-hand side, for rk4_test.py.
#include <functional>

#include <Eigen/Dense>
#include <pybind11/eigen.h>
#include <pybind11/functional.h>
#include <pybind11/pybind11.h>

#include "algorithms/utils/rk4/Rk4.hpp"

using Rhs = std::function<Eigen::VectorXd(double, const Eigen::VectorXd&)>;

PYBIND11_MODULE(_rk4, m) {
    m.def(
        "step",
        [](const Rhs& fun, double t, const Eigen::VectorXd& y, double h) -> Eigen::VectorXd {
            return Rk4::step(fun, t, y, h);
        },
        "One RK4 step of dy/dt = fun(t, y) from t to t + h.");
}
