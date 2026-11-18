# =============================================================================
# DRAWING HELPERS
# Colours, fonts and primitives shared by every panel: text with subscripts,
# arrows, arcs, panels. Screen coordinates in pixels, y down.
# =============================================================================

import math

import pygame

# =============================================================================
# COLOURS
# Same palette as the LapTime game: one colour per kind of quantity.
# =============================================================================

BACKGROUND = (22, 24, 28)
PANEL = (31, 34, 40)
PANEL_EDGE = (58, 62, 70)
FIELD = (42, 45, 51)
GRID = (46, 50, 56)
AXIS = (90, 95, 105)
TEXT = (226, 229, 235)
DIM = (140, 146, 156)
# Colour convention of the drawings (3D, side, top, free-body diagram): one colour per kind of action.
VELOCITY = (95, 205, 125)     # velocities: V, V_x, V_y, V_sx, belt speed
FORCE = (255, 180, 50)        # forces of the road on the tyre: F_x, F_y, F_z
MOMENT = (190, 140, 255)      # moments of the road on the tyre: M_y, M_z
LOAD = (90, 155, 255)         # external loads: P, weight m_w g
REACTION = (200, 204, 212)    # reactions of the frame on the wheel: R_h, M_h
T_DRIVE = (60, 200, 190)      # input torque T_D (drive), as its pedal and slider
T_BRAKE = (235, 100, 165)     # input torque T_B (brake), as its pedal and slider
GEOMETRY = (226, 229, 235)    # angles and spin: delta, Omega, axes
POINT = (255, 235, 90)        # operating point, centre C, tau*
CARCASS = (215, 180, 140)     # carcass: spring and damper of the transient tyre
PATCH = MOMENT                # contact patch in the side, top and zoom views: the road, as its moments
WARNING = (255, 95, 80)       # limits and alerts: peak, held wheel, red mark, input error
BRAND = (255, 166, 43)        # site link on hover, controller notice: the orange-yellow of nicolasromanella.com
PAD_ON = (80, 200, 120)       # controller detected (green dot)
# Plots: one colour per axis, x as the forces, y red; the main curve blue.
F_X = FORCE                   # x quantities in the plots (sigma_x, tau*_x)
F_Y = (240, 85, 75)           # y quantities in the plots (tau*_y, M_z curves)
F_Z = LOAD                    # the load P in the top bar
STEEL = REACTION              # fork and hub
TYRE = (20, 20, 20)
TREAD = (44, 44, 44)
RIM = (74, 79, 88)
CURVE = (90, 155, 255)        # main curve of a plot: s_x, F_t in s, polar
CURVE_SIGMA = (175, 125, 255) # F_t in sigma
CURVE_ALPHA = (80, 205, 215)  # F_y against alpha
REFERENCE = (110, 115, 125)   # reference curves and circles

_FONTS = {}


# Returns a cached font of the given pixel size.
def font(size: int) -> pygame.font.Font:
    if size not in _FONTS:
        _FONTS[size] = pygame.font.SysFont("segoeui,dejavusans,arial", size)
    return _FONTS[size]


# =============================================================================
# TEXT
# "F_x" draws x as a subscript; "u_x [mm]" keeps the rest normal.
# =============================================================================

# Returns the width [px] of a label with subscripts.
def label_width(text: str, size: int = 14) -> int:
    return sum(font(s).size(t)[0] for t, s in _runs(text, size))


# Returns the text split into (piece, font size) runs, subscripts after '_'.
def _runs(text: str, size: int) -> list:
    runs, i, sub = [], 0, int(size * 0.72)
    while i < len(text):
        j = text.find("_", i)
        if j < 0:
            runs.append((text[i:], size)); break
        if j > i:
            runs.append((text[i:j], size))
        k = j + 1
        while k < len(text) and (text[k].isalnum() or text[k] in "αβ"):
            k += 1
        runs.append((text[j + 1:k], sub))
        i = k
    return runs


