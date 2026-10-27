"""Per-evaluation density; isolated between generator worker threads."""
from contextlib import contextmanager
from threading import local
_state=local()
def current_density():return getattr(_state,'value',1)
@contextmanager
def density_scope(value):
    value=int(value)
    if value<1:raise ValueError('Density must be a positive integer.')
    previous=current_density();_state.value=value
    try:yield
    finally:_state.value=previous
