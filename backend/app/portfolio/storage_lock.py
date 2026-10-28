import threading

from app.data_sync.storage import ProcessRLock

_locks = {}
_guard = threading.Lock()


def portfolio_lock(root):
    key = str(root.resolve())
    with _guard:
        if key not in _locks:
            _locks[key] = ProcessRLock(lambda: root / "account-write.lock")
        return _locks[key]
