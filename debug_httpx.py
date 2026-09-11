from backend.app.services.local_llm_startup import httpx, _ORIGINAL_GET
print("Is patched:", httpx.get is not _ORIGINAL_GET)
