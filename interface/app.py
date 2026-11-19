# =============================================================================
# APP
# Window, main loop and controls of the tyre rig. Advances the rig in real
# time with the 1 ms step of the report (7.2) and draws one frame per loop.
# Keyboard: Tab mode, R reset, 1/2/3 views; drive: arrows steer, throttle,
# brake, stick = steer angle; test: left/right delta 0.5 deg, up T_D, down T_B 1 % (Shift lowers), -/+ buttons. Sliders for
# delta, T_D, T_B (test mode, bottom left), V and P (top bar). Controller as 7.3.
# A new V or P changes only the test condition: state and inputs stay (report 2.3).
# =============================================================================

import ctypes
import math
import sys
import time
from collections import deque

import pygame
from pygame._sdl2 import controller as sdl_controller

from interface import draw as d
from interface.plots import ForcesView, PlotsView, TransientView
from interface.views import ORBIT_HINT, Rig3D, contact_zoom, side_scale, side_view, top_view
from interface.widgets import Button, NumberBox, Slider, Switch
from rig.rig import (V_MAX, V_RESET, Conditions, Controls, check_conditions, free_rolling, load_limits,
                     outputs, step, torque_limit)
from rig.tyre import at_load
from rig.wheel import G, Wheel, free_rolling_radius, loaded_radius

WIDTH, HEIGHT = 1600, 900       # [px] drawing size; the window scales it to fit
WINDOW_SHARE = 0.85             # [-]  initial window size as a share of the screen
DT = 1e-3                       # [s]  rig time step (report 7.2)
STEER_RATE = math.radians(60)   # [rad/s] steer rate of the stick in test mode (report 7.3)
STEER_BACK = 0.4                # [s]     drive mode: a released steer arrow returns from full lock to zero in this time
STEER_MAX = math.radians(20)    # [rad]   steer limit in drive mode, full stick (design choice)
DEAD_ZONE = 0.08                # [-]     controller dead zone
STEP_DELTA = math.radians(0.5)  # [rad]   one step of delta: keys and -/+ buttons, test mode
STEP_TORQUE = 0.01              # [-]     one step of T_D, T_B as a share of T_max
TORQUE_RATE = 0.5               # [1/s]   test mode: change of T_D, T_B per second at full trigger, share of T_max
KEY_RAMP = 0.75                 # [s]     drive mode: throttle or brake arrow held from rest reaches T_max in this time;
                                #         the rate grows with the time held, so the value grows with its square
STEER_RAMP = 0.5                # [s]     drive mode: a steer arrow held from rest reaches full lock in this time,
                                #         growing with the square of the time held; released, back in STEER_BACK
KEY_RELEASE = 0.3               # [s]     drive mode: a released throttle or brake arrow returns from T_max to zero
STEP_V, STEP_P = 1.0, 50.0      # [m/s], [N] one step of V and P with the -/+ buttons
V_STEADY = 0.5                  # [m/s] below this |V_x| the steady transient slip is not drawn (display only)
MAX_STEPS = 50                  # [-]  rig steps per frame at most (slow PCs fall behind real time)
DEG = math.pi / 180.0
SITE = "nicolasromanella.com"    # link at the left of the top bar
SITE_URL = "https://nicolasromanella.com"


