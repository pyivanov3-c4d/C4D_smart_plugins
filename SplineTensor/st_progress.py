"""Main-thread status bar bridge for threaded generator evaluation."""
import threading
import c4d
from c4d import plugins

# Development ID, distinct from the object plugin.
PROGRESS_ID = 1069999
_lock = threading.RLock()
_jobs = {}
_visible = False


def flush():
    global _visible
    if not c4d.threading.GeIsMainThread():
        return
    with _lock:
        state = next(reversed(_jobs.values()), None) if _jobs else None
    if state is None:
        if _visible:
            c4d.gui.StatusClear()
            _visible = False
        return
    percent, label, busy = state
    c4d.gui.StatusSetText('SplineTensor: ' + label)
    if busy:
        c4d.gui.StatusSetSpin()
    else:
        c4d.gui.StatusSetBar(percent)
    _visible = True


class Progress:
    def __init__(self):
        self.token = object()

    def stage(self, percent, label, busy=False):
        with _lock:
            _jobs[self.token] = (percent, label, busy)
        if c4d.threading.GeIsMainThread():
            flush()
        else:
            c4d.SpecialEventAdd(PROGRESS_ID)

    def close(self):
        with _lock:
            _jobs.pop(self.token, None)
        if c4d.threading.GeIsMainThread():
            flush()
        else:
            c4d.SpecialEventAdd(PROGRESS_ID)


class ProgressMessages(plugins.MessageData):
    def GetTimer(self):
        return 100

    def CoreMessage(self, message, data):
        flush()
        return True


def register_progress():
    return plugins.RegisterMessagePlugin(PROGRESS_ID, 'SplineTensor Progress', 0,
                                         ProgressMessages())
