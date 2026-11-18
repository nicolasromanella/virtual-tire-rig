# =============================================================================
# WHEEL
# The wheel subsystem, the same function on the rig and in the simulator
# (report 2.6): hub velocity, load and torques in; state derivatives,
# tyre forces and hub actions out. Kinematics (ch. 3), isotropic tyre (ch. 4),
# spin equation with the friction switch (5.4) and transient tyre with
# carcass damping (ch. 6). Wheel frame: x forward, y left, z up, origin at O.
# =============================================================================

import math
from dataclasses import dataclass, field

from rig.tyre import TyreAtLoad, TyreFile, characteristic, trail

G = 9.81    # [m/s^2] gravitational acceleration


# =============================================================================
# WHEEL PARAMETERS
# Chrono sedan wheel (rim + tyre); rolling resistance from De Felice and Wong.
# =============================================================================

@dataclass(frozen=True)
class Wheel:
    m_w: float = 24.7                   # [kg]     mass of rim and tyre
    j_w: float = 1.10                   # [kg m^2] spin inertia
    f_z_ref: float = 275.0 * G          # [N]      reference contact load, radii computed here (A4)
    f_0: float = 0.015                  # [-]      rolling resistance at zero speed
    k_f: float = 5.2e-7                 # [s^2/m^2] growth of rolling resistance with rolling speed
    c_0: float = 233.0                  # [N s/m]  carcass damping (design choice)
    rolling_resistance: bool = True     # switch for M_y (scenarios S19, S20)
    tyre: TyreFile = field(default_factory=TyreFile)


# Returns the loaded radius h [m], height of the hub (report 5.1).
def loaded_radius(w: Wheel) -> float:
    return w.tyre.r_e - w.f_z_ref / w.tyre.c_z


# Returns the free-rolling radius R_0 [m] (report 5.1).
def free_rolling_radius(w: Wheel) -> float:
    return w.tyre.r_e - w.f_z_ref / (3.0 * w.tyre.c_z)


# Returns the largest torque [N m] friction can hold at Omega = 0, T_B + f_0 F_z h (report 5.4).
def holding_limit(t_b: float, f_z: float, w: Wheel) -> float:
    return t_b + (w.f_0 * f_z * loaded_radius(w) if w.rolling_resistance else 0.0)


# =============================================================================
# WHEEL STATE
# =============================================================================

@dataclass(frozen=True)
class WheelState:
    omega: float = 0.0      # [rad/s] spin of the rim, positive rolling forward
    tau_x: float = 0.0      # [-]     transient slip along x, carcass deflection / d
    tau_y: float = 0.0      # [-]     transient slip along y


# =============================================================================
# WHEEL RESULT
# Derivatives of the states and every force and moment of one evaluation.
# =============================================================================

@dataclass(frozen=True)
class WheelResult:
    omega_dot: float    # [rad/s^2] spin acceleration
    tau_x_dot: float    # [1/s]     rate of the transient slip along x
    tau_y_dot: float    # [1/s]     rate of the transient slip along y
    v_sx: float         # [m/s]     slip velocity along x
    v_sy: float         # [m/s]     slip velocity along y
    tau_star_x: float   # [-]       slip passed to the characteristic, x
    tau_star_y: float   # [-]       slip passed to the characteristic, y
    f_x: float          # [N]       road force on the tyre along x
    f_y: float          # [N]       road force on the tyre along y
    m_y: float          # [N m]     rolling-resistance moment
    m_z: float          # [N m]     aligning moment
    t_net: float        # [N m]     net torque of motor and brake on the rim, T
    t_friction: float   # [N m]     friction torque on the rim, brake + rolling resistance
    t_hold: float       # [N m]     torque a wheel at rest must hold, T_h = T_D - h F_x
    trail: float        # [m]       pneumatic trail


# =============================================================================
# WHEEL EQUATIONS
# nu = +1 / -1: friction against the spin (rolling, or breaking free);
# nu = 0: wheel held at rest, Omega_dot = 0 (report 5.4).
# nu is decided once per time step by friction_direction.
# =============================================================================

