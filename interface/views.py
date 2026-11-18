# =============================================================================
# WHEEL VIEWS
# 3D view of the rig (report fig. 2.1 geometry), 3D free-body diagram of the
# wheel (fig. 5.1), side view (fig. 3.3-3.4) and top view fixed to the belt
# (fig. 2.2b). Every quantity comes from the rig outputs of the current
# frame; nothing here computes physics.
# =============================================================================

import math

import pygame

from interface import draw as d

DEFLECTION_SCALE = 5.0      # [-] carcass deflection drawn enlarged
FRAME = d.REACTION          # actions of the frame on the wheel (free-body diagram)


# =============================================================================
# 3D CAMERA
# Default azimuth 68 deg, elevation 36 deg; drag with the mouse to orbit.
# World frame: X along the belt direction e_r, Y to its left, Z up, origin O.
# =============================================================================

AZIMUTH, ELEVATION = math.radians(68.0), math.radians(36.0)   # [rad] default camera
ELEVATION_RANGE = (math.radians(5.0), math.radians(89.0))      # [rad] always above the road
ORBIT_RATE = math.radians(0.4)                                 # [rad/px] camera turn per pixel dragged
ORBIT_HINT = "drag: rotate · wheel: zoom · right click: reset view"
ZOOM_RANGE = (0.5, 4.0)                                         # [-] mouse-wheel zoom, share of the fitted scale


# Returns the camera axes (right, up, towards the viewer) for azimuth and elevation [rad].
def camera(az: float, el: float):
    right = (-math.sin(az), math.cos(az), 0.0)
    up = (-math.sin(el) * math.cos(az), -math.sin(el) * math.sin(az), math.cos(el))
    towards = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    return right, up, towards


# Returns the dot product of two 3D vectors.
def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


# Returns the sum of 3D vectors.
def _add(*vs):
    return tuple(sum(c) for c in zip(*vs))


# Returns the 3D vector v times k.
def _mul(k, v):
    return (k * v[0], k * v[1], k * v[2])


# Returns the convex hull of 2D points, counter-clockwise (monotone chain).
def _hull(points):
    pts = sorted(set(points))
    # lower or upper half of the hull
    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(p)
        return h[:-1]
    return half(pts) + half(pts[::-1])


# =============================================================================
# MOTION BLUR
# A moving stripe is drawn as the band it sweeps in one frame, so fast motion
# does not alias (wagon-wheel effect); one red stripe marks the motion.
# =============================================================================

MARK = (255, 95, 80)        # red reference mark on tyre and belt (d.WARNING)
BELT_STEP = 0.24            # [m] spacing of the belt stripes, the same in every view
MARK_EVERY = 9              # [-] every 9th stripe is red (2.16 m)
SPOKES = 6                  # [-] spokes of the rim, in every view


# Returns the colour between back and front, fainter the longer the sweep [px or rad] compared with width.
def blur_colour(back, front, sweep: float, width: float, floor: float = 0.22):
    k = 1.0 if sweep <= width else max(width / sweep, floor)
    return tuple(int(b + (f - b) * k) for b, f in zip(back, front))


# =============================================================================
# PROJECTION
# Same camera for every 3D drawing; a box of corners is fitted into the panel.
# =============================================================================

