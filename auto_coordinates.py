"""GodiNavi automatic window discovery and pixel-validated HUD layout."""
import time
from auto_ui.service import RegionService
from auto_ui.window_info import window_context
from game_windows import target, u


class AutoCoordinates:
    def __init__(self, capture):
        self.service = RegionService(lambda rect: capture.capture_client(rect)[0])
        self.window = None
        self.context = None
        self.box = None
        self.checked_at = 0
        self.reason = "searching"
        self.geometry = None

    def reset(self):
        self.window = self.context = self.box = None
        self.geometry = None
        self.service.invalidate()

    def locate(self):
        if self.window is None:
            self.window = target()
            if self.window is None:
                self.reason = "no_game"
                return None
        hwnd = self.window['hwnd']
        context = window_context(hwnd)
        if not context or context['identity'] != (hwnd, self.window['pid']) or u.IsIconic(hwnd):
            self.reset()
            self.reason = "minimized"
            return None
        if u.GetForegroundWindow() != hwnd:
            self.box = None
            self.reason = "foreground"
            return None
        if context != self.context:
            self.box = None
            self.service.invalidate()
        now = time.perf_counter()
        if self.box is None or now-self.checked_at >= .1:
            layout = self.service.snapshot(hwnd, context['rect'])
            self.box = layout.bbox('coordinates')
            self.geometry = layout.geometry
            self.checked_at = now
        self.context = context
        if self.box is None:
            self.reason = "no_hud"
        return (context['identity'], context['rect'], self.box) if self.box else None

    def unchanged(self, token):
        # Discard samples captured across window movement, resize or focus loss.
        context = window_context(self.window['hwnd']) if self.window else None
        return bool(context and context['identity'] == token[0]
                    and context['rect'] == token[1]
                    and not u.IsIconic(self.window['hwnd'])
                    and u.GetForegroundWindow() == self.window['hwnd'])
