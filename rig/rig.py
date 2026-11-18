# =============================================================================
# RIG
# Virtual tyre test rig: fixed frame, belt at the imposed speed V, wheel
# steered by delta, vertical load P on the fork (report ch. 2). One time step
# with classical RK4 and the friction switch frozen during the step (7.2).
# Physics is a pure function: step(state, controls, conditions, wheel, dt).
# =============================================================================

import math
from dataclasses import dataclass

from rig.tyre import TyreAtLoad, at_load, peak_slip
from rig.wheel import (G, Wheel, WheelResult, WheelState, evaluate, free_rolling_radius,
                       friction_direction, loaded_radius, stop_if_reversed)

V_MAX = 70.0                    # [m/s] highest belt speed (design choice)
LOAD_RANGE = (0.5, 1.5)         # [-]   contact load range / f_z0
V_START = 20.0                  # [m/s] belt speed at the start of every scenario (report 8.2)
V_RESET = 10.0                  # [m/s] belt speed after a reset of the interface (report 7.3)


# =============================================================================
# INPUTS AND TEST CONDITIONS
# Inputs come from the controls; test conditions from the interface (2.3).
# =============================================================================

@dataclass(frozen=True)
class Controls:
    delta: float = 0.0      # [rad] steer angle from the belt direction, CCW from above
    t_d: float = 0.0        # [N m] drive torque, >= 0
    t_b: float = 0.0        # [N m] brake torque, >= 0


@dataclass(frozen=True)
class Conditions:
    v: float = V_START      # [m/s] belt speed, 0..V_MAX
    p: float = Wheel().f_z_ref - Wheel().m_w * G     # [N] vertical load on the fork, F_z = reference load


# Returns the contact load F_z [N] = P + m_w g (report 5.2).
def contact_load(c: Conditions, w: Wheel) -> float:
    return c.p + w.m_w * G


# Returns the allowed range of the fork load P [N] for the wheel.
def load_limits(w: Wheel) -> tuple:
    return (LOAD_RANGE[0] * w.tyre.f_z0 - w.m_w * G, LOAD_RANGE[1] * w.tyre.f_z0 - w.m_w * G)


# Raises ValueError if the test conditions are outside the validity domain.
def check_conditions(c: Conditions, w: Wheel) -> None:
    lo, hi = load_limits(w)
    if not 0.0 <= c.v <= V_MAX:
        raise ValueError(f"belt speed {c.v} m/s outside 0..{V_MAX} m/s")
    if not lo <= c.p <= hi:
        raise ValueError(f"fork load {c.p:.0f} N outside {lo:.0f}..{hi:.0f} N")


# Returns the hub velocity (V_x, V_y) [m/s] in the wheel frame (report 3.1).
def hub_velocity(c: Conditions, u: Controls) -> tuple:
    return c.v * math.cos(u.delta), -c.v * math.sin(u.delta)


# =============================================================================
# REFERENCE STATES AND TORQUES
# =============================================================================

# Returns the free-rolling state at belt speed v [m/s] with delta = 0.
def free_rolling(v: float, w: Wheel) -> WheelState:
    return WheelState(omega=v / free_rolling_radius(w), tau_x=0.0, tau_y=0.0)


# Returns the locking torque T_lock [N m] = mu_0 F_z h at the given conditions.
def locking_torque(c: Conditions, w: Wheel) -> float:
    k = at_load(contact_load(c, w), w.tyre)
    return k.d * loaded_radius(w)


# Returns the torque limit T_max [N m] = 1.1 T_lock at the current load (D9).
def torque_limit(c: Conditions, w: Wheel) -> float:
    return 1.1 * locking_torque(c, w)


# =============================================================================
# TIME STEP
# RK4 on (Omega, tau_x, tau_y), inputs and conditions held over the step;
# nu decided at the start, spin stopped at the end if it reversed.
# =============================================================================

