"""Ordered capture timestamps, bounded frame buffering and exact-image OCR cache."""
from collections import OrderedDict, deque
from dataclasses import dataclass
import threading
import time
from measurement import Measurement, parse_coordinate
import numpy as np
import cv2
from PIL import Image


def digit_image(image):
    """Keep bright neutral digit strokes, not translucent HUD/background pixels."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    low, high = rgb.min(axis=2), rgb.max(axis=2)
    mask = ((low >= 180) & ((high-low) <= 65)).astype(np.uint8)
    mask[mask.sum(axis=1) > mask.shape[1]*.7, :] = 0
    mask[:, mask.sum(axis=0) > mask.shape[0]*.85] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(count, dtype=np.uint8)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= 3:
            keep[index] = 255
    return Image.fromarray(keep[labels]).convert("RGB")



class DigitFilter:
    """Ignore antialias/background shimmer; preserve definite stroke changes."""
    def __init__(self):
        self.foreground = self.background = self.image = None

    def prepare(self, image):
        rgb=np.asarray(image.convert('RGB'),dtype=np.uint8)
        low,high=rgb.min(axis=2),rgb.max(axis=2)
        foreground=(low>=200)&((high-low)<=65)
        background=(high<=160)|((high-low)>90)
        if self.image is not None and foreground.shape==self.foreground.shape:
            changed=np.any(foreground & self.background) or np.any(background & self.foreground)
            if not changed:
                return self.image
        self.foreground,self.background=foreground,background
        self.image=digit_image(image)
        return self.image


@dataclass
class Frame:
    image: object
    signature: bytes
    first_at: float
    last_at: float


class FrameBuffer:
    def __init__(self, capacity=128):
        self.capacity = capacity
        self.frames = deque()
        self.condition = threading.Condition()
        self.high_water = 0

    def offer(self, image, captured_at):
        signature = image.tobytes()
        with self.condition:
            if self.frames and self.frames[-1].signature == signature:
                self.frames[-1].last_at = captured_at
            else:
                if len(self.frames) >= self.capacity:
                    raise BufferError('overflow')
                self.frames.append(Frame(image, signature, captured_at, captured_at))
                self.high_water = max(self.high_water, len(self.frames))
            self.condition.notify()

    def take(self, timeout=.05):
        with self.condition:
            if not self.frames:
                self.condition.wait(timeout)
            return self.frames.popleft() if self.frames else None

    def __len__(self):
        with self.condition:
            return len(self.frames)


class CoordinateCache:
    def __init__(self, recognize, capacity=256):
        self.recognize = recognize
        self.capacity = capacity
        self.values = OrderedDict()
        self.hits = self.calls = 0
        self.last_ocr_ms = 0

    def read(self, image):
        key = (image.size, image.tobytes())
        if key in self.values:
            self.hits += 1
            self.values.move_to_end(key)
            return self.values[key]
        start = time.perf_counter()
        point = parse_coordinate(self.recognize(image))
        self.last_ocr_ms = (time.perf_counter()-start)*1000
        self.calls += 1
        if point is not None:
            self.values[key] = point
            if len(self.values) > self.capacity:
                self.values.popitem(last=False)
        return point


class TimedReader:
    def __init__(self, timeout, cache):
        self.measurement = Measurement(timeout)
        self.cache = cache
        self.last_valid = None
        self.point = None

    def accept(self, image, first_at, last_at):
        self.point = self.cache.read(image)
        if self.last_valid is None:
            self.last_valid = first_at
        if self.point is None:
            if last_at-self.last_valid > max(2, self.measurement.timeout*3):
                raise ValueError('unreadable')
            return
        self.last_valid = last_at
        # OCR completion/wall-clock time is deliberately never used here.
        self.measurement.observe(self.point, first_at)
        if last_at > first_at:
            self.measurement.observe(self.point, last_at)
