# =============================================================================
# TYRE LAW
# Isotropic tyre built on the PAC2002 lateral coefficients of the Project
# Chrono sedan tyre (Sedan_Pac02Tire.tir, 245/40 R18). Report chapter 4:
# characteristic in practical slip (4.3), load factors (4.5), pneumatic trail (4.7) and
# relaxation length (6.5). Zero camber, no shifts, no residual torque.
# =============================================================================

import math
from dataclasses import dataclass


# =============================================================================
# TYRE FILE
# Coefficients copied unchanged from the tyre file. The ISO sign of PKY1 in
# the file (-21.92) is dropped: the report uses positive stiffness.
# =============================================================================

@dataclass(frozen=True)
class TyreFile:
    f_z0: float = 0.81 * 4850.0     # [N]    nominal load, LFZO * FNOMIN
    l_fz0: float = 0.81             # [-]    load scaling factor LFZO
    r_e: float = 0.344              # [m]    unloaded radius UNLOADED_RADIUS
    c_z: float = 280.8e3            # [N/m]  vertical stiffness VERTICAL_STIFFNESS
    p_cy1: float = 1.3507           # [-]    shape factor C
    p_dy1: float = 1.0489           # [-]    peak friction at f_z0
    p_dy2: float = -0.18033         # [-]    variation of peak friction with load
    p_ey1: float = -0.0074722       # [-]    curvature E at f_z0
    p_ey2: float = -0.0063208       # [-]    variation of curvature with load
    p_ky1: float = 21.92            # [-]    maximum cornering stiffness / f_z0
    p_ky2: float = 2.0012           # [-]    load at maximum stiffness / f_z0
    p_ty1: float = 2.144            # [-]    peak relaxation length / r_e
    p_ty2: float = 1.983            # [-]    load at peak relaxation length / f_z0
    q_bz1: float = 10.904           # [-]    trail stiffness factor B_t
    q_bz2: float = -1.8412          # [-]    variation of B_t with load
    q_bz3: float = -0.52041         # [-]    variation of B_t with load squared
    q_cz1: float = 1.2136           # [-]    trail shape factor C_t
    q_dz1: float = 0.093509         # [-]    trail at zero slip / r_e
    q_dz2: float = -0.0092183       # [-]    variation of the trail with load
    q_ez1: float = -1.5697          # [-]    trail curvature E_t
    q_ez2: float = 0.33394          # [-]    variation of E_t with load
    q_ez4: float = 0.26711          # [-]    variation of E_t with the slip angle


# =============================================================================
# TYRE AT A GIVEN LOAD
# Every load-dependent factor, computed once per time step (assumption A3).
# =============================================================================

@dataclass(frozen=True)
class TyreAtLoad:
    f_z: float      # [N]    contact load
    mu_0: float     # [-]    peak friction coefficient
    mu_1: float     # [-]    sliding friction coefficient, F_t(inf) / F_z
    b: float        # [-]    Magic Formula stiffness factor
    c: float        # [-]    Magic Formula shape factor
    d: float        # [N]    Magic Formula peak
    e: float        # [-]    Magic Formula curvature
    c_s: float      # [N]    slip stiffness, B C D
    d_relax: float  # [m]    relaxation length d
    d_t: float      # [m]    trail at zero slip
    b_t: float      # [-]    trail stiffness factor
    c_t: float      # [-]    trail shape factor
    e_t0: float     # [-]    trail curvature before the slip-angle term
    e_ta: float     # [-]    variation of the trail curvature with the slip angle


# Returns the tyre factors at contact load f_z [N] > 0 (report 4.5, 4.7, 6.5).
def at_load(f_z: float, t: TyreFile) -> TyreAtLoad:
    df_z = (f_z - t.f_z0) / t.f_z0
    mu_0 = t.p_dy1 + t.p_dy2 * df_z
    d = mu_0 * f_z
    c = t.p_cy1
    c_s = t.p_ky1 * t.f_z0 * math.sin(2.0 * math.atan(f_z / (t.p_ky2 * t.f_z0)))
    return TyreAtLoad(
        f_z=f_z, mu_0=mu_0, mu_1=mu_0 * math.sin(c * math.pi / 2.0),
        b=c_s / (c * d), c=c, d=d, e=min(t.p_ey1 + t.p_ey2 * df_z, 1.0), c_s=c_s,
        d_relax=t.p_ty1 * math.sin(2.0 * math.atan(f_z / (t.p_ty2 * t.f_z0))) * t.r_e * t.l_fz0,
        d_t=f_z * (t.q_dz1 + t.q_dz2 * df_z) * t.r_e / t.f_z0,
        b_t=t.q_bz1 + t.q_bz2 * df_z + t.q_bz3 * df_z * df_z,
        c_t=t.q_cz1,
        e_t0=t.q_ez1 + t.q_ez2 * df_z,
        e_ta=t.q_ez4)


# =============================================================================
# CHARACTERISTIC
# F_t(s) = D sin(C arctan(B s - E (B s - arctan B s))), s >= 0 (report 4.3).
# =============================================================================

# Returns the size of the tangential force F_t [N] for the slip size s >= 0 [-].
def characteristic(s: float, k: TyreAtLoad) -> float:
    bs = k.b * s
    return k.d * math.sin(k.c * math.atan(bs - k.e * (bs - math.atan(bs))))


# Returns the slip s_p [-] at the peak of the characteristic (where C arctan(...) = pi/2).
def peak_slip(k: TyreAtLoad) -> float:
    lo, hi = 0.0, 10.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        bs = k.b * mid
        if k.c * math.atan(bs - k.e * (bs - math.atan(bs))) < math.pi / 2.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# =============================================================================
# PNEUMATIC TRAIL
# t = D_t cos(C_t arctan(B_t a - E_t (B_t a - arctan B_t a))) cos(alpha),
# a = |tan alpha|, the slip input of PAC2002 (alpha_t = tan alpha, no shift), any alpha (report 4.7).
# =============================================================================

# Returns the pneumatic trail t [m] for the slip angle alpha [rad], any value.
def trail(alpha: float, k: TyreAtLoad) -> float:
    a = abs(math.tan(alpha))
    e_t = min(k.e_t0 * (1.0 + k.e_ta * 2.0 / math.pi * math.atan(k.b_t * k.c_t * a)), 1.0)
    x = k.b_t * a
    return k.d_t * math.cos(k.c_t * math.atan(x - e_t * (x - math.atan(x)))) * math.cos(alpha)