class Projection:
    # Returns nothing; fits the box of 3D corners [drawing units] into rect at the camera az, el [rad].
    def __init__(self, rect: pygame.Rect, corners, az: float = AZIMUTH, el: float = ELEVATION):
        self.rect = rect
        self.home = (az, el)
        self.right, self.up, self.towards = camera(az, el)
        xs = [_dot(p, self.right) for p in corners]
        ys = [_dot(p, self.up) for p in corners]
        self.k = min((rect.w - 10) / (max(xs) - min(xs)), (rect.h - 10) / (max(ys) - min(ys)))
        self.cx = rect.centerx - self.k * 0.5 * (max(xs) + min(xs))
        self.cy = rect.centery + self.k * 0.5 * (max(ys) + min(ys))
        self.centre = _mul(1.0 / len(corners), _add(*corners))   # box centre stays at the same screen point
        self.anchor = self.p(self.centre)
        self.az, self.el = az, el
        self.k_fit = self.k                                       # [px/unit] fitted scale, zoom 1

    # Returns nothing; sets the camera [rad], same scale, box centre kept on screen.
    def look(self, az: float, el: float):
        self.az, self.el = az, min(max(el, ELEVATION_RANGE[0]), ELEVATION_RANGE[1])
        self.right, self.up, self.towards = camera(self.az, self.el)
        self.cx = self.anchor[0] - self.k * _dot(self.centre, self.right)
        self.cy = self.anchor[1] + self.k * _dot(self.centre, self.up)

    # Returns nothing; orbits the camera by a mouse drag [px].
    def orbit(self, dx: float, dy: float):
        self.look(self.az - ORBIT_RATE * dx, self.el + ORBIT_RATE * dy)

    # Returns nothing; zooms by factor about the centre of the box, within ZOOM_RANGE (mouse wheel).
    def zoom(self, factor: float):
        self.k = min(max(self.k * factor, ZOOM_RANGE[0] * self.k_fit), ZOOM_RANGE[1] * self.k_fit)
        self.look(self.az, self.el)

    # Returns nothing; back to the default camera and scale of this view.
    def reset_view(self):
        self.k = self.k_fit
        self.look(*self.home)

    # Returns the screen point [px] of a 3D point [drawing units].
    def p(self, v):
        return (self.cx + self.k * _dot(v, self.right), self.cy - self.k * _dot(v, self.up))

    # Draws a 3D arrow from start along vec [drawing units].
    def arrow(self, surface, colour, start, vec, width=3):
        d.arrow(surface, colour, self.p(start), self.p(_add(start, vec)), width, 11)

    # Draws a moment as an arc about the axis u x w at centre, span growing with |moment| / reference, with the
    # weight of the force arrows; returns the screen point at the head of the arc, or None if negligible.
    def moment(self, surface, colour, centre, u, w, radius: float, moment: float, reference: float, a0: float = 0.0):
        if not math.isfinite(moment) or abs(moment) < 1e-3 * reference:
            return None
        span = (0.4 + 2.0 * min(abs(moment) / reference, 1.0)) * (1 if moment > 0 else -1)
        pts = [self.p(_add(centre, _mul(radius * math.cos(a0 + span * i / 24), u), _mul(radius * math.sin(a0 + span * i / 24), w)))
               for i in range(25)]
        d.arc_line(surface, colour, pts, 3)                         # fixed-size head along the end tangent
        return pts[-1]

    # Draws the wheel at hub c with axes ex (along) and ey (axle), turned by spin [rad]; smear [rad] is the
    # rim rotation during one frame (motion blur); returns the outer face centre.
    def wheel(self, surface, c, ex, ey, spin: float, front_sign: float, r_e: float = 1.0, half_w: float = 0.16,
              smear: float = 0.0):
        ez = (0.0, 0.0, 1.0)
        n = 72
        ring = [_add(_mul(math.cos(2 * math.pi * i / n), ex), _mul(math.sin(2 * math.pi * i / n), ez)) for i in range(n)]
        front = _add(c, _mul(front_sign * half_w, ey))
        back = _add(c, _mul(-front_sign * half_w, ey))
        face = [self.p(_add(front, _mul(r_e, q))) for q in ring]
        rear = [self.p(_add(back, _mul(r_e, q))) for q in ring]
        pygame.draw.polygon(surface, d.TREAD, _hull(face + rear))
        pygame.draw.polygon(surface, d.AXIS, _hull(face + rear), 1)
        pygame.draw.polygon(surface, d.TYRE, face)
        pygame.draw.polygon(surface, d.DIM, face, 1)
        rim = [self.p(_add(front, _mul(0.45 * r_e, q))) for q in ring]
        pygame.draw.polygon(surface, d.RIM, rim)
        smear = max(min(smear, 2 * math.pi), -2 * math.pi)
        at = lambda a, r: self.p(_add(front, _mul(r * math.cos(a), ex), _mul(r * math.sin(a), ez)))
        # sector swept by an angle a .. a + smear between radii r0 and r1, as a screen polygon
        sector = lambda a, r0, r1: [at(a + smear * i / 12, r1) for i in range(13)] + [at(a + smear * (12 - i) / 12, r0) for i in range(13)]
        spoke = (110, 115, 125)
        for k in range(SPOKES):
            a = -spin + 2 * math.pi * k / SPOKES                     # positive spin: bottom moves backwards
            if abs(smear) < 0.06:
                pygame.draw.line(surface, spoke, self.p(front), at(a, 0.43), 2)
            else:
                pygame.draw.polygon(surface, blur_colour(d.RIM, spoke, abs(smear), 0.06), sector(a, 0.02, 0.43))
        if abs(smear) < 0.06:
            pygame.draw.line(surface, MARK, at(-spin, 0.62 * r_e), at(-spin, 0.97 * r_e), 3)
        else:
            pygame.draw.polygon(surface, blur_colour(d.TYRE, MARK, abs(smear), 0.06, 0.1), sector(-spin, 0.62 * r_e, 0.97 * r_e))
        return front


# =============================================================================
# RIG IN 3D
# Belt, fork, wheel, joint, load P along the steering axis and vectors.
# =============================================================================