# Returns derivatives, forces and moments for hub velocity (v_x, v_y) [m/s], load f_z [N], torques t_d, t_b [N m].
def evaluate(v_x: float, v_y: float, f_z: float, t_d: float, t_b: float, nu: int,
             q: WheelState, w: Wheel, k: TyreAtLoad) -> WheelResult:
    h = loaded_radius(w)
    r_0 = free_rolling_radius(w)

    # Slip velocity and transient tyre (report 3.4, 6.4)
    v_sx = v_x - q.omega * r_0
    v_sy = v_y
    speed = abs(v_x)
    d_eff = k.d_relax * (1.0 + w.c_0 * speed / k.c_s)
    tau_x_dot = (v_sx - speed * q.tau_x) / d_eff
    tau_y_dot = (v_sy - speed * q.tau_y) / d_eff
    damping = w.c_0 * k.d_relax / k.c_s                     # [s] c_0 d / C_s
    tau_star_x = q.tau_x + damping * tau_x_dot
    tau_star_y = q.tau_y + damping * tau_y_dot

    # Isotropic tyre force, opposite to the transient slip (report 6.4)
    size = math.hypot(tau_star_x, tau_star_y)
    if size > 0.0:
        scale = characteristic(size, k) / size
        f_x, f_y = -scale * tau_star_x, -scale * tau_star_y
    else:
        f_x, f_y = 0.0, 0.0

    # Aligning moment; at rest (v_x = v_y = 0) the slip angle is taken as zero (atan2 of -0.0 would give pi)
    alpha = math.atan2(-v_y, v_x) if (v_x != 0.0 or v_y != 0.0) else 0.0
    t = trail(alpha, k)
    m_z = -t * f_y

    # Spin equation with the friction switch (report 5.4)
    rolling = w.f_0 + w.k_f * (q.omega * r_0) ** 2 if w.rolling_resistance else 0.0
    t_roll = rolling * f_z * h                              # [N m] rolling-resistance torque while rolling
    t_hold = t_d - h * f_x
    if nu == 0:
        capacity = holding_limit(t_b, f_z, w)
        share = t_b / capacity if capacity > 0.0 else 1.0   # brake part of the holding torque
        t_friction = -t_hold
        m_y = -t_hold * (1.0 - share)
        t_net = t_d - t_hold * share
        omega_dot = 0.0
    else:
        t_friction = -nu * (t_b + t_roll)
        m_y = -nu * t_roll
        t_net = t_d - nu * t_b
        omega_dot = (t_hold + t_friction) / w.j_w

    return WheelResult(omega_dot, tau_x_dot, tau_y_dot, v_sx, v_sy, tau_star_x, tau_star_y,
                       f_x, f_y, m_y, m_z, t_net, t_friction, t_hold, t)


# =============================================================================
# FRICTION SWITCH
# Decided from the state at the start of a time step (report 7.2).
# =============================================================================

# Returns nu: sign of Omega while rolling; at Omega = 0, 0 if held, else the sign of T_h.
def friction_direction(v_x: float, v_y: float, f_z: float, t_d: float, t_b: float,
                       q: WheelState, w: Wheel, k: TyreAtLoad) -> int:
    if q.omega > 0.0:
        return 1
    if q.omega < 0.0:
        return -1
    t_hold = evaluate(v_x, v_y, f_z, t_d, t_b, 0, q, w, k).t_hold
    if abs(t_hold) <= holding_limit(t_b, f_z, w):
        return 0
    return 1 if t_hold > 0.0 else -1


# Returns the spin at the end of a step: zero if it reversed against nu and the friction can hold it there.
def stop_if_reversed(v_x: float, v_y: float, f_z: float, t_d: float, t_b: float, nu: int,
                     q: WheelState, w: Wheel, k: TyreAtLoad) -> float:
    if nu == 0 or q.omega * nu >= 0.0:
        return q.omega
    at_rest = WheelState(0.0, q.tau_x, q.tau_y)
    if friction_direction(v_x, v_y, f_z, t_d, t_b, at_rest, w, k) == 0:
        return 0.0
    return q.omega
