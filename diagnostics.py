"""Per-attempt diagnostics and transparent heuristic review reasons."""
from dataclasses import dataclass, field
import threading
import statistics


@dataclass
class Diagnostics:
    lock: object = field(default_factory=threading.Lock)
    origin: float | None = None
    previous: float | None = None
    captures: int = 0
    gap_total_ms: float = 0
    max_gap_ms: float = 0
    max_lag_ms: float = 0
    max_ocr_ms: float = 0
    max_backlog: int = 0
    ocr_calls: int = 0
    ocr_failures: int = 0
    events: list = field(default_factory=list)

    def event(self, kind, at, value):
        self.events.append(dict(kind=kind,at_seconds=round(at-(self.origin if self.origin is not None else at),4),ms=round(value,4)))
        if len(self.events)>100:
            self.events.sort(key=lambda e:e['ms'],reverse=True)
            del self.events[100:]

    def capture(self, at):
        with self.lock:
            if self.origin is None: self.origin=at
            if self.previous is not None:
                gap=(at-self.previous)*1000
                self.gap_total_ms+=gap
                self.max_gap_ms=max(self.max_gap_ms,gap)
                if gap>=20: self.event('capture_gap',at,gap)
            self.previous=at
            self.captures+=1

    def processed(self, first_at, completed_at, ocr_ms, called, valid, backlog):
        with self.lock:
            lag=max(0,(completed_at-first_at)*1000)
            self.max_lag_ms=max(self.max_lag_ms,lag)
            self.max_backlog=max(self.max_backlog,backlog)
            if called:
                self.ocr_calls+=1
                self.max_ocr_ms=max(self.max_ocr_ms,ocr_ms)
                if not valid:self.ocr_failures+=1
            if lag>=100:self.event('processing_lag',first_at,lag)

    def snapshot(self, high_water=0):
        with self.lock:
            return dict(captures=self.captures,mean_gap_ms=self.gap_total_ms/max(1,self.captures-1),
                        max_gap_ms=self.max_gap_ms,max_lag_ms=self.max_lag_ms,max_ocr_ms=self.max_ocr_ms,
                        max_backlog=max(self.max_backlog,high_water),ocr_calls=self.ocr_calls,
                        ocr_failures=self.ocr_failures,scope='whole_observation_including_stop_wait',
                        events=sorted((dict(e) for e in self.events),key=lambda e:e['at_seconds']))


def review(average,cells,intervals,diagnostics,previous):
    reasons=[]
    if average is None:return ['invalid']
    if diagnostics is None:return ['no_diagnostics']
    gap=diagnostics.get('max_gap_ms',0)
    if gap>=average: reasons.append('capture_severe')
    elif gap>=50: reasons.append('capture_gap')
    if diagnostics.get('ocr_failures',0): reasons.append('ocr_failure')
    if any(n>1 for _,n in intervals): reasons.append('skipped_cells')
    if cells<20: reasons.append('short_run')
    if diagnostics.get('max_lag_ms',0)>=250: reasons.append('processing_lag')
    if len(previous)>=5:
        median=statistics.median(previous)
        mad=statistics.median(abs(x-median) for x in previous)
        if abs(average-median)>max(.5,median*.002,6*mad): reasons.append('outlier')
    return reasons
