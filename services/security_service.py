"""V6.17 — protecoes leves sem dependencia externa."""
from collections import defaultdict, deque
from threading import Lock
import time

_hits=defaultdict(deque); _lock=Lock()

def allow(key:str, limit:int, window_seconds:int)->bool:
    now=time.monotonic(); cutoff=now-window_seconds
    with _lock:
        q=_hits[key]
        while q and q[0] < cutoff: q.popleft()
        if len(q)>=limit: return False
        q.append(now); return True

def reset_for_tests():
    with _lock: _hits.clear()