class Rig3D(Projection):
    # Returns nothing; fits rig, fork and load arrow into rect.
    def __init__(self, rect: pygame.Rect):
        # fit what is seen: wheel at any delta, fork, load arrow and the ground around O; the belt is clipped
        pts = [(x, y, z) for x in (-1.1, 1.1) for y in (-1.1, 1.1) for z in (0.0, 1.95)] + [(0, 0, 3.75), (0, 0.45, 3.75)]
        super().__init__(rect.inflate(-40, -30), pts)
        self.rect = rect

    # Draws the rig; spin [rad] is the rim angle integrated from Omega.
    # belt_shift and belt_smear in drawing units (unloaded radii), spin and smear in rad, r_e_m [m] the unloaded radius.
    # values: numbers with units instead of the symbols.
    def draw(self, surface, out, delta: float, belt_shift: float, spin: float, f_z0: float,
             smear: float = 0.0, belt_smear: float = 0.0, r_e_m: float = 0.344, values: bool = False):
        name = lambda symbol, number: number if values else symbol
        h, r_e, half_w = 0.95, 1.0, 0.16
        clip = surface.get_clip()
        surface.set_clip(self.rect.inflate(4, 4))                      # the belt runs out of the panel
        ex = (math.cos(delta), math.sin(delta), 0.0)
        ey = (-math.sin(delta), math.cos(delta), 0.0)
        c = (0.0, 0.0, h)
        o = (0.0, 0.0, 0.0)

        belt = [self.p(v) for v in ((-3.2, -1.3, 0), (3.0, -1.3, 0), (3.0, 1.3, 0), (-3.2, 1.3, 0))]
        pygame.draw.polygon(surface, (42, 45, 51), belt)
        pygame.draw.polygon(surface, d.AXIS, belt, 1)
        step = BELT_STEP / r_e_m                                      # [units] stripe k at X = k step - shift, belt runs to -X
        first = math.ceil((belt_shift - 3.2) / step)
        for k in range(first, first + int(6.2 / step) + 2):
            x = k * step - belt_shift
            colour = MARK if k % MARK_EVERY == 0 else (61, 65, 72)
            if not -3.2 <= x <= 3.0:
                continue
            if belt_smear < 0.03:
                pygame.draw.line(surface, colour, self.p((x, -1.3, 0)), self.p((x, 1.3, 0)), 2 if k % MARK_EVERY == 0 else 1)
            else:
                x1 = min(x + belt_smear, 3.0)
                quad = [self.p((x, -1.3, 0)), self.p((x1, -1.3, 0)), self.p((x1, 1.3, 0)), self.p((x, 1.3, 0))]
                pygame.draw.polygon(surface, blur_colour((42, 45, 51), colour, belt_smear, 0.03, 0.15), quad)
        d.dashed(surface, (150, 100, 60), self.p((-3.2, 0, 0)), self.p((3.0, 0, 0)), 1, 6)

        front_sign = 1.0 if _dot(self.towards, ey) > 0 else -1.0
        leg, crown_z = 0.42, 2 * h + 0.3
        top = lambda s: _add(c, _mul(s * leg, ey), (0, 0, crown_z - h))
        bottom = lambda s: _add(c, _mul(s * leg, ey))
        fork = (170, 178, 192)
        pygame.draw.line(surface, fork, self.p(top(-front_sign)), self.p(bottom(-front_sign)), 6)
        pygame.draw.line(surface, fork, self.p(bottom(-front_sign)), self.p(c), 4)

        front = self.wheel(surface, c, ex, ey, spin, front_sign, r_e, half_w, smear)

        pygame.draw.line(surface, fork, self.p(front), self.p(bottom(front_sign)), 4)
        pygame.draw.line(surface, fork, self.p(top(front_sign)), self.p(bottom(front_sign)), 6)
        pygame.draw.line(surface, fork, self.p(top(-front_sign)), self.p(top(front_sign)), 6)
        pygame.draw.line(surface, fork, self.p(_add(c, (0, 0, crown_z - h))), self.p((0, 0, 2.55)), 7)
        sleeve = [self.p((0.11 * math.cos(2 * math.pi * i / 24), 0.11 * math.sin(2 * math.pi * i / 24), z))
                  for z in (2.55, 2.85) for i in range(24)]
        pygame.draw.polygon(surface, (61, 65, 72), _hull(sleeve))
        pygame.draw.polygon(surface, d.DIM, _hull(sleeve), 1)
        pygame.draw.line(surface, fork, self.p((0, 0, 2.85)), self.p((0, 0, 3.1)), 7)
        sp = self.p((0, 0, 2.7))
        pygame.draw.line(surface, d.DIM, (sp[0] - 8, sp[1]), (sp[0] - 34, sp[1]), 3)
        for j in range(4):
            pygame.draw.line(surface, d.DIM, (sp[0] - 34, sp[1] - 12 + 7 * j), (sp[0] - 42, sp[1] - 6 + 7 * j), 1)
        tip, tail = self.p((0, 0, 3.12)), self.p((0, 0, 3.75))        # P acts along the steering axis
        d.arrow(surface, d.LOAD, tail, tip, 4, 11)
        d.label(surface, name("P", f"{-out.r_hz:.0f} N"), (tail[0] + 10, tail[1]), d.LOAD, 15, backed=True)

        v = out.v_x * math.cos(delta) - out.v_y * math.sin(delta)
        scale_v = 2.6 / 25.0
        vx = _mul(out.v_x * scale_v, ex)
        vy = _mul(out.v_y * scale_v, ey)
        vv = (v * scale_v, 0.0, 0.0)
        if v > 0.05:
            d.dashed(surface, d.VELOCITY, self.p(vv), self.p(vx), 1, 4)
            d.dashed(surface, d.VELOCITY, self.p(vv), self.p(vy), 1, 4)
            self.arrow(surface, d.VELOCITY, o, vx, 2)
            self.arrow(surface, d.VELOCITY, o, vy, 2)
            self.arrow(surface, d.VELOCITY, o, vv, 3)
            d.label(surface, name("V", f"{v:.1f} m/s"), self.p(_mul(1.12, vv)), d.VELOCITY, 15, "c", backed=True)

        w = out.wheel
        k_f = 1.6 / f_z0
        self.arrow(surface, d.FORCE, o, _mul(w.f_x * k_f, ex), 4)
        self.arrow(surface, d.FORCE, o, _mul(w.f_y * k_f, ey), 4)
        self.arrow(surface, d.FORCE, o, (0, 0, out.f_z * 0.6 / f_z0), 4)
        d.label(surface, name("F_x", f"{w.f_x:.0f} N"), self.p(_add(_mul(w.f_x * k_f * 1.15, ex), (0, 0, 0.08))), d.FORCE, 14, "c", backed=True)
        d.label(surface, name("F_y", f"{w.f_y:.0f} N"), self.p(_add(_mul(w.f_y * k_f * 1.15, ey), (0, 0, 0.08))), d.FORCE, 14, "c", backed=True)
        d.label(surface, name("F_z", f"{out.f_z:.0f} N"), self.p((0.12, 0.0, out.f_z * 0.6 / f_z0 + 0.1)), d.FORCE, 14, "c", backed=True)

        rad = 1.6                                                     # delta from the belt direction to x, head at x
        pts = [self.p((rad * math.cos(delta * i / 20), rad * math.sin(delta * i / 20), 0)) for i in range(21)]
        if abs(delta) > math.radians(2.0):
            d.arc_line(surface, d.GEOMETRY, pts, 2, 9)
        mid = delta / 2
        d.label(surface, name("δ", f"{math.degrees(delta):+.1f}°"), self.p((1.85 * math.cos(mid), 1.85 * math.sin(mid), 0)), d.GEOMETRY, 15, "c", backed=True)
        surface.set_clip(clip)