# Returns the state after one time step dt [s].
def step(q: WheelState, u: Controls, c: Conditions, w: Wheel, dt: float) -> WheelState:
    f_z = contact_load(c, w)
    k = at_load(f_z, w.tyre)
    v_x, v_y = hub_velocity(c, u)
    nu = friction_direction(v_x, v_y, f_z, u.t_d, u.t_b, q, w, k)

    # derivatives at state s, inputs and nu held
    def rate(s: WheelState) -> WheelResult:
        return evaluate(v_x, v_y, f_z, u.t_d, u.t_b, nu, s, w, k)

    # state s advanced by a [s] along the rates r
    def shifted(s: WheelState, r: WheelResult, a: float) -> WheelState:
        return WheelState(s.omega + a * r.omega_dot, s.tau_x + a * r.tau_x_dot, s.tau_y + a * r.tau_y_dot)

    k1 = rate(q)
    k2 = rate(shifted(q, k1, 0.5 * dt))
    k3 = rate(shifted(q, k2, 0.5 * dt))
    k4 = rate(shifted(q, k3, dt))
    omega = q.omega + dt / 6.0 * (k1.omega_dot + 2.0 * k2.omega_dot + 2.0 * k3.omega_dot + k4.omega_dot)
    tau_x = q.tau_x + dt / 6.0 * (k1.tau_x_dot + 2.0 * k2.tau_x_dot + 2.0 * k3.tau_x_dot + k4.tau_x_dot)
    tau_y = q.tau_y + dt / 6.0 * (k1.tau_y_dot + 2.0 * k2.tau_y_dot + 2.0 * k3.tau_y_dot + k4.tau_y_dot)
    end = WheelState(omega, tau_x, tau_y)
    return WheelState(stop_if_reversed(v_x, v_y, f_z, u.t_d, u.t_b, nu, end, w, k), tau_x, tau_y)


# =============================================================================
# OUTPUTS
# Everything the display and the tests read; undefined values are NaN (3.5).
# =============================================================================

@dataclass(frozen=True)
class Outputs:
    f_z: float              # [N]     contact load
    nu: int                 # [-]     friction direction for the next step, 0 = held
    v_x: float              # [m/s]   hub velocity along x
    v_y: float              # [m/s]   hub velocity along y
    alpha: float            # [rad]   slip angle, NaN at V = 0
    radius: float           # [m]     rolling radius V_x / Omega, NaN at Omega = 0
    s_x: float              # [-]     practical slip, NaN at V_x = 0
    s_y: float              # [-]
    sigma_x: float          # [-]     theoretical slip, NaN at Omega = 0
    sigma_y: float          # [-]
    wheel: WheelResult      # forces, moments and derivatives
    f_par: float            # [N]     tyre force along the belt
    f_perp: float           # [N]     tyre force across the belt
    r_hx: float             # [N]     hub forces: frame on the wheel
    r_hy: float             # [N]
    r_hz: float             # [N]
    m_hx: float             # [N m]   hub moments: frame on the wheel
    m_hz: float             # [N m]
    p_belt: float           # [W]     power of the belt drive, -F_par V
    p_motor: float          # [W]     power of the drive torque, T_D Omega
    p_friction: float       # [W]     power lost in brake and rolling resistance
    p_kinetic: float        # [W]     rate of the kinetic energy, J_w Omega Omega_dot
    p_tyre: float           # [W]     power taken by the tyre


# Returns every output of the rig at state q.
def outputs(q: WheelState, u: Controls, c: Conditions, w: Wheel) -> Outputs:
    f_z = contact_load(c, w)
    k = at_load(f_z, w.tyre)
    h, r_0 = loaded_radius(w), free_rolling_radius(w)
    v_x, v_y = hub_velocity(c, u)
    nu = friction_direction(v_x, v_y, f_z, u.t_d, u.t_b, q, w, k)
    r = evaluate(v_x, v_y, f_z, u.t_d, u.t_b, nu, q, w, k)
    nan = math.nan
    rolling = q.omega * r_0
    f_par = r.f_x * math.cos(u.delta) - r.f_y * math.sin(u.delta)
    f_perp = r.f_x * math.sin(u.delta) + r.f_y * math.cos(u.delta)
    return Outputs(
        f_z=f_z, nu=nu, v_x=v_x, v_y=v_y,
        alpha=math.atan2(-v_y, v_x) if c.v > 0.0 else nan,
        radius=v_x / q.omega if q.omega != 0.0 else nan,
        s_x=r.v_sx / v_x if v_x != 0.0 else nan,
        s_y=r.v_sy / v_x if v_x != 0.0 else nan,
        sigma_x=r.v_sx / rolling if rolling != 0.0 else nan,
        sigma_y=r.v_sy / rolling if rolling != 0.0 else nan,
        wheel=r, f_par=f_par, f_perp=f_perp,
        r_hx=-r.f_x, r_hy=-r.f_y, r_hz=-c.p, m_hx=-h * r.f_y, m_hz=-r.m_z,
        p_belt=-f_par * c.v, p_motor=u.t_d * q.omega, p_friction=-r.t_friction * q.omega,
        p_kinetic=w.j_w * q.omega * r.omega_dot,
        p_tyre=-(r.f_x * r.v_sx + r.f_y * r.v_sy) + r.f_x * q.omega * (h - r_0))


# Returns the slip at the peak force s_p [-] at the current load.
def peak_slip_at(c: Conditions, w: Wheel) -> float:
    return peak_slip(at_load(contact_load(c, w), w.tyre))
