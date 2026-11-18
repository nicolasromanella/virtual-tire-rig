# =============================================================================
# WIDGETS
# Minimal controls drawn with Pygame: segmented switch, button, number box, slider.
# Each widget handles its own mouse and keyboard events.
# =============================================================================

import pygame

from interface import draw as d


# =============================================================================
# SEGMENTED SWITCH
# A row of options; one is selected.
# =============================================================================

class Switch:
    # Returns nothing; one option selected out of options.
    def __init__(self, options: list, selected: str, size: int = 13):
        self.options, self.selected, self.size = options, selected, size
        self.rects = []

    # Returns the total width [px] of the switch.
    def width(self) -> int:
        return sum(d.label_width(o, self.size) + 20 for o in self.options)

    # Draws the switch with its top-left corner at pos; returns its rect.
    def draw(self, surface, pos) -> pygame.Rect:
        x, y = pos
        h = self.size + 12
        self.rects = []
        for option in self.options:
            w = d.label_width(option, self.size) + 20
            r = pygame.Rect(x, y, w, h)
            hover = option != self.selected and r.collidepoint(d.MOUSE)    # another option under the mouse
            if option == self.selected or hover:
                pygame.draw.rect(surface, d.PANEL_EDGE if option == self.selected else d.HOVER, r, border_radius=4)
            d.label(surface, option, r.center, d.TEXT if option == self.selected or hover else d.DIM, self.size, "c")
            self.rects.append((r, option))
            x += w
        outline = pygame.Rect(pos[0], y, x - pos[0], h)
        pygame.draw.rect(surface, d.PANEL_EDGE, outline, 1, border_radius=4)
        return outline

    # Returns True if a click selected another option.
    def click(self, point) -> bool:
        for r, option in self.rects:
            if r.collidepoint(point) and option != self.selected:
                self.selected = option
                return True
        return False


# =============================================================================
# BUTTON
# =============================================================================

class Button:
    # Returns nothing; rect is set at the first draw.
    def __init__(self, text: str, size: int = 13, outline: bool = True):
        self.text, self.size, self.rect, self.outline = text, size, pygame.Rect(0, 0, 0, 0), outline

    # Draws the button at pos, filled when active, height [px] by default from the text size; returns its rect.
    def draw(self, surface, pos, active: bool = False, height: int = 0) -> pygame.Rect:
        w = d.label_width(self.text, self.size) + 22
        self.rect = pygame.Rect(pos[0], pos[1], w, height or self.size + 12)
        hover = self.rect.collidepoint(d.MOUSE)                  # lights up under the mouse
        if active or hover:
            pygame.draw.rect(surface, d.HOVER if hover else d.FIELD, self.rect, border_radius=4)
        if self.outline or active or hover:
            pygame.draw.rect(surface, d.TEXT if active or hover else d.AXIS, self.rect, 1, border_radius=4)
        d.label(surface, self.text, self.rect.center, d.TEXT, self.size, "c")
        return self.rect

    # Returns True if the point is on the button.
    def click(self, point) -> bool:
        return self.rect.collidepoint(point)


# =============================================================================
# NUMBER BOX
# Click to edit, type digits, Enter applies, Escape cancels.
# =============================================================================