# =============================================================================
# FREE-BODY DIAGRAM IN 3D
# The same wheel, still and seen in its own frame (x along, y axle, z up).
# Road on tyre at O, frame on wheel at the hub H, weight, net torque T.
# Arrow length proportional to the force; moments as arcs about their axis.
# =============================================================================

class Wheel3D(Projection):
    # Returns nothing; fits the wheel and the room for its arrows into rect.
    def __init__(self, rect: pygame.Rect):
        super().__init__(rect, [(x, y, z) for x in (-2.0, 2.0) for y in (-1.9, 1.9) for z in (-0.9, 2.9)],
                         math.radians(55.0), math.radians(24.0))     # lower than the rig view: vertical arrows readable

    # Draws the free-body diagram in the style of the rig view: the same wheel and ground, forces with the
    # same scale and weight, the name (or value) past the tip on a dark tag, moments as arcs of the same
    # weight; values: numbers instead of symbols. References [N m] set the drawn span of the moments.
    def draw(self, surface, out, t_net: float, weight: float, f_z0: float, t_ref: float, m_ref: float,
             values: bool = False):
        h = 0.95
        ex, ey, ez = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
        o, hub = (0.0, 0.0, 0.0), (0.0, 0.0, h)
        clip = surface.get_clip()
        surface.set_clip(self.rect.inflate(8, 8))
        ground = [self.p(v) for v in ((-1.9, -1.4, 0), (1.9, -1.4, 0), (1.9, 1.4, 0), (-1.9, 1.4, 0))]
        pygame.draw.polygon(surface, (42, 45, 51), ground)
        pygame.draw.polygon(surface, d.AXIS, ground, 1)
        front_sign = 1.0 if _dot(self.towards, ey) > 0 else -1.0
        self.wheel(surface, hub, ex, ey, 0.0, front_sign)                # the rig wheel, still
        d.dashed(surface, d.DIM, self.p(_add(hub, _mul(-0.3, ey))), self.p(_add(hub, _mul(0.3, ey))), 1, 4)   # axle: thin, dashed
        corner = (self.rect.x + 40, self.rect.bottom - 50)             # axes of the wheel frame, fixed on screen
        for axis, axis_name in ((ex, "x"), (ey, "y"), (ez, "z")):
            a, b = self.p((0, 0, 0)), self.p(axis)
            n = math.hypot(b[0] - a[0], b[1] - a[1])
            tip = (corner[0] + 36 * (b[0] - a[0]) / n, corner[1] + 36 * (b[1] - a[1]) / n)
            d.arrow(surface, d.DIM, corner, tip, 1, 7)
            d.label(surface, axis_name, (corner[0] + 48 * (b[0] - a[0]) / n, corner[1] + 48 * (b[1] - a[1]) / n), d.DIM, 12, "c")

        w = out.wheel
        k_f, k_v = 2.2 / f_z0, 1.1 / f_z0                            # [units/N] horizontal, vertical at half scale

        # force arrow from its point of application along vec, symbol or value past the tip; skipped below 2 px
        def force(colour, start, vec, symbol, value, width=4):
            if math.hypot(*vec) * self.k < 2.0:
                return
            self.arrow(surface, colour, start, vec, width)
            text = f"{value:.0f} N" if values else symbol
            d.label(surface, text, self.p(_add(start, _mul(1.15, vec), (0, 0, 0.08))), colour, 14, "c", backed=True)

        # moment arc about the axis u x v with its symbol or value next to the head
        def couple(colour, centre, u, v, radius, value, reference, symbol, a0=0.0):
            head = self.moment(surface, colour, centre, u, v, radius, value, reference, a0)
            if head is not None:
                d.label(surface, f"{value:.0f} N m" if values else symbol, (head[0] + 8, head[1] - 10), colour, 14, "ml",
                        backed=True)

        # road on tyre at O
        couple(d.MOMENT, o, ex, ey, 0.55, w.m_z, m_ref, "M_z", 0.3)
        couple(d.MOMENT, o, ez, ex, 0.32, w.m_y, 0.02 * t_ref, "M_y", 1.9)
        force(d.FORCE, o, _mul(w.f_x * k_f, ex), "F_x", w.f_x)
        force(d.FORCE, o, _mul(w.f_y * k_f, ey), "F_y", w.f_y)
        f_z = _mul(out.f_z * k_v, ez)
        if out.f_z * k_v * self.k >= 2.0:                               # head at O, from under the road
            self.arrow(surface, d.FORCE, _mul(-1.0, f_z), f_z, 4)
            d.label(surface, f"{out.f_z:.0f} N" if values else "F_z", self.p(_add(_mul(-1.12, f_z), (0.12, 0, 0))),
                    d.FORCE, 14, "c", backed=True)
        # frame on wheel at H, from H outwards. R_hy and R_hz are slid along their lines of action, which pass
        # through H, so they leave the wheel; moments are free vectors and sit where they read best
        couple(FRAME, _add(hub, (-1.35, 0, 0)), ey, ez, 0.35, out.m_hx, t_ref, "M_hx", 0.4)       # behind the tyre, on the x axis
        couple(FRAME, _add(hub, (0, 0, 1.25)), ex, ey, 0.3, out.m_hz, m_ref, "M_hz", 2.0)
        couple(d.T_DRIVE if t_net >= 0 else d.T_BRAKE, hub, ez, ex, 0.7, t_net, t_ref, "T = T_D − T_B", 0.4)
        force(FRAME, hub, (out.r_hx * k_f, 0, 0), "R_hx", out.r_hx)                 # at H: its line passes through H
        end = _mul(math.copysign(0.45, out.r_hy), ey)                 # the axle end it points away from
        force(FRAME, _add(hub, end), (0, out.r_hy * k_f, 0), "R_hy", out.r_hy)
        force(FRAME, _add(hub, (0, 0, 1.1 - out.r_hz * k_v)), (0, 0, out.r_hz * k_v), "R_hz", out.r_hz)   # head above the tyre
        # weight at H, downwards; drawn at least 0.4 units long, else it would be a few pixels (not to scale)
        w_len = max(weight * k_v, 0.4)
        self.arrow(surface, d.LOAD, hub, (0, 0, -w_len), 4)
        w_tip = self.p(_add(hub, (0, 0, -w_len)))                       # name beside the tip, clear of H and of M_y
        d.label(surface, f"{weight:.0f} N" if values else "m_w g", (w_tip[0] - 10, w_tip[1]), d.LOAD, 14, "mr",
                backed=True)
        pygame.draw.circle(surface, d.TEXT, self.p(hub), 4)
        pygame.draw.circle(surface, d.TEXT, self.p(o), 4)
        d.label(surface, "H", (self.p(hub)[0] - 10, self.p(hub)[1] + 6), d.TEXT, 14, "tr", backed=True)
        d.label(surface, "O", (self.p(o)[0] - 10, self.p(o)[1] + 4), d.TEXT, 14, "tr", backed=True)
        surface.set_clip(clip)


