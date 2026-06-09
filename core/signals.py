"""Pure-Python Signal stub — drop-in for PySide6.QtCore.Signal."""


class Signal:
    """Minimal callback-list implementation with the same connect/emit/disconnect API as Qt."""

    def __init__(self, *_types):
        self._cbs: list = []

    def connect(self, cb) -> None:
        if cb not in self._cbs:
            self._cbs.append(cb)

    def disconnect(self, cb) -> None:
        try:
            self._cbs.remove(cb)
        except ValueError:
            pass

    def emit(self, *args) -> None:
        for cb in list(self._cbs):
            try:
                cb(*args)
            except Exception:
                pass
