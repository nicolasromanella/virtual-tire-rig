# =============================================================================
# RIGHT PANEL
# Three views selected in the top bar: Plots (tyre curves with the current
# operating point), Transient (Maxwell element live, report ch. 6) and Forces
# (3D free-body diagram and load cell, report ch. 5). Curves from rig.tyre.
# =============================================================================

import math

import pygame

from interface import draw as d
from interface.views import FRAME, ORBIT_HINT, Wheel3D
from interface.widgets import Button, Slider, Switch
from rig.tyre import TyreAtLoad, characteristic, peak_slip, trail

DEG = math.pi / 180.0


# Returns about n round tick values covering lo..hi.
def ticks(lo: float, hi: float, n: int = 5) -> list:
    raw = (hi - lo) / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    first = math.ceil(lo / step - 1e-9) * step
    return [round(first + i * step, 10) for i in range(int((hi - first) / step + 1e-9) + 1)]


# =============================================================================
# AXES
# Maps data to pixels inside a panel; draws grid, ticks, the y name with its
# unit above the axis on the left and the x name with its unit below.
# =============================================================================

class Axes:
    # Returns nothing; plot area inside rect for the data ranges (lo, hi).
    def __init__(self, rect: pygame.Rect, x_range, y_range):
        self.cell = rect
        self.rect = pygame.Rect(rect.x + 50, rect.y + 36, rect.w - 100, rect.h - 82)   # centred in the panel
        self.x0, self.x1 = x_range
        self.y0, self.y1 = y_range

    # Returns the pixel point of the data point (x, y), clamped to the plot area.
    def to(self, x: float, y: float):
        px = self.rect.x + (x - self.x0) / (self.x1 - self.x0) * self.rect.w
        py = self.rect.bottom - (y - self.y0) / (self.y1 - self.y0) * self.rect.h
        return (min(max(px, self.rect.x), self.rect.right), min(max(py, self.rect.y), self.rect.bottom))

    # Draws grid lines at the ticks, their labels and the axis names.
    def frame(self, surface, x_ticks, y_ticks, x_name: str = "", y_name: str = "", x_fmt="{:g}", y_fmt="{:g}"):
        for x in x_ticks:
            px, _ = self.to(x, self.y0)
            pygame.draw.line(surface, d.GRID, (px, self.rect.y), (px, self.rect.bottom), 1)
            d.label(surface, x_fmt.format(x), (px, self.rect.bottom + 12), d.DIM, 11, "c")
        for y in y_ticks:
            _, py = self.to(self.x0, y)
            pygame.draw.line(surface, d.GRID, (self.rect.x, py), (self.rect.right, py), 1)
            d.label(surface, y_fmt.format(y), (self.rect.x - 6, py), d.DIM, 11, "mr")
        if self.y0 < 0 < self.y1:
            _, py = self.to(self.x0, 0)
            pygame.draw.line(surface, d.AXIS, (self.rect.x, py), (self.rect.right, py), 1)
        if self.x0 < 0 < self.x1:
            px, _ = self.to(0, self.y0)
            pygame.draw.line(surface, d.AXIS, (px, self.rect.y), (px, self.rect.bottom), 1)
        pygame.draw.rect(surface, d.AXIS, self.rect, 1)
        if y_name:
            d.label(surface, "↑ " + y_name, (self.cell.x + 12, self.cell.y + 9), d.TEXT, 13)
        if x_name:
            d.label(surface, x_name + " →", (self.rect.centerx, self.rect.bottom + 32), d.TEXT, 13, "c")

    # Returns pixel points of a list of (x, y), dropping points outside the range.
    def line(self, points):
        return [self.to(x, y) for x, y in points
                if self.y0 - 1e-9 <= y <= self.y1 + 1e-9 and self.x0 - 1e-9 <= x <= self.x1 + 1e-9]

    # Draws the operating point; outside the range it stops on the edge with an arrow pointing outwards.
    def point(self, surface, x: float, y: float, hollow: bool = False):
        if not (math.isfinite(x) and math.isfinite(y)):
            return
        p = self.to(x, y)
        pygame.draw.circle(surface, d.POINT, p, 5, 2 if hollow else 0)
        dx = -1 if x < self.x0 else (1 if x > self.x1 else 0)
        dy = 1 if y < self.y0 else (-1 if y > self.y1 else 0)
        if dx or dy:
            n = math.hypot(dx, dy)
            d.arrow(surface, d.POINT, (p[0] + 7 * dx / n, p[1] + 7 * dy / n), (p[0] + 22 * dx / n, p[1] + 22 * dy / n), 2, 8)

    # Draws a range slider with its label, centred in the header of the cell.
    def header_slider(self, surface, slider, text: str):
        w = d.label_width(text, 12) + 8 + 140
        x = self.cell.centerx - w / 2
        r = d.label(surface, text, (x, self.cell.y + 10), d.DIM, 12)
        slider.draw(surface, pygame.Rect(r.right + 8, self.cell.y + 11, 140, 14), d.AXIS)

    # Draws a text centred in the header of the cell.
    def header_text(self, surface, text: str, colour):
        d.label(surface, text, (self.cell.centerx, self.cell.y + 18), colour, 13, "c")


    # Draws a legend in the top-right corner of the plot area: items of (name, colour, style),
    # style "line", "dashed" or "ring" (an open circle, for marked points).
    def legend(self, surface, items, left: bool = False):
        y = self.rect.y + 6
        for name, colour, style in items:
            if left:                                                 # line first, then the name
                r = d.label(surface, name, (self.rect.x + 42, y), d.TEXT, 12)
                a, b = (self.rect.x + 10, y + 8), (self.rect.x + 32, y + 8)
            else:
                r = d.label(surface, name, (self.rect.right - 8, y), d.TEXT, 12, "tr")
                a, b = (r.x - 30, y + 8), (r.x - 8, y + 8)
            if style == "line":
                pygame.draw.line(surface, colour, a, b, 2)
            elif style == "dashed":
                d.dashed(surface, colour, a, b, 2, 4)
            else:
                pygame.draw.circle(surface, colour, (r.x - 14, y + 8), 5, 2)
            y += 18

    # Writes brake on the bottom left and drive on the bottom right of the plot area.
    def sides(self, surface, left: str = "← brake", right: str = "drive →"):
        d.label(surface, left, (self.rect.x + 6, self.rect.bottom - 20), d.DIM, 11)
        d.label(surface, right, (self.rect.right - 6, self.rect.bottom - 20), d.DIM, 11, "tr")