# =============================================================================
# READOUT ROW
# Three values at the bottom of a panel: left, centre and right. Each slot is
# as wide as its widest expected text, so the labels do not move.
# =============================================================================

# Draws (name, value, widest value) items at the bottom of rect: left, centred, right.
def readout_row(surface, rect: pygame.Rect, items):
    y = rect.bottom - 22
    for i, (name, value, widest) in enumerate(items):
        width = d.label_width(name + " ", 13) + d.label_width(widest, 13)
        x = (rect.x + 12, rect.centerx - width / 2, rect.right - 12 - width)[i]
        r = d.label(surface, name + " ", (x, y), d.DIM, 13)
        d.label(surface, value, (r.right, y), d.TEXT, 13)


# =============================================================================
# SIDE VIEW
# x to the left, z up (De Felice). Hub at a fixed point; road at depth h.
# =============================================================================

# Returns the scale [px/m] of the side and top views for a side panel of height [px].
def side_scale(height: float, r_e: float) -> float:
    return 0.30 * height / r_e


# Returns the patch half-length estimate [m], sqrt(2 R_e rho) with rho = R_e - h (report fig. trail).
def patch_half_length(r_e: float, h: float) -> float:
    return math.sqrt(2.0 * r_e * (r_e - h))

# Draws the side view: wheel, spin, torques, C, F_x, F_z and the patch.
def side_view(surface, rect: pygame.Rect, out, omega: float, t_d: float, t_b: float, k_spring: float,
              h: float, r_0: float, r_e: float, belt_shift: float, spin: float, f_z0: float,
              smear: float = 0.0, belt_smear: float = 0.0, values: bool = False):
    name = lambda symbol, number: number if values else symbol
    d.panel(surface, rect)
    d.label(surface, "side", (rect.x + 10, rect.y + 6), d.DIM, 13)
    scale = side_scale(rect.h, r_e)                                  # [px/m]
    top, bottom = rect.y + 24, rect.bottom - 30                      # free height between title and readout
    hub = (rect.centerx, 0.5 * (top + bottom) - 0.5 * (h - r_e) * scale)   # wheel centred vertically
    road_y = hub[1] + h * scale
    clip = surface.get_clip()
    surface.set_clip(rect.inflate(-2, -2))

    pygame.draw.line(surface, d.AXIS, (rect.x + 6, road_y), (rect.right - 6, road_y), 1)
    pygame.draw.circle(surface, d.TYRE, hub, int(r_e * scale))
    pygame.draw.circle(surface, d.DIM, hub, int(r_e * scale), 1)
    pygame.draw.circle(surface, d.RIM, hub, int(0.42 * r_e * scale))
    smear = max(min(smear, 2 * math.pi), -2 * math.pi)
    at = lambda a, r: (hub[0] + r * scale * math.cos(a), hub[1] - r * scale * math.sin(a))
    sector = lambda a, r0, r1: [at(a - smear * i / 12, r1) for i in range(13)] + [at(a - smear * (12 - i) / 12, r0) for i in range(13)]
    for k in range(SPOKES):
        a = spin + 2 * math.pi * k / SPOKES
        if abs(smear) < 0.06:
            pygame.draw.line(surface, (110, 115, 125), hub, at(a, 0.40 * r_e), 2)
        else:
            pygame.draw.polygon(surface, blur_colour(d.RIM, (110, 115, 125), abs(smear), 0.06), sector(a, 0.02, 0.40 * r_e))
    if abs(smear) < 0.06:
        pygame.draw.line(surface, MARK, at(spin, 0.6 * r_e), at(spin, 0.97 * r_e), 3)
    else:
        pygame.draw.polygon(surface, blur_colour(d.TYRE, MARK, abs(smear), 0.06, 0.1), sector(spin, 0.6 * r_e, 0.97 * r_e))
    pygame.draw.circle(surface, d.TEXT, hub, 3)

    w = out.wheel
    patch = (hub[0], road_y)
    u_x = w.f_x / k_spring                                           # [m] physical carcass deflection
    off = -u_x * DEFLECTION_SCALE * scale                            # x to the left on screen
    a = patch_half_length(r_e, h) * scale
    pygame.draw.line(surface, d.PATCH, (patch[0] - a + off, road_y), (patch[0] + a + off, road_y), 3)     # on the road, thin

    # velocities along the vertical through the hub, one scale: V_x at the hub, zero at C, V_sx at C_0;
    # the three tips lie on one line (report 3.3-3.4). Labels are collected and drawn last, on dark tags.
    labels = []                                                      # (text, position, colour, anchor)
    k_v = 0.35 * rect.w / 30.0                                       # [px per m/s]
    tip = (hub[0] - out.v_x * k_v, hub[1])
    d.arrow(surface, d.VELOCITY, hub, tip, 3)
    labels.append((name("V_x", f"{out.v_x:.1f} m/s"), (tip[0] - 4, tip[1] - 24), d.VELOCITY, "tr" if out.v_x >= 0 else "tl"))
    c0_y = hub[1] + r_0 * scale                                      # C_0, the point of the tyre at depth R_0
    slip_tip = (hub[0] - w.v_sx * k_v, c0_y)
    c_point = None
    if omega != 0.0 and abs(out.v_x / omega) < 3.0 * r_e:
        c_point = (hub[0], hub[1] + out.v_x / omega * scale)
    end = c_point if c_point is not None and c_point[1] > c0_y else slip_tip   # braked: the line goes on to C
    if abs(out.v_x) * k_v > 2.0 or abs(w.v_sx) * k_v > 2.0:
        d.dashed(surface, d.VELOCITY, tip, end, 1, 4)

    if abs(omega) > 0.05:
        span = min(abs(omega) / 60.0, 1.0) * 1.6 + 0.3
        a0 = math.pi / 2
        d.arc_arrow(surface, d.GEOMETRY, hub, 0.62 * r_e * scale, a0, a0 + (span if omega > 0 else -span), 3)
        labels.append((name("Ω", f"{omega:+.1f} rad/s"), (hub[0] - 0.62 * r_e * scale - 6, hub[1] - 0.62 * r_e * scale - 6),
                       d.GEOMETRY, "tr"))
    elif omega == 0.0:
        text = "Ω = 0 · locked" if out.v_x != 0.0 or out.v_y != 0.0 else "Ω = 0"
        d.label(surface, text, (rect.x + 52, rect.y + 6), d.WARNING, 13)
    # drive torque along positive spin, brake torque against the spin: two arcs, two colours
    for value, sign, radius, colour, symbol in ((t_d, 1.0, 0.50, d.T_DRIVE, "T_D"),
                                                (t_b, -1.0 if omega >= 0 else 1.0, 0.34, d.T_BRAKE, "T_B")):
        if value > 5.0:
            span = min(value / 1500.0, 1.0) * 2.4 + 0.4
            a0 = -math.pi / 2
            d.arc_arrow(surface, colour, hub, radius * r_e * scale, a0, a0 + sign * span, 3)
            a1 = a0 + sign * span
            labels.append((name(symbol, f"{value:.0f} N m"), (hub[0] + (radius + 0.16) * r_e * scale * math.cos(a1),
                                                              hub[1] - (radius + 0.16) * r_e * scale * math.sin(a1)), colour, "c"))

    k_f = 0.45 * rect.w / f_z0                                       # [px/N]
    f_tip = (patch[0] - 6, patch[1] - out.f_z * k_f * 0.5)           # F_z at half scale, up into the tyre
    d.arrow(surface, d.FORCE, (patch[0] - 6, patch[1]), f_tip, 4)
    labels.append((name("F_z", f"{out.f_z:.0f} N"), (f_tip[0] - 8, f_tip[1] + 4), d.FORCE, "mr"))
    if abs(w.v_sx) * k_v > 2.0:                                      # slip velocity of C_0, same scale as V_x
        d.arrow(surface, d.VELOCITY, (hub[0], c0_y), slip_tip, 3)
    if abs(w.v_sx) * k_v > 0.5:                                      # below the road, on the side of its tip
        labels.append((name("V_sx", f"{w.v_sx:+.2f} m/s"), (slip_tip[0], road_y + 26), d.VELOCITY,
                       "tr" if w.v_sx > 0 else "tl"))
    line = (patch[0], road_y + 12)                                   # F_x below the road, opposite to V_sx
    if abs(w.f_x) * k_f > 2.0:
        f_end = (line[0] - w.f_x * k_f, line[1])
        d.arrow(surface, d.FORCE, line, f_end, 4)
        labels.append((name("F_x", f"{w.f_x:.0f} N"), (f_end[0], road_y + 26), d.FORCE, "tr" if w.f_x > 0 else "tl"))
    if c_point is not None:
        pygame.draw.circle(surface, d.GEOMETRY, c_point, 5)                 # notable point: white
        labels.append(("C", (hub[0] + 9, c_point[1]), d.GEOMETRY, "ml"))
    for text, pos, colour, anchor in labels:
        d.label(surface, text, pos, colour, 13, anchor, backed=True)
    surface.set_clip(clip)

    radius = "–" if math.isnan(out.radius) else f"{out.radius:.3f} m"
    readout_row(surface, rect, (("R", radius, "0.000 m"), ("M_y", f"{w.m_y:.0f} N m", "−00 N m"),
                                ("u_x", f"{u_x * 1000:+.1f} mm", "+00.0 mm")))


