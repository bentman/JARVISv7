from __future__ import annotations

import io
import zipfile


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()
