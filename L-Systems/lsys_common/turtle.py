"""Pure-numpy L-system rewriting and turtle interpretation (no vsketch needed).

Symbols: Draw symbols draw a unit step, ``+``/``-`` turn by +/-turn_angle,
``[``/``]`` push/pop the turtle, ``*`` applies ``transform_scale``,
``#``/``!`` raise/lower the stroke weight (min 1), ``'``/``"`` raise/lower the
colour index. A move symbol advances without drawing.
"""
from typing import Callable, Dict, List, Tuple

import numpy as np

# ((x0, y0), (x1, y1), stroke weight, colour index)
Segment = Tuple[Tuple[float, float], Tuple[float, float], int, int]


def translate(dx, dy):
    return np.array([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]])


def scale(s):
    return np.array([[s, 0.0, 0.0], [0.0, s, 0.0], [0.0, 0.0, 1.0]])


def rotate(degrees):
    theta = np.radians(degrees)
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def expand(axiom: str, rules: Dict[str, str], iterations: int) -> str:
    """Apply the rewrite ``rules`` {predecessor char: successor} `iterations` times."""
    state = axiom
    for _ in range(iterations):
        state = "".join(rules.get(t, t) for t in state)
    return state


def turtle_segments(
    state: str,
    *,
    draw: str,
    move: str = "",
    turn_angle: float,
    length_scale: float = 1.0,
    transform_scale: float = 1.0,
    angle_std: float = 0.0,
    length_std: float = 0.0,
    gauss: Callable[[], float] = lambda: 0.0,
    weight: int = 1,
    color: int = 0,
) -> List[Segment]:
    """Walk the turtle over `state`; `length_scale` is folded into the root
    matrix, so segments come out in the caller's length unit. `gauss` supplies
    standard-normal samples for the angle/length jitter."""
    matrix = scale(length_scale)
    weight = max(int(weight), 1)
    stack = []
    segments: List[Segment] = []
    for t in state:
        if t in draw:
            dist = 1 + gauss() * length_std
            p0 = matrix @ np.array([0.0, 0.0, 1.0])
            p1 = matrix @ np.array([0.0, dist, 1.0])
            segments.append(((p0[0], p0[1]), (p1[0], p1[1]), weight, color))
            matrix = matrix @ translate(0, dist)
        elif t == "+":
            matrix = matrix @ rotate(turn_angle + gauss() * angle_std)
        elif t == "-":
            matrix = matrix @ rotate(-turn_angle + gauss() * angle_std)
        elif move and t in move:
            matrix = matrix @ translate(0, 1 + gauss() * length_std)
        elif t == "[":
            stack.append((matrix.copy(), weight, color))
        elif t == "]":
            matrix, weight, color = stack.pop()
        elif t == "*":
            matrix = matrix @ scale(transform_scale)
        elif t == "#":
            weight += 1
        elif t == "!":
            weight = max(weight - 1, 1)
        elif t == "'":
            color += 1
        elif t == '"':
            color -= 1
    return segments
