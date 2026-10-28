"""Thread-safe, coalesced status updates for Metaspline calculations."""
import threading
import time
import c4d

PROGRESS_ID = 1070002  # Local development ID, separate from the generator.
_lock = threading.RLock()
_jobs = {}
_pending = False
_displayed = None
_local = threading.local()


class Cancelled(Exception):
    pass


def current():
    return getattr(_local, 'job', None)


def flush():
    global _pending, _displayed
    if not c4d.threading.GeIsMainThread():return
    with _lock:
        _pending = False
        state = next(reversed(_jobs.values()), None) if _jobs else None
    if state == _displayed:return
    if state is None:
        if _displayed is not None:c4d.gui.StatusClear()
    else:
        label,percent=state
        c4d.gui.StatusSetText('Metaspline: '+label)
        if percent is None:c4d.gui.StatusSetSpin()
        else:c4d.gui.StatusSetBar(percent)
    _displayed=state


def _notify():
    global _pending
    if c4d.threading.GeIsMainThread():
        flush()
        return
    with _lock:
        if _pending:return
        _pending=True
    c4d.SpecialEventAdd(PROGRESS_ID)


class Progress:
    def __init__(self, thread=None):
        self.token=object();self.thread=thread
        self.previous=current();_local.job=self
        self.last=0.;self.label=None;self.closed=False

    def check(self):
        if self.thread is not None and self.thread.TestBreak():raise Cancelled()

    def stage(self, label, percent=None):
        self.check()
        now=time.monotonic()
        if label==self.label and now-self.last<.1:return
        self.label=label;self.last=now
        with _lock:_jobs[self.token]=(label,percent)
        _notify()

    def count(self, done, total, label):
        self.stage(label, max(0,min(100,100.*done/max(1,total))))

    def close(self):
        if self.closed:return
        self.closed=True
        _local.job=self.previous
        with _lock:
            existed=self.token in _jobs
            _jobs.pop(self.token,None)
        if existed:_notify()


def register_progress():
    class ProgressMessages(c4d.plugins.MessageData):
        def GetTimer(self):return 100
        def CoreMessage(self, message, data):
            flush()
            return True
    return c4d.plugins.RegisterMessagePlugin(PROGRESS_ID,'Metaspline Progress',0,ProgressMessages())
