// The classic fourth-order Runge–Kutta step: rk4.py's, for the F´ build.
#ifndef UTILS_RK4_HPP
#define UTILS_RK4_HPP

namespace Rk4 {

//! One RK4 step of dy/dt = fun(t, y, args...) from t to t + h, returning the state at t + h.
//! State is any type with + and scalar *, such as an Eigen vector.
template <typename Fun, typename State, typename... Args>
State step(const Fun& fun, double t, const State& y, double h, const Args&... args) {
    const State k1 = fun(t, y, args...);
    const State k2 = fun(t + 0.5 * h, State(y + 0.5 * h * k1), args...);
    const State k3 = fun(t + 0.5 * h, State(y + 0.5 * h * k2), args...);
    const State k4 = fun(t + h, State(y + h * k3), args...);
    return y + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
}

}  // namespace Rk4

#endif