# Draws every other segment of a polyline.
def _dashed_line(surface, colour, points, width=2):
    for a, b in zip(points[::2], points[1::2]):
        pygame.draw.line(surface, colour, a, b, width)


# =============================================================================
# PLOTS VIEW
# Slip indices, characteristic in s / sigma raw / sigma adjusted, combined
# slip, aligning moment or trail against alpha with adjustable range.
# =============================================================================

class PlotsView:
    # Returns nothing; switches and range sliders of the four plots.
    def __init__(self):
        self.axis = Switch(["s", "σ", "α"], "s")                     # characteristic in s or sigma, or F_y(alpha)
        self.polar = Switch(["α", "σ_y"], "α")
        self.mz = Switch(["M_z", "t"], "M_z")
        self.ratio_range = Slider(2.0, 10.0, 3.0)                    # [-]   largest Omega R_0 / V_x shown
        self.slip_range = Slider(0.2, 5.0, 1.0)                      # [-]   largest |s| or |sigma| shown
        self.lateral_range = Slider(5.0, 90.0, 20.0)                 # [deg] largest alpha of F_y(alpha)
        self.alpha_range = Slider(10.0, 180.0, 20.0)                 # [deg] half range of the M_z plot
        self.cache_key, self.cache = None, {}

    # Returns True if the click changed a switch of the plots.
    def click(self, point) -> bool:
        return self.axis.click(point) or self.polar.click(point) or self.mz.click(point)

    # Returns the range sliders of the plots.
    def sliders(self) -> list:
        return [self.ratio_range, self.lateral_range if self.axis.selected == "α" else self.slip_range, self.alpha_range]

    # Returns the cached curves for the tyre at its current load.
    def curves(self, k: TyreAtLoad) -> dict:
        key = round(k.f_z)
        if key == self.cache_key:
            return self.cache
        f = lambda m: characteristic(abs(m), k) / k.f_z
        c = {}
        grid = [5.0 * (i / 1000) ** 1.5 for i in range(1001)]          # [-] slip magnitude, dense near 0
        # one tyre, F_t(|s|) (report 4.3); in sigma the same tyre is F_t(|sigma| / (1 + sigma_x)), drawn live
        c["s"] = [(m, f(m)) for m in grid]
        c["grid"] = grid
        angles = [-179.75 + 359.5 * i / 1438 for i in range(1439)]    # whole turn; never exactly +-90 deg
        # steady pure side slip at any alpha: F_y = F_t(|tan alpha|) sign(sin alpha), also rolling backward (report 4.5)
        c["mz"] = [(a, -trail(a * DEG, k) * characteristic(abs(math.tan(a * DEG)), k) * (1 if math.sin(a * DEG) >= 0 else -1))
                   for a in angles]
        c["t"] = [(a, trail(a * DEG, k) * 1000) for a in angles]
        c["mu_0"], c["mu_1"] = k.mu_0, k.mu_1
        self.cache_key, self.cache, self.cache_k = key, c, k
        return c

    # Draws the four plots in rect.
    def draw(self, surface, rect: pygame.Rect, out, q, r_0: float, k: TyreAtLoad):
        c = self.curves(k)
        w, h = (rect.w - 10) // 2, (rect.h - 10) // 2
        cells = [pygame.Rect(rect.x, rect.y, w, h), pygame.Rect(rect.x + w + 10, rect.y, w, h),
                 pygame.Rect(rect.x, rect.y + h + 10, w, h), pygame.Rect(rect.x + w + 10, rect.y + h + 10, w, h)]
        for cell in cells:
            d.panel(surface, cell)
        self.slip(surface, cells[0], out, q, r_0)
        self.characteristic(surface, cells[1], out, c, k)
        self.combined(surface, cells[2], out, c)
        self.aligning(surface, cells[3], out, c)

    # Draws the slip indices against Omega R_0 / V_x.
    def slip(self, surface, cell, out, q, r_0):
        x_max = self.ratio_range.value
        top = x_max - 1                                              # s_x reaches -top at the right end
        ax = Axes(cell, (0, x_max), (-top - 0.6, top + 0.6))         # margin so the labels clear the line
        ax.frame(surface, ticks(0, x_max, 5), ticks(-top - 0.6, top + 0.6, 5), "Ω R_0 / V_x [-]", "slip [-]")
        n = 600
        xs = [x_max * i / n for i in range(n + 1)]
        d.polyline(surface, d.CURVE, ax.line([(r, 1 - r) for r in xs]))
        d.polyline(surface, d.F_X, ax.line([(r, 1 / r - 1) for r in xs if r > 1e-3]))   # branch Omega R_0 / V_x > 0
        ax.legend(surface, [("s_x", d.CURVE, "line"), ("σ_x", d.F_X, "line")])
        ax.sides(surface)
        ax.header_slider(surface, self.ratio_range, f"range {x_max:.1f}")
        if abs(out.v_x) > 1e-6:
            ratio = q.omega * r_0 / out.v_x
            ax.point(surface, ratio, 1 - ratio)                      # on s_x
            if ratio > 0.0:
                ax.point(surface, ratio, 1 / ratio - 1)              # on sigma_x

    # F_t / F_z of the one tyre law against s or sigma. The point is the slip the tyre sees, tau* (report 6.4),
    # so it always lies on the curve. In sigma the curve depends on the slip direction, s = sigma / (1 + sigma_x):
    # it is drawn for the current direction, with braking and driving at alpha = 0 as faint references.
    def characteristic(self, surface, cell, out, c, k):
        self.axis.draw(surface, (cell.right - 10 - self.axis.width(), cell.y + 6))
        if self.axis.selected == "α":
            return self.lateral(surface, cell, out, c, k)
        use_s = self.axis.selected == "s"
        m_max = self.slip_range.value
        ax = Axes(cell, (0, m_max), (0, 1.45))
        ax.frame(surface, ticks(0, m_max, 5), [0, 0.5, 1], "‖s‖ [-]" if use_s else "‖σ‖ [-]", "F_t / F_z [-]")
        _, y1 = ax.to(0, c["mu_1"])
        d.dashed(surface, d.DIM, (ax.rect.x, y1), (ax.rect.right, y1), 1, 3)
        d.label(surface, "μ_1", (ax.rect.right - 6, y1 + 3), d.DIM, 11, "tr")
        f_t = math.hypot(out.wheel.f_x, out.wheel.f_y) / out.f_z
        tx, ty = out.wheel.tau_star_x, out.wheel.tau_star_y
        if use_s:
            d.polyline(surface, d.CURVE, ax.line(c["s"]))
            if ax.x0 < 1 < ax.x1:
                px, _ = ax.to(1, 0)
                d.dashed(surface, d.DIM, (px, ax.rect.y), (px, ax.rect.bottom), 1, 3)
                d.label(surface, "locked, α = 0", (px - 4, ax.rect.bottom - 20), d.DIM, 11, "tr")
            s_p = peak_slip(k)
            pygame.draw.circle(surface, d.WARNING, ax.to(s_p, characteristic(s_p, k) / k.f_z), 5, 2)   # peak, same size as the operating point
            ax.point(surface, math.hypot(tx, ty), f_t)
            return self.range_and_note(surface, ax, m_max, [("F_t", d.CURVE, "line")])
        if tx < 1.0:
            sx, sy = tx / (1 - tx), ty / (1 - tx)                     # sigma = s / (1 - s_x), s = tau*
            m = math.hypot(sx, sy)
            cos_t = sx / m if m > 0 else 1.0
            live = [(g, characteristic(g / (1 + g * cos_t), k) / k.f_z) for g in c["grid"] if 1 + g * cos_t > 1e-3]
            d.polyline(surface, d.CURVE_SIGMA, ax.line(live))
            s_p = peak_slip(k)
            if 1 - s_p * cos_t > 0:                                   # peak where |sigma| / (1 + sigma_x) = s_p
                m_p = s_p / (1 - s_p * cos_t)
                pygame.draw.circle(surface, d.WARNING, ax.to(m_p, characteristic(s_p, k) / k.f_z), 5, 2)
            ax.point(surface, m, f_t)
        else:
            ax.point(surface, 1e9, f_t)                               # locked: sigma infinite, arrow at the edge
        self.range_and_note(surface, ax, m_max, [("F_t", d.CURVE_SIGMA, "line")])

    # F_y / F_z against the slip angle, positive side only as the other two modes (report 4.5), at the
    # longitudinal slip the tyre sees now, tau*_x; the peak ring moves with it, at |s| = s_p. As in the
    # other two modes the point is the slip the tyre sees: alpha' = atan|tau*_y|, equal to the kinematic
    # alpha in steady state, so the point lies on the curve at every instant, also in a transient.
    def lateral(self, surface, cell, out, c, k):
        span = self.lateral_range.value                               # [deg]
        ax = Axes(cell, (0.0, span), (0.0, 1.45))
        step = next(st for st in (2, 5, 10, 15, 30) if span / st <= 6)
        ax.frame(surface, [i * step for i in range(int(span // step) + 1)], [0, 0.5, 1], "α [°]", "F_y / F_z [-]",
                 x_fmt="{:g}°")
        _, y1 = ax.to(0, c["mu_1"])
        d.dashed(surface, d.DIM, (ax.rect.x, y1), (ax.rect.right, y1), 1, 3)
        d.label(surface, "μ_1", (ax.rect.right - 6, y1 + 3), d.DIM, 11, "tr")
        tx = out.wheel.tau_star_x
        live = []
        for i in range(401):
            a = span * i / 400
            s_y = math.tan(a * DEG)
            m = math.hypot(tx, s_y)
            live.append((a, characteristic(m, k) * s_y / m / k.f_z if m > 0 else 0.0))
        d.polyline(surface, d.CURVE_ALPHA, ax.line(live))
        s_p = peak_slip(k)
        if abs(tx) < s_p:                                             # peak where |(tau*_x, tan alpha)| = s_p
            t_p = math.sqrt(s_p ** 2 - tx ** 2)
            a_p = math.degrees(math.atan(t_p))
            if a_p <= span:
                pygame.draw.circle(surface, d.WARNING, ax.to(a_p, characteristic(s_p, k) * t_p / s_p / k.f_z), 5, 2)
        ax.legend(surface, [("F_y", d.CURVE_ALPHA, "line")])
        d.label(surface, f"τ*_x = {tx:+.2f}", (ax.rect.right - 6, ax.rect.y + 26), d.DIM, 11, "tr")
        ax.header_slider(surface, self.lateral_range, f"α 0–{span:.0f}°")
        ty = out.wheel.tau_star_y
        ax.point(surface, math.degrees(math.atan(abs(ty))), abs(out.wheel.f_y) / out.f_z)   # alpha', |F_y|

    # Draws the legend and the range slider of a characteristic plot.
    def range_and_note(self, surface, ax, m_max, items):
        ax.legend(surface, items)
        ax.header_slider(surface, self.slip_range, f"range {m_max:.1f}")

    # Polar diagram of the current lateral slip only: tau*_y (alpha mode) or sigma_y (sigma mode) held at the
    # value the tyre sees now, longitudinal slip swept, so the point lies on the curve also in a transient.
    # Red dots: where the curve touches the friction circle mu_0, |s| = s_p.
    def combined(self, surface, cell, out, c):
        self.polar.draw(surface, (cell.right - self.polar.width() - 10, cell.y + 6))
        ax = Axes(cell, (-1.25, 1.25), (-1.25, 1.25))
        ax.frame(surface, [-1, -0.5, 0, 0.5, 1], [-1, -0.5, 0, 0.5, 1], "F_x / F_z [-]", "F_y / F_z [-]")
        for mu, colour in ((c["mu_0"], d.DIM), (c["mu_1"], d.REFERENCE)):
            circle = [ax.to(mu * math.cos(2 * math.pi * i / 180), mu * math.sin(2 * math.pi * i / 180)) for i in range(181)]
            _dashed_line(surface, colour, circle, 1)
        ax.legend(surface, [("μ_0", d.DIM, "dashed"), ("μ_1", d.REFERENCE, "dashed")])
        k = self.cache_k
        force = lambda s_x, s_y: (-s_x * characteristic(math.hypot(s_x, s_y), k) / math.hypot(s_x, s_y) / k.f_z,
                                  -s_y * characteristic(math.hypot(s_x, s_y), k) / math.hypot(s_x, s_y) / k.f_z)
        tx, ty = out.wheel.tau_star_x, out.wheel.tau_star_y
        angle = math.degrees(math.atan(abs(ty)))                     # slip angle seen by the tyre, folded
        share = min(angle / 30.0, 1.0)
        colour = tuple(int(a + (b - a) * share) for a, b in zip(d.CURVE, d.F_Y))   # blue at 0, red from 30 deg
        u0, u1 = math.asinh(-10.0 / 0.05), math.asinh(1.0 / 0.05)
        if self.polar.selected == "α":
            sweep = [0.05 * math.sinh(u0 + (u1 - u0) * i / 800) for i in range(801)]          # tau*_x
            slips = [(s_x, ty) for s_x in sweep]
            text = f"α = {math.degrees(math.atan(-ty)):+.1f}°"
        elif tx < 1.0:
            s_y_sigma = ty / (1 - tx)                                    # sigma_y, held
            sweep = [-0.95 + 20.0 * (i / 800) ** 3 for i in range(801)]                         # sigma_x
            slips = [(g / (1 + g), s_y_sigma / (1 + g)) for g in sweep]  # s = sigma / (1 + sigma_x)
            text = f"σ_y = {s_y_sigma:+.3f}"
        else:
            slips, text = [], "σ_y undefined (locked)"
        slips = [s for s in slips if math.hypot(*s) > 1e-9]
        d.polyline(surface, colour, ax.line([force(*s) for s in slips]), 2)
        ax.header_text(surface, text, colour)
        s_p = peak_slip(k)
        for (a_x, a_y), (b_x, b_y) in zip(slips, slips[1:]):          # |s| crosses s_p: the curve touches mu_0
            m_a, m_b = math.hypot(a_x, a_y) - s_p, math.hypot(b_x, b_y) - s_p
            if m_a * m_b < 0:
                w = m_a / (m_a - m_b)
                x, y = force(a_x + w * (b_x - a_x), a_y + w * (b_y - a_y))
                pygame.draw.circle(surface, d.WARNING, ax.to(x, y), 5, 2)
        ax.sides(surface)
        ax.point(surface, out.wheel.f_x / out.f_z, out.wheel.f_y / out.f_z)

    # Draws M_z or the trail t against alpha.
    def aligning(self, surface, cell, out, c):
        is_mz = self.mz.selected == "M_z"
        self.mz.draw(surface, (cell.right - self.mz.width() - 10, cell.y + 6))
        span = self.alpha_range.value
        data = [(a, v) for a, v in (c["mz"] if is_mz else c["t"]) if abs(a) <= span]
        top = max(abs(v) for _, v in data) * 1.15
        lo = -top if is_mz else min(min(v for _, v in data) * 1.15, -0.1 * top)
        ax = Axes(cell, (-span, span), (lo, top))
        step = next(s for s in (5, 10, 15, 30, 45, 90) if 2 * span / s <= 8)   # [deg] round angles
        ax.frame(surface, [i * step for i in range(-int(span // step), int(span // step) + 1)], ticks(lo, top, 4), "α [°]", "M_z [N m]" if is_mz else "t [mm]",
                 x_fmt="{:g}°")
        if is_mz:
            # M_z = -t(alpha) F_y with F_y in combined slip at the current tau*_x (friction circle shared with F_x)
            tx = out.wheel.tau_star_x
            k = self.cache_k
            live = []
            for a, _ in data:
                s_y = abs(math.tan(a * DEG))
                m = math.hypot(tx, s_y)
                f_y = characteristic(m, k) * s_y / m * (1 if math.sin(a * DEG) >= 0 else -1) if m > 0 else 0.0
                live.append((a, -trail(a * DEG, k) * f_y))
            d.polyline(surface, d.F_Y, ax.line(live))
            ax.legend(surface, [("M_z", d.F_Y, "line")])
            d.label(surface, f"τ*_x = {tx:+.2f}", (ax.rect.right - 6, ax.rect.y + 26), d.DIM, 11, "tr")
        else:
            d.polyline(surface, d.F_Y, ax.line(data))
            ax.legend(surface, [("t", d.F_Y, "line")])
        ax.header_slider(surface, self.alpha_range, f"α ±{span:.0f}°")
        if math.isfinite(out.alpha):
            ax.point(surface, math.degrees(out.alpha), out.wheel.m_z if is_mz else out.wheel.trail * 1000)


# =============================================================================
# TRANSIENT VIEW
# Maxwell element along x and y with carcass damping (report fig. 6.3),
# transient slip against time, force build-up against distance rolled.
# =============================================================================

class TransientView:
    # Returns nothing; the scale of the traces is set at the first draw.
    def __init__(self):
        self.reset()

    # Returns nothing; forgets the plotted range (scale only grows until a reset).
    def reset(self):
        self.span = {"x": None, "y": None}

    # Draws the transient view: x on the left, y on the right; element on top, traces below.
    def draw(self, surface, rect, out, q, k: TyreAtLoad, history):
        w = (rect.w - 10) // 2
        h_top = 330                                                  # [px] height of the element panel
        k_spring = k.c_s / k.d_relax
        v_x = abs(out.v_x)
        c_text = "∞" if v_x < 1e-6 else f"{k.c_s / v_x:.0f} N s/m"
        r = out.wheel
        for i, (comp, u, tau, tau_star, force) in enumerate((("x", r.f_x / k_spring, q.tau_x, r.tau_star_x, r.f_x),
                                                              ("y", r.f_y / k_spring, q.tau_y, r.tau_star_y, r.f_y))):
            x = rect.x + i * (w + 10)
            top = pygame.Rect(x, rect.y, w, h_top)
            low = pygame.Rect(x, rect.y + h_top + 10, w, rect.h - h_top - 10)
            colour = d.F_X if comp == "x" else d.F_Y                  # axis colour: the trace and the patch only
            d.panel(surface, top)
            d.panel(surface, low)
            self.element(surface, top, comp, u, tau, tau_star, force, c_text, colour)
            self.traces(surface, low, comp, history, colour)

    # Draws the Maxwell element along one axis with its deflection.
    def element(self, surface, cell, name, u, tau, tau_star, force, c_text, colour):
        d.label(surface, f"{name} · {'longitudinal' if name == 'x' else 'lateral'}", (cell.x + 12, cell.y + 8), d.DIM, 13)
        y_mid = cell.y + cell.h * 0.45
        rim = pygame.Rect(cell.x + 16, y_mid - 70, 40, 140)
        pygame.draw.rect(surface, d.RIM, rim)
        d.label(surface, "rim", (rim.centerx, rim.bottom + 12), d.DIM, 12, "c")
        gain = 5.0                                                   # [px per mm] drawn deflection
        rest = 0.22 * cell.w
        length = max(rest + u * 1000 * gain, 20)
        x0, x1 = rim.right + 12, rim.right + 12 + length
        pygame.draw.line(surface, d.STEEL, (rim.right, y_mid - 30), (x0, y_mid - 30), 2)
        d.spring(surface, d.GEOMETRY, (x0, y_mid - 30), (x1, y_mid - 30), 10, 10)
        d.label(surface, "K", ((x0 + x1) / 2, y_mid - 56), d.GEOMETRY, 13, "c")
        pygame.draw.line(surface, d.STEEL, (rim.right, y_mid + 30), (x0, y_mid + 30), 2)
        pot = pygame.Rect(x0, y_mid + 18, 0.6 * rest + 25 * gain, 24)
        pygame.draw.rect(surface, d.GEOMETRY, pot, 1)
        rod = x1 - 0.4 * rest
        pygame.draw.line(surface, d.GEOMETRY, (rod, y_mid + 22), (rod, y_mid + 38), 2)
        pygame.draw.line(surface, d.STEEL, (rod, y_mid + 30), (x1 + 10, y_mid + 30), 2)
        d.label(surface, "c_0", ((x0 + x1) / 2, y_mid + 52), d.GEOMETRY, 13, "c")
        patch = pygame.Rect(x1 + 10, y_mid - 70, 26, 140)
        pygame.draw.rect(surface, d.TYRE, patch)                    # contact patch: black, edged in the axis colour
        pygame.draw.rect(surface, colour, patch, 2)
        d.label(surface, "patch", (patch.centerx, patch.bottom + 12), d.DIM, 12, "c")
        road_x = cell.right - 40
        cs = patch.right + 0.25 * (road_x - patch.right)
        pygame.draw.line(surface, d.STEEL, (patch.right, y_mid), (cs, y_mid), 2)
        damper = pygame.Rect(cs, y_mid - 13, 0.35 * (road_x - patch.right), 26)
        pygame.draw.rect(surface, d.GEOMETRY, damper, 1)
        pygame.draw.line(surface, d.GEOMETRY, (damper.centerx, y_mid - 9), (damper.centerx, y_mid + 9), 2)
        pygame.draw.line(surface, d.STEEL, (damper.centerx, y_mid), (road_x, y_mid), 2)
        d.label(surface, "c", (damper.centerx, y_mid - 30), d.GEOMETRY, 13, "c")
        pygame.draw.rect(surface, (42, 45, 51), (road_x, y_mid - 70, 22, 140))
        d.label(surface, "road", (road_x + 11, y_mid + 82), d.DIM, 12, "c")
        y = cell.bottom - 26
        items = (("u", f"{u * 1000:+.1f} mm"), ("τ", f"{tau:+.4f}"), ("τ*", f"{tau_star:+.4f}"), ("F", f"{force:+.0f} N"), ("c", c_text))
        x = cell.x + 12
        for n, v in items:
            r = d.label(surface, n + " ", (x, y), d.DIM, 13)
            r = d.label(surface, v, (r.right, y), d.TEXT, 13)
            x = r.right + 16

    # Draws tau* of component comp ("x" or "y") and its steady value against time, last second.
    def traces(self, surface, cell, comp, history, colour):
        i = 1 if comp == "x" else 2
        steady = [(p[0], p[i + 2]) for p in history if math.isfinite(p[i + 2])]
        values = [p[i] for p in history] + [v for _, v in steady]
        old = self.span[comp]
        lo, hi = (min(values + [-0.01]), max(values + [0.01])) if values else (-0.01, 0.01)
        if old is not None:
            lo, hi = min(lo, old[0]), max(hi, old[1])
        self.span[comp] = (lo, hi)
        pad, room = 0.08 * (hi - lo), 0.25 * (hi - lo)               # room above the data for the legend
        ax = Axes(cell, (-1.0, 0.0), (lo - pad, hi + room))
        ax.frame(surface, [-1, -0.75, -0.5, -0.25, 0], ticks(lo - pad, hi + room, 4), "t − t_now [s]",
                 f"τ*_{comp} [-]", y_fmt="{:.3g}")
        ax.legend(surface, [(f"τ*_{comp}", colour, "line"), (f"steady V_s{comp} / |V_x|", d.REFERENCE, "line")])
        d.label(surface, "scale grows only, R resets", (ax.rect.x + 6, ax.rect.y + 6), d.DIM, 11)   # in the room above the data
        if len(history) < 2:
            return
        t_end = history[-1][0]
        pts = [ax.to(t - t_end, v) for t, v in steady[::2]]
        if len(pts) >= 2:                                            # under the trace: the target it follows
            d.polyline(surface, d.REFERENCE, pts, 1)
        d.polyline(surface, colour, [ax.to(p[0] - t_end, p[i]) for p in history[::2]], 2)


# =============================================================================
# FORCES VIEW
# 3D free-body diagram of the wheel (report fig. 5.1) and the measured actions.
# =============================================================================

# Power terms of the balance (report S22): name, formula, meaning. Click the arrow to open.
POWER_TERMS = (
    ("motor", "P_motor = T_D Ω", "power of the drive torque on the rim"),
    ("belt", "P_belt = −F_r V", "power the belt drive spends to keep V"),
    ("friction", "P_friction = (T_B + f F_z h) |Ω|", "lost in brake and rolling resistance, 0 when held"),
    ("tyre", "P_tyre = −F_t · V_s + F_x Ω (h − R_0)", "sliding and carcass; last term because h ≠ R_0"),
    ("kinetic", "P_kinetic = J_w Ω dΩ/dt", "rate of the kinetic energy of the wheel"),
)


class ForcesView:
    # Returns nothing; the free-body diagram is built at the first draw.
    def __init__(self):
        self.wheel3d = None
        self.open = set()           # power terms whose explanation is shown
        self.toggles = []           # (screen rect, name) of the arrows drawn in the last frame
        self.hidden = set()         # colour-key groups switched off: not drawn in the free-body diagram
        self.keys = []              # (screen rect, name) of the colour-key entries drawn in the last frame
        self.values_button = Button("values")   # numbers instead of symbols in the 3D drawing

    # Returns True if the click switched a colour-key group on or off, or opened or closed a power explanation.
    def click(self, point) -> bool:
        for r, name in self.keys:
            if r.collidepoint(point):
                self.hidden ^= {name}
                return True
        for r, name in self.toggles:
            if r.collidepoint(point):
                self.open ^= {name}
                return True
        return False

    # Draws the free-body diagram, the measured actions and the power balance.
    def draw(self, surface, rect, out, t_net: float, weight: float, f_z0: float, t_ref: float, values: bool = False):
        fbd = pygame.Rect(rect.x, rect.y, rect.w - 370, rect.h)
        d.panel(surface, fbd)
        inner = pygame.Rect(fbd.x + 10, fbd.y + 48, fbd.w - 20, fbd.h - 88)
        if self.wheel3d is None or self.wheel3d.rect != inner:   # rebuilt only if the panel changes, so the camera stays
            self.wheel3d = Wheel3D(inner)
        d.label(surface, "free-body diagram, wheel frame", (fbd.x + 12, fbd.y + 9), d.TEXT, 13)
        d.label(surface, ORBIT_HINT, (fbd.x + 12, fbd.y + 28), (95, 100, 110), 12)
        self.values_button.draw(surface, (fbd.right - 12 - d.label_width("values", 13) - 22, fbd.y + 6), values)
        self.wheel3d.draw(surface, out, t_net, weight, f_z0, t_ref, 80.0, values, self.hidden)
        x = fbd.x + 12
        self.keys = []
        for name, colour in (("road forces", d.FORCE), ("road moments", d.MOMENT), ("loads", d.LOAD),   # colour key:
                             ("frame reactions", d.REACTION), ("T_D", d.T_DRIVE), ("T_B", d.T_BRAKE)):  # a click hides or shows the group
            r = pygame.Rect(x, fbd.bottom - 29, d.label_width(name, 12) + 14, 22)   # a button without outline:
            if r.collidepoint(d.MOUSE):                                          # it lights up under the mouse, like -/+
                pygame.draw.rect(surface, d.HOVER, r, border_radius=4)
                pygame.draw.rect(surface, d.TEXT, r, 1, border_radius=4)
            d.label(surface, name, r.center, (70, 74, 82) if name in self.hidden else colour, 12, "c")
            self.keys.append((r, name))
            x = r.right + 4
        x = fbd.right + 10
        w = out.wheel
        groups = (("road on tyre", (("F_x", w.f_x, "N"), ("M_y", w.m_y, "N m"), ("F_y", w.f_y, "N"), ("M_z", w.m_z, "N m"),
                                    ("F_z", out.f_z, "N"), ("M_x", 0.0, "N m"))),
                  ("hub", (("R_hx", out.r_hx, "N"), ("M_hx", out.m_hx, "N m"), ("R_hy", out.r_hy, "N"), ("M_hz", out.m_hz, "N m"),
                           ("R_hz", out.r_hz, "N"), ("T", t_net, "N m"))),
                  ("belt", (("F_r", out.f_par, "N"), ("F_n", out.f_perp, "N"))))
        y = rect.y
        for title, items in groups:
            box = pygame.Rect(x, y, 360, 34 + 24 * ((len(items) + 1) // 2))
            d.panel(surface, box)
            d.label(surface, title, (box.x + 12, box.y + 8), d.DIM, 13)
            for i, (name, value, unit) in enumerate(items):
                px, py = box.x + 12 + (i % 2) * 175, box.y + 32 + 24 * (i // 2)
                r = d.label(surface, name + " ", (px, py), d.DIM, 13)
                d.label(surface, f"{value:.0f} {unit}", (r.right, py), d.TEXT, 13)
            y = box.bottom + 10
        box = pygame.Rect(x, y, 360, rect.bottom - y)
        d.panel(surface, box)
        d.label(surface, "power [kW]", (box.x + 12, box.y + 8), d.DIM, 13)
        values = {"motor": out.p_motor, "belt": out.p_belt, "friction": out.p_friction, "tyre": out.p_tyre,
                  "kinetic": out.p_kinetic}
        colours = {"motor": d.T_DRIVE, "belt": d.VELOCITY, "friction": d.T_BRAKE, "tyre": d.CARCASS, "kinetic": d.STEEL}
        top = max(max(abs(p) for p in values.values()), 1.0)
        self.toggles = []
        py = box.y + 36
        for name, formula, meaning in POWER_TERMS:
            p, opened = values[name], name in self.open
            hit = pygame.Rect(box.x + 8, py - 2, 80, 20)
            self.toggles.append((hit, name))
            ax, ay = box.x + 16, py + 9
            tri = [(ax - 4, ay - 2), (ax + 4, ay - 2), (ax, ay + 3)] if opened else [(ax - 2, ay - 4), (ax + 3, ay), (ax - 2, ay + 4)]
            pygame.draw.polygon(surface, d.TEXT if opened else d.DIM, tri)
            d.label(surface, name, (box.x + 26, py), d.TEXT if opened else d.DIM, 13)
            d.label(surface, f"{p / 1000:+.2f}", (box.right - 12, py), d.TEXT, 13, "tr")
            bar = pygame.Rect(box.x + 12, py + 19, box.w - 24, 6)
            pygame.draw.rect(surface, d.FIELD, bar, border_radius=3)
            pygame.draw.rect(surface, colours[name], (bar.x, bar.y, bar.w * abs(p) / top, 6), border_radius=3)
            py += 38
            if opened:
                pygame.draw.line(surface, colours[name], (box.x + 16, py - 4), (box.x + 16, py + 34), 2)
                d.label(surface, formula, (box.x + 26, py - 4), d.TEXT, 14)
                d.label(surface, meaning, (box.x + 26, py + 18), d.DIM, 12)
                py += 50
        d.label(surface, "P_motor + P_belt = P_friction + P_tyre + P_kinetic", (box.x + 12, py + 4), d.DIM, 13)