# =============================================================================
# TOP VIEW, FIXED TO THE BELT
# x to the left, y down; the belt direction e_r points left, the belt runs right.
# =============================================================================

# Draws the top view fixed to the belt: wheel, V, delta, F_x, F_y at the trail; scale [px/m].
def top_view(surface, rect: pygame.Rect, out, delta: float, k_spring: float, r_e: float,
             belt_shift: float, f_z0: float, belt_smear: float = 0.0, scale: float = 300.0, values: bool = False):
    name = lambda symbol, number: number if values else symbol
    d.panel(surface, rect)
    d.label(surface, "top", (rect.x + 10, rect.y + 6), d.DIM, 13)
    o = (rect.centerx, rect.y + 0.47 * rect.h)
    clip = surface.get_clip()
    surface.set_clip(rect.inflate(-2, -2))

    # world (X along e_r, Y to its left) -> screen (X left, Y down)
    sc = lambda X, Y: (o[0] - X * scale, o[1] + Y * scale)
    ex = (math.cos(delta), math.sin(delta))
    ey = (-math.sin(delta), math.cos(delta))
    wp = lambda a, b: sc(a * ex[0] + b * ey[0], a * ex[1] + b * ey[1])
    half_l, half_w = r_e, 0.11
    pygame.draw.polygon(surface, d.TYRE, [wp(-half_l, -half_w), wp(half_l, -half_w), wp(half_l, half_w), wp(-half_l, half_w)])
    pygame.draw.polygon(surface, d.DIM, [wp(-half_l, -half_w), wp(half_l, -half_w), wp(half_l, half_w), wp(-half_l, half_w)], 1)
    d.dashed(surface, d.AXIS, wp(-1.6, 0), wp(1.6, 0), 1, 5)

    w = out.wheel
    u_x, u_y = w.f_x / k_spring, w.f_y / k_spring
    k = DEFLECTION_SCALE
    pygame.draw.polygon(surface, d.PATCH, [wp(-0.12 + k * u_x, -0.07 + k * u_y), wp(0.12 + k * u_x, -0.07 + k * u_y),
                                             wp(0.12 + k * u_x, 0.07 + k * u_y), wp(-0.12 + k * u_x, 0.07 + k * u_y)], 1)

    labels = []                                                      # drawn last, on dark tags
    v = math.hypot(out.v_x, out.v_y)
    k_v = 0.35 * rect.w / 30.0
    if v > 0.05:
        d.arrow(surface, d.VELOCITY, o, (o[0] - v * k_v, o[1]), 3)
        labels.append((name("V", f"{v:.1f} m/s"), (o[0] - v * k_v - 6, o[1] - 12), d.VELOCITY, "mr"))
    r_arc = 0.75 * r_e * scale                                       # delta from the belt direction to x, head at x
    if abs(delta) > math.radians(2.0):
        pts = [(o[0] - r_arc * math.cos(delta * i / 16), o[1] + r_arc * math.sin(delta * i / 16)) for i in range(17)]
        d.arc_line(surface, d.GEOMETRY, pts, 2, 9)
        mid = delta / 2
        labels.append((name("δ", f"{math.degrees(delta):+.1f}°"),
                       (o[0] - (r_arc + 20) * math.cos(mid), o[1] + (r_arc + 20) * math.sin(mid)), d.GEOMETRY, "c"))

    k_f = 0.45 * rect.w / f_z0
    t = w.trail
    at = wp(-t * 4.0, 0)                                             # trail drawn x4 to be visible
    f_y_end = (at[0] - w.f_y * k_f * ey[0], at[1] + w.f_y * k_f * ey[1])
    f_x_end = (o[0] - w.f_x * k_f * ex[0], o[1] + w.f_x * k_f * ex[1])
    if abs(w.f_y) * k_f > 2.0:
        d.arrow(surface, d.FORCE, at, f_y_end, 4)
        labels.append((name("F_y", f"{w.f_y:.0f} N"), (f_y_end[0] + 8, f_y_end[1] + 6), d.FORCE, "tl"))
    if abs(w.f_x) * k_f > 2.0:
        d.arrow(surface, d.FORCE, o, f_x_end, 4)
        labels.append((name("F_x", f"{w.f_x:.0f} N"), (f_x_end[0], f_x_end[1] + 10), d.FORCE, "c"))
    pygame.draw.circle(surface, d.TEXT, o, 3)
    for text, pos, colour, anchor in labels:
        d.label(surface, text, pos, colour, 13, anchor, backed=True)
    surface.set_clip(clip)

    readout_row(surface, rect, (("t", f"{t * 1000:.1f} mm", "00.0 mm"), ("M_z", f"{w.m_z:.0f} N m", "−00 N m"),
                                ("u_y", f"{u_y * 1000:+.1f} mm", "+00.0 mm")))


