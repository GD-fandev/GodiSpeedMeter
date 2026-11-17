"""Dedicated capture producer and independent ordered HUD/OCR consumer."""
from dataclasses import dataclass, field
import math
import queue
import threading
import time
from diagnostics import Diagnostics
from pipeline import FrameBuffer, CoordinateCache, TimedReader, DigitFilter


class HeaderView:
    """Expose client dimensions to GodiNavi's header validator without a full frame."""
    def __init__(self, header, size):
        self.header = header
        self.width, self.height = size

    def crop(self, box):
        return self.header.crop(box)


@dataclass
class Session:
    request: int
    timeout: float
    token: tuple
    geometry: dict
    header_rect: tuple
    coordinate_box: tuple
    stream: FrameBuffer = field(default_factory=FrameBuffer)
    cancelled: threading.Event = field(default_factory=threading.Event)
    failure: str = ''
    finished: bool = False
    latest_header: object = None
    hud_captured_at: float = 0
    digit_filter: DigitFilter = field(default_factory=DigitFilter)
    captures: int = 0
    previous_capture: float | None = None
    gap_sum: float = 0
    max_gap_ms: float = 0
    diagnostics: Diagnostics = field(default_factory=Diagnostics)


class Engine:
    def __init__(self, model_root, events):
        self.model_root = model_root
        self.events = events
        self.commands = queue.Queue()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.session = None
        self.threads = [threading.Thread(target=self._recognize, daemon=True),
                        threading.Thread(target=self._capture, daemon=True)]
        for thread in self.threads:
            thread.start()

    def send(self, request, key, **values):
        self.events.put((request, key, values))

    def close(self):
        self.stop.set()
        if self.session:
            self.session.cancelled.set()
        for thread in self.threads:
            thread.join(timeout=2)

    def _new_session(self, request, timeout, token, geometry):
        _,rect,box = token
        size = (rect[2]-rect[0],rect[3]-rect[1])
        sx = geometry['scale']*size[0]/geometry['render_size'][0]
        sy = geometry['scale']*size[1]/geometry['render_size'][1]
        # Both native header sprites plus 2px tolerance; no map-name OCR.
        w,h = min(size[0],math.ceil(322*sx)+2),min(size[1],math.ceil(47*sy)+2)
        header = (rect[0],rect[1],rect[0]+w,rect[1]+h)
        relative = (box[0]-rect[0],box[1]-rect[1],box[2]-rect[0],box[3]-rect[1])
        return Session(request,timeout,token,geometry,header,relative)

    def _capture(self):
        capture = None
        request = 0
        try:
            from desktop_capture import DesktopCapture, FrameNotReady
            from auto_coordinates import AutoCoordinates
            capture = DesktopCapture()
            locator = AutoCoordinates(capture)
            armed = False
            timeout, delay = .7, 0
            while not self.stop.is_set():
                try:
                    command = self.commands.get(timeout=.05 if not armed else 0)
                    request,action,*options = command
                    if self.session:
                        self.session.cancelled.set()
                    self.session = None
                    locator.reset()
                    armed = action == 'start'
                    if armed:
                        timeout,delay = options
                    self.send(request,'status',code='searching' if armed else 'cancelled')
                except queue.Empty:
                    pass
                if not armed or not self.ready.is_set():
                    self.stop.wait(.005)
                    continue
                session = self.session
                if session and session.finished:
                    session.cancelled.set()
                    self.session = None
                    armed = False
                    continue
                if session and session.failure:
                    session.cancelled.set()
                    self.session = None
                    locator.reset()
                    self.send(request,'discarded',reason=session.failure,diagnostics=session.diagnostics.snapshot(session.stream.high_water))
                    self.send(request,'status',code=session.failure)
                    # Never quietly average through lost data or a changed HUD.
                    if session.failure in ('overflow','reader_error'):
                        armed=False
                    self.stop.wait(.15)
                    continue
                try:
                    if session is None:
                        token = locator.locate()
                        if token is None:
                            self.send(request,'status',code=locator.reason)
                            self.stop.wait(.1)
                            continue
                        session = self._new_session(request,timeout,token,dict(locator.geometry))
                        self.session = session
                        self.send(request,'status',code='tracking')
                    if not locator.unchanged(session.token):
                        session.failure = 'window_changed'
                        continue
                    # Only the coordinate rectangle is captured at full speed.
                    # HUD evidence is refreshed independently at 5 Hz.
                    if time.perf_counter()-session.hud_captured_at >= .2:
                        session.latest_header,_ = capture.capture_client(session.header_rect)
                        session.hud_captured_at = time.perf_counter()
                    coordinate,_ = capture.capture_client(session.token[2])
                    captured = time.perf_counter_ns()/1_000_000_000
                    if not locator.unchanged(session.token):
                        session.failure = 'window_changed'
                        continue
                    if session.previous_capture is not None:
                        gap = captured-session.previous_capture
                        session.gap_sum += gap
                        session.max_gap_ms = max(session.max_gap_ms,gap*1000)
                    session.diagnostics.capture(captured)
                    session.previous_capture = captured
                    session.captures += 1
                    # Only normalized coordinate strokes enter the ordered OCR queue.
                    session.stream.offer(session.digit_filter.prepare(coordinate),captured)
                    if delay:
                        self.stop.wait(delay)
                except FrameNotReady:
                    self.stop.wait(.0005)
                    continue
                except BufferError:
                    if session:
                        session.failure = 'overflow'
                except Exception as exc:
                    if session:
                        session.cancelled.set()
                    self.session = None
                    locator.reset()
                    self.send(request,'status',code='capture_error',detail=str(exc))
                    self.stop.wait(.25)
        except Exception as exc:
            self.send(request,'fatal',detail=str(exc))
        finally:
            if capture:
                capture.close()

    def _recognize(self):
        try:
            from PIL import Image
            from paddle_ocr_backend import PaddleOcrBackend
            from auto_ui.geometry import header_errors
            ocr = PaddleOcrBackend(self.model_root)
            ocr.recognize_coordinates(Image.new('RGB',(160,40)))
            cache = CoordinateCache(ocr.recognize_coordinates)
            self.ready.set()
            self.send(0,'ready')
            active = reader = None
            last_ui = 0
            checked_at = 0
            while not self.stop.is_set():
                session = self.session
                if session is None or session.cancelled.is_set() or session.failure or session.finished:
                    self.stop.wait(.005)
                    continue
                if active is not session:
                    active = session
                    reader = TimedReader(session.timeout,cache)
                    checked_at = 0
                frame = session.stream.take()
                if frame is None:
                    continue
                try:
                    now = time.perf_counter()
                    # HUD validation consumes a latest-only snapshot, never the OCR FIFO.
                    # Its animation/background changes must not create coordinate jobs.
                    if now-checked_at >= .1:
                        rect=session.token[1]
                        errors=header_errors(HeaderView(session.latest_header,(rect[2]-rect[0],rect[3]-rect[1])),session.geometry)
                        if max(errors) > .16 or sum(errors) > .23:
                            session.failure='no_hud'
                            continue
                        checked_at=now
                    calls_before=cache.calls
                    reader.accept(frame.image,frame.first_at,frame.last_at)
                    session.diagnostics.processed(frame.first_at,time.perf_counter(),cache.last_ocr_ms,
                        cache.calls>calls_before,reader.point is not None,len(session.stream))
                    if session.cancelled.is_set() or session.failure:
                        continue
                    m=reader.measurement
                    now=time.perf_counter()
                    if now-last_ui >= .1:
                        self.send(session.request,'live',point=reader.point,
                                  capture_ms=session.gap_sum/max(1,session.captures-1)*1000,
                                  max_gap_ms=session.max_gap_ms,ocr_ms=cache.last_ocr_ms,
                                  backlog=len(session.stream),lag_ms=(now-frame.last_at)*1000,
                                  hits=cache.hits,calls=cache.calls,intervals=len(m.intervals))
                        last_ui=now
                    if m.done:
                        self.send(session.request,'done',measurement=m,
                                  diagnostics=session.diagnostics.snapshot(session.stream.high_water))
                        session.finished=True
                except ValueError as exc:
                    session.failure=str(exc) if str(exc)=='unreadable' else 'reader_error'
                except Exception:
                    session.failure='reader_error'
        except Exception as exc:
            self.send(0,'fatal',detail=str(exc))
