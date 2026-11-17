"""Pure timing logic; timestamps refer to capture, not OCR completion."""
import re
from dataclasses import dataclass, field


def parse_coordinate(text):
    match = re.fullmatch(r"\s*\(?\s*(-?\d+)\s*[:,; ]\s*(-?\d+)\s*\)?\s*", text)
    return tuple(map(int, match.groups())) if match else None


@dataclass
class Measurement:
    timeout: float = .7
    previous: tuple | None = None
    changed_at: float | None = None
    direction: tuple | None = None
    intervals: list = field(default_factory=list)
    done: bool = False
    error: str = ""

    def observe(self, point, now):
        if self.done or point is None:
            return
        if self.previous is None:
            self.previous = point
            return
        if point == self.previous:
            if self.changed_at is not None and now-self.changed_at >= self.timeout:
                self.done = True
            return
        dx, dy = point[0]-self.previous[0], point[1]-self.previous[1]
        if dx and dy:
            self.error = "diagonal"
            self.done = True
            return
        direction = ((1 if dx > 0 else -1), 0) if dx else (0, (1 if dy > 0 else -1))
        if self.direction and direction != self.direction:
            self.error = "direction"
            self.done = True
            return
        if self.changed_at is not None:
            self.intervals.append(((now-self.changed_at)*1000, abs(dx)+abs(dy)))
        self.previous, self.changed_at, self.direction = point, now, direction

    @property
    def kept(self):
        return self.intervals[:-1]  # discard final transition interval

    @property
    def average_ms(self):
        data = self.kept
        return sum(t for t,n in data)/sum(n for t,n in data) if data else None
