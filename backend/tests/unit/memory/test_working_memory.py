from __future__ import annotations

from backend.app.memory.working import WorkingMemory
from backend.app.memory.write_policy import WritePolicy


def test_working_memory_bounded_by_max_entries():
    memory = WorkingMemory(max_entries=2)

    memory.add("one")
    memory.add("two")
    memory.add("three")

    assert memory.as_list() == ["two", "three"]


def test_working_memory_drops_oldest_on_overflow():
    memory = WorkingMemory(max_entries=1)

    memory.add("old")
    memory.add("new")

    assert memory.as_list() == ["new"]


def test_working_memory_clear_empties_list():
    memory = WorkingMemory()
    memory.add("entry")

    memory.clear()

    assert memory.as_list() == []


def test_working_memory_returns_copy_not_internal_list():
    memory = WorkingMemory()
    memory.add("entry")
    returned = memory.as_list()

    returned.append("mutated")


    assert memory.as_list() == ["entry"]


def test_write_policy_defaults_enable_bounded_working_memory():
    policy = WritePolicy()

    assert policy.write_to_working_memory is True
    assert policy.max_working_memory_entries == 10