class _Response:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self._payload = payload or {}
    def raise_for_status(self) -> None:
        return None
    def json(self) -> dict[str, object]:
        return self._payload

r = _Response()
print(r.status_code)
