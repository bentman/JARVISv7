from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.app.cache.keys import NS_RETRIEVAL
from backend.app.cache.manager import CacheManager
from backend.app.memory.episodic import EpisodicMemory
from backend.app.memory.retrieval import RetrievalManager
from backend.tests.conftest import SKIP_UNLESS_LIVE


def _seed_episodic_entry(base_dir: Path, session_id: str, turn_id: str, transcript: str, response_text: str) -> None:
    session_dir = base_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / f"{turn_id}.json").write_text(
        (
            "{\n"
            f'  "turn_id": "{turn_id}",\n'
            f'  "session_id": "{session_id}",\n'
            '  "session_started_at": "2026-01-01T00:00:00+00:00",\n'
            f'  "transcript": "{transcript}",\n'
            f'  "response_text": "{response_text}",\n'
            '  "tools_invoked": [],\n'
            '  "written_at": "2026-01-01T00:00:00+00:00"\n'
            "}\n"
        ),
        encoding="utf-8",
    )


@pytest.mark.live
@pytest.mark.requires_docker
@pytest.mark.requires_redis
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_retrieval_cache_hit_returns_same_results_as_miss(tmp_path: Path) -> None:
    episodic = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
    manager = RetrievalManager()
    cache = CacheManager()
    if not cache.is_available():
        pytest.skip("Redis unavailable")

    _seed_episodic_entry(
        base_dir=tmp_path / "episodic",
        session_id="live-cache-session",
        turn_id="live-cache-turn",
        transcript="cache proof transcript",
        response_text="cache proof response",
    )

    key = manager._cache_key("cache proof", 3)
    cache.delete(key)

    miss = manager.retrieve(query="cache proof", n=3, cache_manager=cache, episodic=episodic)
    cached_value = cache.get(key)
    hit = manager.retrieve(query="cache proof", n=3, cache_manager=cache, episodic=episodic)

    assert key.startswith(f"{NS_RETRIEVAL}:keyword:")
    assert cached_value is not None
    assert len(miss) > 0
    assert len(hit) == len(miss)
    assert [(f.turn_id, f.session_id, f.content) for f in hit] == [(f.turn_id, f.session_id, f.content) for f in miss]


@pytest.mark.live
@pytest.mark.requires_docker
@pytest.mark.requires_redis
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_retrieval_falls_back_to_disk_when_redis_stopped(tmp_path: Path) -> None:
    episodic = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
    manager = RetrievalManager()
    cache = CacheManager()
    if not cache.is_available():
        pytest.skip("Redis unavailable")

    _seed_episodic_entry(
        base_dir=tmp_path / "episodic",
        session_id="live-fallback-session",
        turn_id="live-fallback-turn",
        transcript="fallback transcript",
        response_text="fallback response",
    )

    stopped = False
    try:
        stop = subprocess.run(["docker", "stop", "jarvisv7-redis"], capture_output=True, text=True, check=False)
        if stop.returncode != 0:
            pytest.skip(f"Unable to stop Redis container: {stop.stdout.strip()} {stop.stderr.strip()}")
        stopped = True

        facts = manager.retrieve(query="fallback", n=3, cache_manager=cache, episodic=episodic)
        assert len(facts) > 0
        assert facts[0].turn_id == "live-fallback-turn"
    finally:
        if stopped:
            subprocess.run(["docker", "start", "jarvisv7-redis"], capture_output=True, text=True, check=False)
