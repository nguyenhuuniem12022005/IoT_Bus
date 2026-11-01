"""Kiểm tra trung vị, chống nhấp nháy và reset."""
import pytest
from vision_node.counter import StableCounter


def test_spike_and_sustained_change() -> None:
    counter = StableCounter()
    assert [counter.update(n) for n in [0, 0, 0, 0, 0, 4, 0, 0]] == [0] * 8
    for _ in range(5):
        counter.update(0)
    assert [counter.update(n) for n in [2, 2, 2, 2]] == [0, 0, 0, 2]
    assert [counter.update(n) for n in [0, 0, 0, 0]] == [2, 2, 2, 0]
    counter.reset()
    assert counter.value == 0 and not counter.history


def test_consecutive_candidate_required() -> None:
    counter = StableCounter(window=1, min_change_frames=2)
    assert [counter.update(n) for n in [1, 2, 1, 2, 2]] == [0, 0, 0, 0, 2]


@pytest.mark.parametrize('value', [-1, True, 1.5])
def test_reject_invalid_count(value: object) -> None:
    with pytest.raises(ValueError):
        StableCounter().update(value)


@pytest.mark.parametrize('window,frames', [(0, 2), (5, 0), (True, 2)])
def test_invalid_parameters(window: int, frames: int) -> None:
    with pytest.raises(ValueError):
        StableCounter(window, frames)