class NumberBox:
    # Returns nothing; value shown with decimals, box wide enough for chars.
    def __init__(self, name: str, unit: str, value: float, decimals: int, chars: int = 6):
        self.name, self.unit, self.decimals, self.chars = name, unit, decimals, chars
        self.value, self.text, self.editing, self.error = value, "", False, False
        self.rect = pygame.Rect(0, 0, 0, 0)

    # Returns the text in the box: typed text while editing, else the value.
    def shown(self) -> str:
        return self.text if self.editing else f"{self.value:.{self.decimals}f}"

    # Draws name, box and unit at pos; with buttons (minus, plus) they touch the box on its two sides,
    # in the order name, minus, box, plus, unit; returns the total rect.
    def draw(self, surface, pos, size: int = 13, buttons=None) -> pygame.Rect:
        r_name = d.label(surface, self.name, (pos[0], pos[1] + 6), d.DIM, size)
        w = d.font(size).size("0" * self.chars)[0] + 12
        x = r_name.right + 6
        if buttons is not None:
            x = buttons[0].draw(surface, (x, pos[1]), height=size + 12).right - 1   # shared edge
        self.rect = pygame.Rect(x, pos[1], w, size + 12)
        pygame.draw.rect(surface, d.BACKGROUND, self.rect, border_radius=3)
        edge = d.WARNING if self.error else (d.TEXT if self.editing else d.AXIS)
        pygame.draw.rect(surface, edge, self.rect, 1, border_radius=3)
        d.label(surface, self.shown() + ("|" if self.editing else ""), (self.rect.x + 6, self.rect.y + 6), d.TEXT, size)
        x = self.rect.right
        if buttons is not None:
            x = buttons[1].draw(surface, (x - 1, pos[1]), height=size + 12).right
        r_unit = d.label(surface, self.unit, (x + 6, pos[1] + 6), d.DIM, size)
        return pygame.Rect(pos[0], pos[1], r_unit.right - pos[0], self.rect.h)

    # Starts editing if the click is on the box; returns True if it was.
    def click(self, point) -> bool:
        if self.rect.collidepoint(point):
            self.editing, self.text, self.error = True, "", False
            return True
        self.editing = False
        return False

    # Returns the typed value on Enter, None otherwise.
    def key(self, event):
        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
            self.editing = False
            try:
                return float(self.text.replace(",", "."))
            except ValueError:
                return None
        if event.key == pygame.K_ESCAPE:
            self.editing = False
        elif event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
        elif event.unicode and event.unicode in "0123456789.,-" and len(self.text) < self.chars:
            self.text += event.unicode
        return None


# =============================================================================
# SLIDER
# Horizontal track; drag the knob with the mouse. The owner decides when a
# dragged value is applied (while dragging or on release).
# =============================================================================

class Slider:
    # Returns nothing; range lo..hi, fill from the centre if centred.
    def __init__(self, lo: float, hi: float, value: float, centred: bool = False):
        self.lo, self.hi, self.value, self.centred = lo, hi, value, centred
        self.rect, self.dragging, self.enabled = pygame.Rect(0, 0, 0, 0), False, True

    # Returns the value at the screen x [px] of the track, within the range.
    def value_at(self, x: float) -> float:
        share = min(max((x - self.rect.x) / max(self.rect.w, 1), 0.0), 1.0)
        return self.lo + share * (self.hi - self.lo)

    # Draws track, filled part and knob in rect; returns rect.
    def draw(self, surface, rect: pygame.Rect, colour=d.TEXT) -> pygame.Rect:
        self.rect = pygame.Rect(rect)
        track = pygame.Rect(rect.x, rect.centery - 4, rect.w, 8)
        pygame.draw.rect(surface, d.FIELD, track, border_radius=4)
        share = (min(max(self.value, self.lo), self.hi) - self.lo) / (self.hi - self.lo)
        x = rect.x + share * rect.w
        start = rect.x + (-self.lo / (self.hi - self.lo)) * rect.w if self.centred else rect.x
        if self.centred:
            pygame.draw.line(surface, d.AXIS, (start, track.y - 3), (start, track.bottom + 3), 1)
        pygame.draw.rect(surface, colour, (min(start, x), track.y, max(abs(x - start), 2), 8), border_radius=4)
        if self.enabled:
            pygame.draw.circle(surface, d.TEXT if not self.dragging else d.POINT, (x, track.centery), 7)
            pygame.draw.circle(surface, d.BACKGROUND, (x, track.centery), 7, 1)
        return self.rect

    # Starts dragging if the point is on the slider; returns True if it is.
    def press(self, point) -> bool:
        if self.enabled and self.rect.inflate(10, 14).collidepoint(point):
            self.dragging = True
            self.value = self.value_at(point[0])
            return True
        return False

    # Returns the new value while dragging, None otherwise.
    def drag(self, point):
        if not self.dragging:
            return None
        self.value = self.value_at(point[0])
        return self.value

    # Ends dragging; returns True if the slider was being dragged.
    def release(self) -> bool:
        was, self.dragging = self.dragging, False
        return was