# Draws a label with subscripts; anchor is "tl", "tr", "c", "ml", "mr"; backed: on a dark tag, so it reads
# over drawings (3D views); returns its rect.
def label(surface, text: str, pos, colour=TEXT, size: int = 14, anchor: str = "tl", backed: bool = False) -> pygame.Rect:
    runs = _runs(text, size)
    w = sum(font(s).size(t)[0] for t, s in runs)
    h = font(size).get_height()
    x, y = pos
    if anchor in ("tr", "mr"):
        x -= w
    if anchor == "c":
        x, y = x - w / 2, y - h / 2
    if anchor in ("ml", "mr"):
        y -= h / 2
    if backed:
        tag = pygame.Surface((int(w) + 8, h + 2), pygame.SRCALPHA)
        tag.fill((*BACKGROUND, 190))
        surface.blit(tag, (x - 4, y - 1))
    cx = x
    for t, s in runs:
        img = font(s).render(t, True, colour)
        dy = 0 if s == size else int(size * 0.42)
        surface.blit(img, (cx, y + dy))
        cx += img.get_width()
    return pygame.Rect(int(x), int(y), int(w), h)


# =============================================================================
# SHAPES
# =============================================================================

# Draws a filled panel with a thin edge.
def panel(surface, rect, fill=PANEL):
    pygame.draw.rect(surface, fill, rect, border_radius=6)
    pygame.draw.rect(surface, PANEL_EDGE, rect, 1, border_radius=6)


# Draws an arrow from start to end with a filled head.
def arrow(surface, colour, start, end, width: int = 3, head: float = 11.0):
    x0, y0 = start
    x1, y1 = end
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1.0:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    head = min(head, 0.6 * length)
    base = (x1 - ux * head, y1 - uy * head)
    pygame.draw.line(surface, colour, start, base, width)
    left = (base[0] - uy * head * 0.45, base[1] + ux * head * 0.45)
    right = (base[0] + uy * head * 0.45, base[1] - ux * head * 0.45)
    pygame.draw.polygon(surface, colour, [end, left, right])


# Draws a filled arrowhead of fixed size [px] with its tip at tip, pointing along direction (dx, dy).
def head(surface, colour, tip, direction, size: float = 11.0):
    n = math.hypot(*direction)
    if n < 1e-9:
        return
    ux, uy = direction[0] / n, direction[1] / n
    base = (tip[0] - ux * size, tip[1] - uy * size)
    pygame.draw.polygon(surface, colour, [tip, (base[0] - uy * size * 0.45, base[1] + ux * size * 0.45),
                                          (base[0] + uy * size * 0.45, base[1] - ux * size * 0.45)])


# Draws a polyline (an arc on screen) with a fixed-size arrowhead at its last point, along its end tangent.
def arc_line(surface, colour, pts, width: int = 3, size: float = 11.0):
    if len(pts) < 2:
        return
    pygame.draw.lines(surface, colour, False, pts, width)
    k = max(1, len(pts) // 8)                                   # tangent over the last eighth of the arc
    head(surface, colour, pts[-1], (pts[-1][0] - pts[-1 - k][0], pts[-1][1] - pts[-1 - k][1]), size)


# Draws a circular arc around centre from angle a0 to a1 [rad, CCW on screen] with an arrowhead at a1.
def arc_arrow(surface, colour, centre, radius: float, a0: float, a1: float, width: int = 3):
    n = max(8, int(abs(a1 - a0) * radius / 4))
    pts = [(centre[0] + radius * math.cos(a0 + (a1 - a0) * i / n),
            centre[1] - radius * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    arc_line(surface, colour, pts, width)


# Draws a dashed line.
def dashed(surface, colour, start, end, width: int = 1, dash: float = 5.0):
    x0, y0 = start
    x1, y1 = end
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1.0:
        return
    n = int(length / dash)
    for i in range(0, n, 2):
        a, b = i / n, min((i + 1) / n, 1.0)
        pygame.draw.line(surface, colour, (x0 + (x1 - x0) * a, y0 + (y1 - y0) * a),
                         (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b), width)


# Draws a polyline only if it has at least two points.
def polyline(surface, colour, points, width: int = 2):
    if len(points) >= 2:
        pygame.draw.lines(surface, colour, False, points, width)


# Draws a zigzag spring from start to end (horizontal on screen).
def spring(surface, colour, start, end, turns: int = 10, amplitude: float = 10.0, width: int = 2):
    (x0, y), (x1, _) = start, end
    pts = [(x0, y)]
    for i in range(turns):
        pts.append((x0 + (x1 - x0) * (i + 0.5) / turns, y + (amplitude if i % 2 else -amplitude)))
    pts.append((x1, y))
    pygame.draw.lines(surface, colour, False, pts, width)
