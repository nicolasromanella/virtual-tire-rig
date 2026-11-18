# =============================================================================
# THEME (extra, not part of the rig)
# Hidden: three clicks on Reset within 1.5 s turn every colour towards pink,
# three more turn it back. main.py loads it only if this file exists; nothing
# else in rig/, interface/ or tests/ knows about it. Delete this file and it is gone.
# =============================================================================

import colorsys
import inspect
import time

from interface import app as app_module, draw, plots, views, widgets
from interface.app import App

MODULES = (draw, views, plots, widgets, app_module)
STRENGTH = 0.5                  # [-] share of pink mixed into every colour
CLICKS, WINDOW = 3, 1.5         # three clicks on Reset within 1.5 s


# Returns True if value looks like an RGB colour.
def is_colour(value) -> bool:
    return isinstance(value, tuple) and len(value) == 3 and all(isinstance(c, int) and 0 <= c <= 255 for c in value)


# Returns the pink version of an RGB colour: hue folded into magenta-pink, brightness kept.
def pink(colour):
    r, g, b = (c / 255.0 for c in colour)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.15:                                                   # greys, background, text: tinted pink
        h, s = 0.93, 0.25 + 0.2 * (1.0 - v)
    else:                                                          # colours: different pinks, still told apart
        h, s = 0.80 + 0.17 * h, max(s, 0.55)
    full = tuple(int(255 * c) for c in colorsys.hsv_to_rgb(h % 1.0, s, max(v, 0.08)))
    return tuple(int(o + STRENGTH * (p - o)) for o, p in zip(colour, full))


# Returns every (owner, name) holding a colour: module constants and colour defaults of functions.
def colour_slots():
    slots = []
    for module in MODULES:
        for name, value in list(vars(module).items()):
            if is_colour(value):
                slots.append((module, name, value))
            functions = [value] if inspect.isfunction(value) else (
                [f for f in vars(value).values() if inspect.isfunction(f)] if inspect.isclass(value) else [])
            for f in functions:
                if f.__defaults__ and any(is_colour(x) for x in f.__defaults__) and f.__module__ == module.__name__:
                    slots.append((f, "__defaults__", f.__defaults__))
    return slots


SLOTS = colour_slots()


# Returns nothing; switches every colour slot to pink (on) or back to the original (off).
def paint(on: bool):
    for owner, name, original in SLOTS:
        if name == "__defaults__":
            owner.__defaults__ = tuple(pink(x) if on and is_colour(x) else x for x in original)
        else:
            setattr(owner, name, pink(original) if on else original)


class ThemedApp(App):
    # Returns nothing; the normal app that counts the clicks on Reset.
    def __init__(self):
        self.themed, self.reset_clicks = False, []
        super().__init__()

    # Returns nothing; normal clicks, and three quick clicks on Reset switch the pink colours.
    def click(self, pos):
        if self.reset_button.click(pos):
            now = time.monotonic()
            self.reset_clicks = [t for t in self.reset_clicks if now - t < WINDOW] + [now]
            if len(self.reset_clicks) >= CLICKS:
                self.themed, self.reset_clicks = not self.themed, []
                paint(self.themed)
        super().click(pos)