class App:
    # Returns nothing; opens the window and builds the rig, widgets and views.
    def __init__(self):
        if sys.platform == "win32":
            ctypes.windll.user32.SetProcessDPIAware()           # real pixels, no blurry OS scaling
        pygame.init()
        sdl_controller.init()
        pygame.display.set_caption("Virtual Tire Test Rig")
        pygame.key.set_repeat(300, 50)                           # held keys repeat in test mode
        info = pygame.display.Info()
        share = min(WINDOW_SHARE * info.current_w / WIDTH, WINDOW_SHARE * info.current_h / HEIGHT, 1.0) \
            if info.current_w > 0 else 1.0
        self.window = pygame.display.set_mode((int(WIDTH * share), int(HEIGHT * share)), pygame.RESIZABLE)
        self.window_size = self.window.get_size()
        self.screen = pygame.Surface((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.wheel = Wheel()
        self.joystick = None
        self.gamepad = None                                      # same pad through the SDL game-controller mapping
        self.trigger_seen = [False, False]                       # throttle, brake
        self.mode = Switch(["drive", "test"], "test")           # opens in test mode
        self.view = Switch(["Plots", "Transient", "Forces"], "Plots")
        self.reset_button = Button("Reset")
        self.full_button = Button("Full screen")
        self.zoom_button = Button("zoom")                         # side panel shows the contact zoom
        self.zoom = False
        self.values_button = Button("values")                     # numbers instead of symbols in the 3D views
        self.show_values = False
        self.steps = [(Button("−", 12), Button("+", 12)) for _ in range(3)]   # delta, T_D, T_B
        self.steps_vp = [(Button("−", 13, outline=False), Button("+", 13, outline=False)) for _ in range(2)]  # V, P, beside their boxes
        self.box_v = NumberBox("V", "m/s", V_RESET, 1, 5)
        self.box_p = NumberBox("P", "N", Conditions().p, 0, 5)
        p_lo, p_hi = load_limits(self.wheel)
        self.slide_delta = Slider(-180.0, 180.0, 0.0, centred=True)      # [deg]
        self.slide_t_d = Slider(0.0, 1.0, 0.0)                           # [-] share of T_max
        self.slide_t_b = Slider(0.0, 1.0, 0.0)                           # [-] share of T_max
        self.slide_v = Slider(0.0, V_MAX, V_RESET)                       # [m/s]
        self.slide_p = Slider(p_lo, p_hi, Conditions().p)                # [N]
        self.plots, self.transient, self.forces = PlotsView(), TransientView(), ForcesView()
        self.rig3d = Rig3D(pygame.Rect(14, 64, 612, 322))
        self.message = ""
        self.site_rect = pygame.Rect(0, 0, 0, 0)
        self.hover = ""                                          # button under the mouse: "site", "full" or ""
        self.notice, self.noticed = False, False                   # no-controller notice, shown once per session
        self.pad_used = False                                    # the controller counts once it has been used
        self.notice_ok = Button("OK")
        self.held = {pygame.K_LEFT: 0.0, pygame.K_RIGHT: 0.0, pygame.K_UP: 0.0, pygame.K_DOWN: 0.0}   # [s] arrows held
        self.key_throttle, self.key_brake = 0.0, 0.0              # [-] arrow throttle and brake, share of T_max
        self.orbiting, self.last_pos = None, (0, 0)              # 3D view being turned by the mouse
        self.panning = None                                      # 3D view being moved (wheel button held)
        self.reset()

    # Returns nothing; free rolling at V_RESET, delta = 0, no torque (report 7.3).
    def reset(self, v: float = V_RESET):
        self.conditions = Conditions(v=v, p=self.box_p.value)
        self.box_v.value = v
        self.q = free_rolling(v, self.wheel)
        self.delta, self.t_d, self.t_b = 0.0, 0.0, 0.0
        self.key_throttle, self.key_brake = 0.0, 0.0
        self.t, self.belt, self.spin, self.rtf = 0.0, 0.0, 0.0, 0.0
        self.frame_dt = 0.0                                      # [s] duration of the last frame
        self.history = deque(maxlen=1000)                        # tau* and steady tau every step, last 1 s
        self.transient.reset()

    # Returns every slider that can be dragged now.
    def sliders(self) -> list:
        test = self.mode.selected == "test"
        for s in (self.slide_delta, self.slide_t_d, self.slide_t_b):
            s.enabled = test
        own = [self.slide_delta, self.slide_t_d, self.slide_t_b, self.slide_v, self.slide_p]
        return own + (self.plots.sliders() if self.view.selected == "Plots" else [])

    # =========================================================================
    # INPUT
    # =========================================================================

    # Returns False when the window is closed; handles mouse, keys and pad events.
    def events(self) -> bool:
        try:
            events = pygame.event.get()
        except (SystemError, KeyError):                          # pygame could not convert a pad event: skip it
            return True
        for event in events:
            if event.type == pygame.QUIT:
                return False
            # the pad is opened once and kept: SDL sends JOYDEVICEADDED more than once for the same pad, and
            # replacing the open objects would close the device under the new ones (KeyError in event.get)
            if event.type == pygame.JOYDEVICEADDED and self.joystick is None:
                self.joystick = pygame.joystick.Joystick(event.device_index)
                if sdl_controller.is_controller(event.device_index):  # known pad: SDL maps L1, R1, triggers
                    self.gamepad = sdl_controller.Controller(event.device_index)
            if event.type == pygame.JOYDEVICEREMOVED and self.joystick is not None \
                    and event.instance_id == self.joystick.get_instance_id():
                self.joystick, self.gamepad = None, None
                self.trigger_seen = [False, False]
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.click(self.scaled(event.pos))
            if event.type == pygame.MOUSEMOTION:
                self.drag(self.scaled(event.pos))
                self.hover_at(self.scaled(event.pos))
                d.MOUSE = self.scaled(event.pos)                 # widgets light up under the mouse
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.release()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:   # wheel button: move the 3D view
                pos = self.scaled(event.pos)
                self.panning, self.last_pos = self.view_at(pos), pos
            if event.type == pygame.MOUSEBUTTONUP and event.button == 2:
                self.panning = None
            if event.type == pygame.MOUSEWHEEL:                      # zoom of the 3D view under the mouse
                view = self.view_at(self.scaled(pygame.mouse.get_pos()))
                if view is not None:
                    view.zoom(1.15 ** event.y)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                view = self.view_at(self.scaled(event.pos))
                if view is not None:
                    view.reset_view()
            if event.type == pygame.KEYDOWN and self.notice:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE, pygame.K_SPACE):
                    self.notice = False                          # Enter, Esc or Space close the notice
                continue
            if event.type == pygame.KEYDOWN:
                if self.box_v.editing or self.box_p.editing:
                    self.type_into(event)
                elif event.key == pygame.K_ESCAPE:
                    return False
                else:
                    self.key(event)
        return True

    # Returns the point in drawing pixels of a window point.
    def scaled(self, pos):
        w, h = self.window.get_size()
        return (pos[0] * WIDTH / w, pos[1] * HEIGHT / h)

    # Returns nothing; applies a mouse click [drawing px] to the widget or 3D view under it.
    def click(self, pos):
        if self.notice:                                          # only OK closes the notice
            if self.notice_ok.click(pos):
                self.notice = False
            return
        if self.site_rect.collidepoint(pos):
            open_site()
            return
        if any(s.press(pos) for s in self.sliders()):
            self.drag(pos)
            return
        if self.box_v.click(pos) or self.box_p.click(pos):
            return
        if self.reset_button.click(pos):
            self.reset()
        elif self.full_button.click(pos):
            self.toggle_fullscreen()
        elif self.zoom_button.click(pos):
            self.zoom = not self.zoom
        elif self.values_button.click(pos) or (self.view.selected == "Forces" and self.forces.values_button.click(pos)):
            self.show_values = not self.show_values
        elif self.mode.click(pos):
            self.check_controller()
        elif self.view.click(pos):
            pass
        elif any(b.click(pos) for pair in self.steps_vp for b in pair):
            (v_minus, v_plus), (_, p_plus) = self.steps_vp
            lo, hi = load_limits(self.wheel)
            if v_minus.click(pos) or v_plus.click(pos):
                step = STEP_V if v_plus.click(pos) else -STEP_V
                self.set_condition(self.box_v, min(max(self.conditions.v + step, 0.0), V_MAX))
            else:
                step = STEP_P if p_plus.click(pos) else -STEP_P
                self.set_condition(self.box_p, min(max(self.conditions.p + step, lo), hi))
        elif self.mode.selected == "test" and any(b.click(pos) for pair in self.steps for b in pair):
            for i, (minus, plus) in enumerate(self.steps):
                if minus.click(pos):
                    self.nudge(i, -1)
                elif plus.click(pos):
                    self.nudge(i, +1)
        elif self.view.selected == "Plots" and self.plots.click(pos):
            pass
        elif self.view.selected == "Forces" and self.forces.click(pos):
            pass
        else:
            self.orbiting, self.last_pos = self.view_at(pos), pos

    # Returns nothing; in drive mode without a controller, shows once per session the notice that suggests one.
    def check_controller(self):
        if self.mode.selected == "drive" and not self.noticed and self.controller() is None:
            self.notice = self.noticed = True

    # Returns nothing; remembers which link-like button is under the mouse (the site button turns orange
    # and shows a hand; every other button only lights up).
    def hover_at(self, pos):
        new = "site" if self.site_rect.collidepoint(pos) else "full" if self.full_button.rect.collidepoint(pos) else ""
        if new != self.hover:
            self.hover = new
            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if new == "site" else pygame.SYSTEM_CURSOR_ARROW)
            except Exception:
                pass

    # Returns nothing; switches the window between full screen and its normal size.
    def toggle_fullscreen(self):
        if self.window.get_flags() & pygame.FULLSCREEN:
            self.window = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        else:
            self.window_size = self.window.get_size()
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    # Returns the 3D view under a point (rig or free-body diagram), or None.
    def view_at(self, pos):
        if self.rig3d.rect.collidepoint(pos):
            return self.rig3d
        fbd = self.forces.wheel3d
        if self.view.selected == "Forces" and fbd is not None and fbd.rect.collidepoint(pos):
            return fbd
        return None

    # Returns nothing; applies the slider being dragged.
    def drag(self, pos):
        if self.panning is not None:
            self.panning.pan(pos[0] - self.last_pos[0], pos[1] - self.last_pos[1])
            self.last_pos = pos
            return
        if self.orbiting is not None:
            self.orbiting.orbit(pos[0] - self.last_pos[0], pos[1] - self.last_pos[1])
            self.last_pos = pos
            return
        t_max = torque_limit(self.conditions, self.wheel)
        if self.slide_delta.drag(pos) is not None:
            self.delta = self.slide_delta.value * DEG
        if self.slide_t_d.drag(pos) is not None:
            self.t_d = self.slide_t_d.value * t_max
        if self.slide_t_b.drag(pos) is not None:
            self.t_b = self.slide_t_b.value * t_max
        if self.slide_v.drag(pos) is not None:
            self.set_condition(self.box_v, round(self.slide_v.value, 1))
        if self.slide_p.drag(pos) is not None:
            self.set_condition(self.box_p, round(self.slide_p.value))
        for s in self.plots.sliders():
            s.drag(pos)

    # Returns nothing; ends a drag and the orbit of a 3D view.
    def release(self):
        self.orbiting = None
        for s in self.sliders():
            s.release()

    # Returns nothing; sends a key to the number box being edited.
    def type_into(self, event):
        box = self.box_v if self.box_v.editing else self.box_p
        value = box.key(event)
        if value is not None:
            self.set_condition(box, value)

    # Returns nothing; checks and applies a new V or P from a box or a slider; state and inputs stay (report 2.3).
    def set_condition(self, box, value: float):
        trial = Conditions(v=value, p=self.conditions.p) if box is self.box_v else Conditions(v=self.conditions.v, p=value)
        try:
            check_conditions(trial, self.wheel)
        except ValueError as error:
            box.error, self.message = True, str(error)
            return
        box.error, self.message, box.value = False, "", value
        self.conditions = trial

    # Returns nothing; applies a key press (Tab mode, R reset, 1-3 view, arrows in test mode).
    def key(self, event):
        t_max = torque_limit(self.conditions, self.wheel)
        lower = bool(event.mod & pygame.KMOD_SHIFT)
        if event.key == pygame.K_TAB:
            self.mode.selected = "test" if self.mode.selected == "drive" else "drive"
            self.check_controller()
        elif event.key == pygame.K_r:
            self.reset()
        elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
            self.view.selected = self.view.options[event.key - pygame.K_1]
        elif self.mode.selected == "test":
            if event.key == pygame.K_LEFT:
                self.nudge(0, +1)
            elif event.key == pygame.K_RIGHT:
                self.nudge(0, -1)
            elif event.key == pygame.K_UP:
                self.nudge(1, -1 if lower else +1)
            elif event.key == pygame.K_DOWN:
                self.nudge(2, -1 if lower else +1)

    # Returns nothing; moves input i (0 delta, 1 T_D, 2 T_B) by one fine step in the direction sign.
    def nudge(self, i: int, sign: int):
        t_max = torque_limit(self.conditions, self.wheel)
        if i == 0:
            self.delta += sign * STEP_DELTA
        elif i == 1:
            self.t_d = min(max(self.t_d + sign * STEP_TORQUE * t_max, 0.0), t_max)
        else:
            self.t_b = min(max(self.t_b + sign * STEP_TORQUE * t_max, 0.0), t_max)

    # Returns the controller as (stick, throttle, brake, R1, L1): stick -1..1 (left positive), triggers 0..1,
    # bumpers pressed or not; None if absent. A pad known to SDL is read by name (any brand); an unknown
    # joystick falls back to raw axes 4, 5 and buttons 4, 5 (Xbox layout).
    def read_pad(self):
        if self.gamepad is not None:                             # Xbox, PlayStation, ...: named buttons
            g, full = self.gamepad, 32767.0
            stick = -g.get_axis(pygame.CONTROLLER_AXIS_LEFTX) / full
            stick = stick if abs(stick) > DEAD_ZONE else 0.0
            triggers = [g.get_axis(axis) / full for axis in (pygame.CONTROLLER_AXIS_TRIGGERRIGHT, pygame.CONTROLLER_AXIS_TRIGGERLEFT)]
            triggers = [t if t > DEAD_ZONE else 0.0 for t in triggers]
            return (stick, triggers[0], triggers[1], g.get_button(pygame.CONTROLLER_BUTTON_RIGHTSHOULDER) == 1,
                    g.get_button(pygame.CONTROLLER_BUTTON_LEFTSHOULDER) == 1)
        if self.joystick is None:
            return None
        stick = -self.joystick.get_axis(0)
        stick = stick if abs(stick) > DEAD_ZONE else 0.0
        triggers = [0.0, 0.0]
        if self.joystick.get_numaxes() >= 6:
            for i, axis in enumerate((5, 4)):                    # right trigger throttle, left trigger brake
                raw = self.joystick.get_axis(axis)
                if raw < -0.9:
                    self.trigger_seen[i] = True                  # a trigger reads 0 until first touched, not -1
                value = (raw + 1.0) / 2.0 if self.trigger_seen[i] else 0.0
                triggers[i] = value if value > DEAD_ZONE else 0.0
        bumpers = [self.joystick.get_numbuttons() > b and self.joystick.get_button(b) == 1 for b in (5, 4)]   # RB, LB
        return stick, triggers[0], triggers[1], bumpers[0], bumpers[1]

    # Returns the controller as read_pad does, but only once it has been used since it was seen:
    # stick, trigger or bumper moved. An idle pad (or one the system still lists when it is off)
    # sends nothing and the window says "no controller detected".
    def controller(self):
        raw = self.read_pad()
        if raw is None:
            self.pad_used = False
            return None
        if not self.pad_used:
            stick, throttle, brake, r1, l1 = raw
            self.pad_used = abs(stick) > 0.3 or throttle > 0.3 or brake > 0.3 or r1 or l1
        return raw if self.pad_used else None

    # Returns nothing. Drive: the stick position is the steer angle, triggers the torques, released = zero;
    # arrows steer at a rate. Test: the controller moves the values at a rate and they stay when released:
    # stick turns delta (any angle), R2 / L2 raise T_D / T_B faster the more they are pressed, R1 / L1 lower
    # them; arrows, -/+ buttons and sliders as well (report 7.3).
    def drive(self, dt: float):
        t_max = torque_limit(self.conditions, self.wheel)
        pad = self.controller()
        if self.mode.selected == "drive":
            keys = pygame.key.get_pressed()
            for k in self.held:                                     # time each arrow has been held
                self.held[k] = self.held[k] + dt if keys[k] else 0.0
            ramp = lambda k: 2.0 * self.held[k] / KEY_RAMP ** 2     # [1/s] rate of an arrow held for held[k]
            arrows = (1.0 if keys[pygame.K_LEFT] else 0.0) - (1.0 if keys[pygame.K_RIGHT] else 0.0)
            if pad is not None and arrows == 0.0:
                self.delta = pad[0] * STEER_MAX
            elif arrows != 0.0:                                     # faster the longer the arrow is held
                held = self.held[pygame.K_LEFT if arrows > 0 else pygame.K_RIGHT]
                rate = 2.0 * held / STEER_RAMP ** 2 * STEER_MAX
                self.delta = min(max(self.delta + arrows * rate * dt, -STEER_MAX), STEER_MAX)
            else:                                                   # arrows released: back to zero in STEER_BACK
                step = STEER_MAX / STEER_BACK * dt
                self.delta = 0.0 if abs(self.delta) <= step else self.delta - math.copysign(step, self.delta)
            for name, k in (("key_throttle", pygame.K_UP), ("key_brake", pygame.K_DOWN)):
                v = getattr(self, name)
                v = min(v + ramp(k) * dt, 1.0) if keys[k] else max(v - dt / KEY_RELEASE, 0.0)
                setattr(self, name, v)
            throttle, brake = self.key_throttle, self.key_brake
            if pad is not None:
                throttle, brake = max(throttle, pad[1]), max(brake, pad[2])
            self.t_d, self.t_b = throttle * t_max, brake * t_max
        elif pad is not None:
            stick, throttle, brake, r1, l1 = pad
            self.delta += stick * STEER_RATE * dt
            rate = TORQUE_RATE * t_max * dt                         # [N m] change in this frame at full press
            self.t_d = min(max(self.t_d + rate * (throttle - (1.0 if r1 else 0.0)), 0.0), t_max)
            self.t_b = min(max(self.t_b + rate * (brake - (1.0 if l1 else 0.0)), 0.0), t_max)

    # =========================================================================
    # SIMULATION
    # =========================================================================

    # Returns nothing; advances the rig by one frame [s] of 1 ms steps and updates the outputs.
    def advance(self, frame_dt: float):
        self.frame_dt = frame_dt
        self.delta = math.atan2(math.sin(self.delta), math.cos(self.delta))
        u = Controls(self.delta, self.t_d, self.t_b)
        n = min(int(round(frame_dt / DT)), MAX_STEPS)
        start = time.perf_counter()
        for _ in range(n):
            self.q = step(self.q, u, self.conditions, self.wheel, DT)
            self.t += DT
            self.out = outputs(self.q, u, self.conditions, self.wheel)
            self.history.append(self.transient_sample())
            self.belt += self.conditions.v * DT
            self.spin = (self.spin + self.q.omega * DT) % (2 * math.pi)   # [rad] rim angle, drawing only
        if n:
            # real-time factor: computing time of one step / simulated time of one step (1 ms)
            self.rtf = 0.9 * self.rtf + 0.1 * (time.perf_counter() - start) / (n * DT)
        if not n:
            self.out = outputs(self.q, u, self.conditions, self.wheel)

    # Returns (t, tau*_x, tau*_y, steady x, steady y) now; the steady transient slip is V_s / |V_x| (report 6.2),
    # NaN below V_STEADY, where it grows without limit.
    def transient_sample(self):
        w, v_x = self.out.wheel, abs(self.out.v_x)
        inf_x, inf_y = (w.v_sx / v_x, w.v_sy / v_x) if v_x > V_STEADY else (math.nan, math.nan)
        return (self.t, w.tau_star_x, w.tau_star_y, inf_x, inf_y)

    # =========================================================================
    # FRAME
    # =========================================================================

    # Draws the top bar: mode, V and P, F_z, t, RTF, view, reset.
    def top_bar(self, s):
        bar = pygame.Rect(10, 10, WIDTH - 20, 40)
        d.panel(s, bar)
        y = bar.y + 13
        x = bar.x + 12
        colour = d.BRAND if self.hover == "site" else d.TEXT        # a button: outlined, orange on hover
        self.site_rect = pygame.Rect(x, bar.y + 7, d.label_width(SITE, 13) + 22, 25)
        pygame.draw.rect(s, d.BRAND if self.hover == "site" else d.AXIS, self.site_rect, 1, border_radius=4)
        d.label(s, SITE, self.site_rect.center, colour, 13, "c")
        x = self.site_rect.right + 28
        x = self.mode.draw(s, (x, bar.y + 7)).right + 18
        if not self.slide_v.dragging:
            self.slide_v.value = self.conditions.v
        if not self.slide_p.dragging:
            self.slide_p.value = self.conditions.p
        for box, slider, colour, (minus, plus) in ((self.box_v, self.slide_v, d.VELOCITY, self.steps_vp[0]),
                                                   (self.box_p, self.slide_p, d.LOAD, self.steps_vp[1])):
            start = x                                             # box and slider in one frame: one quantity
            x = box.draw(s, (x + 10, bar.y + 7), buttons=(minus, plus)).right + 12
            x = slider.draw(s, pygame.Rect(x, bar.y + 13, 150, 14), colour).right + 12
            pygame.draw.rect(s, d.PANEL_EDGE, pygame.Rect(start, bar.y + 4, x - start, bar.h - 8), 1, border_radius=6)
            x += 14
        r = d.label(s, "F_z ", (x, y), d.DIM, 13)
        x = d.label(s, f"{self.out.f_z:.0f} N", (r.right, y), d.TEXT, 13).right + 18
        if self.message:
            d.label(s, self.message, (x, y), d.WARNING, 13)
        # fixed slots, right to left: Full screen, Reset, RTF, t, view switch (nothing moves when the numbers change)
        full_x = bar.right - 12 - d.label_width("Full screen", 13) - 22
        self.full_button.draw(s, (full_x, bar.y + 7))
        reset_x = full_x - 8 - d.label_width("Reset", 13) - 22
        self.reset_button.draw(s, (reset_x, bar.y + 7))
        rtf_x = reset_x - 30 - d.label_width("RTF 0.000", 13)
        r = d.label(s, "RTF ", (rtf_x, y), d.DIM, 13)
        d.label(s, f"{self.rtf:.3f}", (r.right, y), d.TEXT, 13)
        t_x = rtf_x - 6 - d.label_width("t 0000.00 s", 13)
        r = d.label(s, "t ", (t_x, y), d.DIM, 13)
        d.label(s, f"{self.t:.2f} s", (r.right, y), d.TEXT, 13)
        self.view.draw(s, (t_x - 18 - self.view.width(), bar.y + 7))

    # Draws the input panel: delta, T_B, T_D with -/+ buttons and sliders.
    def inputs(self, s, rect):
        d.panel(s, rect)
        t_max = torque_limit(self.conditions, self.wheel)
        test = self.mode.selected == "test"
        if not self.slide_delta.dragging:
            self.slide_delta.value = math.degrees(self.delta)
        if not self.slide_t_d.dragging:
            self.slide_t_d.value = self.t_d / t_max
        if not self.slide_t_b.dragging:
            self.slide_t_b.value = self.t_b / t_max
        w = (rect.w - 40) / 3
        row = ((0, self.slide_delta, "δ", f"{math.degrees(self.delta):+.1f}°", d.TEXT),     # brake left, drive right,
               (2, self.slide_t_b, "T_B", f"{self.t_b:.0f} N m", d.T_BRAKE),              # as on the controller
               (1, self.slide_t_d, "T_D", f"{self.t_d:.0f} N m", d.T_DRIVE))
        for col, (i, slider, name, value, colour) in enumerate(row):
            x, y = rect.x + 12 + col * (w + 8), rect.y + 10
            d.label(s, name, (x, y), d.DIM, 13)
            d.label(s, value, (x + w, y), d.TEXT, 13, "tr")
            if test:                                              # fine steps: 0.5 deg, 1 % of T_max
                minus, plus = self.steps[i]
                plus.draw(s, (minus.draw(s, (x + 34, y - 4)).right + 4, y - 4))
            slider.draw(s, pygame.Rect(x, y + 26, w, 14), colour)
        hint = "R reset · ← → steer · ↑ throttle · ↓ brake" if not test \
            else "R reset · ← → δ 0.5° · ↑ T_D · ↓ T_B · −/+ · sliders"
        d.label(s, hint, (rect.x + 12, rect.bottom - 22), (95, 100, 110), 12)
        d.label(s, "© 2026 Nicolas Romanella", (rect.right - 12, rect.bottom - 22), d.TEXT, 12, "tr")

    # Draws the controller notice over the window: dimmed background, message, OK.
    def draw_notice(self, s):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        s.blit(shade, (0, 0))
        box = pygame.Rect(0, 0, 600, 200)
        box.center = (WIDTH // 2, HEIGHT // 2)
        d.panel(s, box)
        d.label(s, "Controller recommended", (box.x + 28, box.y + 26), d.BRAND, 18)
        lines = ("Drive mode works best with a game controller (Xbox, PlayStation or similar).",
                 "If one is connected, move its stick or press a trigger.",
                 "The arrow keys work too: \u2190 \u2192 steer, \u2191 throttle, \u2193 brake.")
        for i, line in enumerate(lines):
            d.label(s, line, (box.x + 28, box.y + 66 + 22 * i), d.TEXT if i < 2 else d.DIM, 14)
        self.notice_ok.draw(s, (box.right - 28 - d.label_width("OK", 13) - 22, box.bottom - 46))

    # Draws the state of the wheel in the corner of the 3D view.
    def readout(self, s, rect):
        o = self.out
        rpm = self.q.omega * 60 / (2 * math.pi)
        lines = (("Ω", f"{self.q.omega:+.1f} rad/s  ({rpm:+.0f} rpm)"),
                 ("α", "–" if math.isnan(o.alpha) else f"{math.degrees(o.alpha):+.1f}°"),
                 ("s", "–" if math.isnan(o.s_x) else f"{o.s_x:+.3f}, {o.s_y:+.3f}"),
                 ("σ", "–" if math.isnan(o.sigma_x) else f"{o.sigma_x:+.3f}, {o.sigma_y:+.3f}"),
                 ("held", "yes (Ω = 0, friction holds)" if o.nu == 0 else "no"))
        y = rect.y + 10                                           # first line, live: is a game controller seen?
        on = self.controller() is not None
        pygame.draw.circle(s, d.PAD_ON if on else d.WARNING, (rect.x + 17, y + 8), 5)
        d.label(s, "controller detected" if on else "no controller detected", (rect.x + 28, y), d.TEXT if on else d.DIM, 13)
        for i, (name, value) in enumerate(lines):
            y = rect.y + 10 + 19 * (i + 1) + 4
            d.label(s, name, (rect.x + 12, y), d.DIM, 13)
            x = rect.x + (46 if name == "held" else 30)            # symbols are short: their values sit closer
            d.label(s, value, (x, y), d.WARNING if name == "held" and o.nu == 0 else d.TEXT, 13)

    # Draws one frame of the whole window.
    def frame(self):
        s = self.screen
        s.fill(d.BACKGROUND)
        self.top_bar(s)
        k = at_load(self.out.f_z, self.wheel.tyre)
        k_spring = k.c_s / k.d_relax
        h, r_0, r_e = loaded_radius(self.wheel), free_rolling_radius(self.wheel), self.wheel.tyre.r_e
        d.panel(s, pygame.Rect(10, 60, 620, 330))
        smear = self.q.omega * self.frame_dt                     # [rad] rim turn during one frame (motion blur)
        belt_smear = self.conditions.v * self.frame_dt           # [m]   belt travel during one frame
        self.rig3d.draw(s, self.out, self.delta, self.belt / r_e, self.spin, self.wheel.tyre.f_z0, smear, belt_smear / r_e, r_e,
                        self.show_values)
        self.readout(s, pygame.Rect(10, 60, 620, 330))
        self.values_button.draw(s, (622 - d.label_width("values", 13) - 22, 68), self.show_values)
        d.label(s, "Virtual Tire Test Rig · v1.6", (622, 368), d.TEXT, 12, "tr")   # name and version, white like the copyright
        side = pygame.Rect(10, 400, 305, 390)
        if self.zoom:
            contact_zoom(s, side, self.out, k_spring, h, r_0, r_e, self.wheel.tyre.f_z0)
        else:
            side_view(s, side, self.out, self.q.omega, self.t_d, self.t_b, k_spring,
                      h, r_0, r_e, self.belt, self.spin, self.wheel.tyre.f_z0, smear, belt_smear, self.show_values)
        top_view(s, pygame.Rect(325, 400, 305, 390), self.out, self.delta, k_spring, r_e, self.belt, self.wheel.tyre.f_z0,
                 belt_smear, side_scale(390, r_e), self.show_values)
        self.zoom_button.draw(s, (side.right - 8 - d.label_width("zoom", 13) - 22, side.y + 4), self.zoom)
        self.inputs(s, pygame.Rect(10, 800, 620, 90))
        right = pygame.Rect(640, 60, WIDTH - 650, HEIGHT - 70)
        if self.view.selected == "Plots":
            self.plots.draw(s, right, self.out, self.q, r_0, k)
        elif self.view.selected == "Transient":
            self.transient.draw(s, right, self.out, self.q, k, list(self.history))
        else:
            self.forces.draw(s, right, self.out, self.out.wheel.t_net, self.wheel.m_w * G, self.wheel.tyre.f_z0,
                             torque_limit(self.conditions, self.wheel), self.show_values)
        if self.notice:
            self.draw_notice(s)
        size = self.window.get_size()
        if size == (WIDTH, HEIGHT):
            self.window.blit(s, (0, 0))
        else:
            pygame.transform.smoothscale(s, size, self.window)
        pygame.display.flip()

    # Returns nothing; main loop at 60 frames per second until the window closes.
    def run(self):
        self.advance(0.0)
        running = True
        while running:
            frame_dt = self.clock.tick(60) / 1000.0
            running = self.events()
            self.drive(frame_dt)
            self.advance(frame_dt)
            self.frame()
        pygame.quit()


# Returns nothing; opens nicolasromanella.com in a new browser tab (web build) or in the default browser.
def open_site():
    try:
        import platform as web                                   # pygbag replaces platform with the browser bridge
        web.window.open(SITE_URL, "_blank")
    except Exception:
        import webbrowser
        webbrowser.open(SITE_URL)
