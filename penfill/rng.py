"""Random-source abstraction for the samplers.

Samplers need only a handful of methods.  ``RandomLike`` captures that subset so
both ``random.Random`` and ``VskRandom`` (vsketch's seeded stream) qualify.
"""
from __future__ import annotations

from typing import Protocol, Sequence, TypeVar

_T = TypeVar("_T")


class RandomLike(Protocol):
    def random(self) -> float: ...
    def uniform(self, a: float, b: float) -> float: ...
    def randint(self, a: int, b: int) -> int: ...
    def choice(self, seq: Sequence[_T]) -> _T: ...


class VskRandom:
    """Adapt ``vsk.random`` to RandomLike, so fills draw from vsketch's seeded
    stream (``vsk.randomSeed``) instead of a separate generator.
    """

    def __init__(self, vsk):
        self._vsk = vsk

    def random(self) -> float:
        return self._vsk.random(1)

    def uniform(self, a: float, b: float) -> float:
        return self._vsk.random(a, b)

    def randint(self, a: int, b: int) -> int:
        return int(self._vsk.random(a, b + 1))

    def choice(self, seq):
        return seq[int(self._vsk.random(len(seq)))]