# =============================================================================
# CONTACT ZOOM, SIDE
# The side view enlarged at the patch, true scale: the unloaded tyre crossing
# the road, the patch displaced by u_x, C_0 on the rim with its slip velocity
# V_sx and the force F_x, which opposes it.
# =============================================================================

ZOOM = 1300.0               # [px/m] scale of the contact zoom
K_SLIP = 80.0               # [px per m/s] drawn length of the slip velocity


# Draws the side view enlarged at the patch, true scale (the side panel with zoom on).
def contact_zoom(surface, rect: pygame.Rect, out, k_spring: float, h: float, r_0: float, r_e: float, f_z0: float):
    d.panel(surface, rect)
    clip = surface.get_clip()
    surface.set_clip(rect.inflate(-2, -2))
    road_y = rect.y + 0.60 * rect.h
    hub = (rect.centerx, road_y - h * ZOOM)                          # far above the panel
    pygame.draw.rect(surface, (42, 45, 51), (rect.x, road_y, rect.w, rect.bottom - road_y))
    pygame.draw.circle(surface, d.TYRE, hub, int(r_e * ZOOM))
    pygame.draw.rect(surface, (42, 45, 51), (rect.x, road_y + 1, rect.w, rect.bottom - road_y))
    pygame.draw.circle(surface, d.DIM, hub, int(r_e * ZOOM), 1)    # unloaded tyre, crossing the road
    pygame.draw.line(surface, d.AXIS, (rect.x, road_y), (rect.right, road_y), 1)
    d.dashed(surface, d.AXIS, (hub[0], rect.y + 24), (hub[0], rect.bottom - 30), 1, 4)

    w = out.wheel
    u_x = w.f_x / k_spring                                           # [m] carcass deflection
    a = patch_half_length(r_e, h)
    pygame.draw.line(surface, d.PATCH, (hub[0] - (a + u_x) * ZOOM, road_y - 2), (hub[0] + (a - u_x) * ZOOM, road_y - 2), 5)

    c0 = (hub[0], hub[1] + r_0 * ZOOM)                               # point of the rim at R_0 below the hub
    v_len = min(abs(w.v_sx) * K_SLIP, 0.45 * rect.w)                 # [px]
    f_len = min(abs(w.f_x) * 0.30 * rect.w / f_z0, 0.45 * rect.w)    # [px]
    if v_len > 1.0:                                                  # slip velocity of C_0, x to the left
        tip = (c0[0] - math.copysign(v_len, w.v_sx), c0[1])
        d.arrow(surface, d.VELOCITY, c0, tip, 3)
        d.label(surface, "V_sx", (tip[0], c0[1] + 16), d.VELOCITY, 13, "c", backed=True)
    if f_len > 1.0:                                                  # road force on the tyre, against V_sx
        tip = (c0[0] - math.copysign(f_len, w.f_x), c0[1])
        d.arrow(surface, d.FORCE, c0, tip, 4)
        d.label(surface, "F_x", (tip[0], c0[1] + 16), d.FORCE, 13, "c", backed=True)
    pygame.draw.circle(surface, d.TEXT, c0, 4, 1)
    d.label(surface, "C_0", (c0[0], c0[1] + 16), d.TEXT, 13, "c")
    surface.set_clip(clip)
    d.label(surface, "contact", (rect.x + 10, rect.y + 6), d.DIM, 13)                    # over the tyre

    readout_row(surface, rect, (("V_sx", f"{w.v_sx:+.2f} m/s", "+00.00 m/s"), ("u_x", f"{u_x * 1000:+.1f} mm", "+00.0 mm"),
                                ("patch", f"{2000 * a:.0f} mm", "000 mm")))
