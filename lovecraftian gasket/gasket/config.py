"""Seed JSON schema, loader and validation - the single source of truth.

Both hand-edits and the (future) optimizer write the *same* schema; the packing
engine consumes the parsed :class:`Config`.  JSON has no complex type and must
stay human-editable, so centres are 2-element ``[x, y]`` arrays (mm) and are
converted to ``complex`` at this boundary.

Schema (see ``seeds/*.json`` for examples)::

    {
      "paper":  "a4",                 # only a4 supported for now
      "margin": 20,                   # mm, drawable inset on every side
      "landscape": false,
      "boundary": {                   # enclosing circle, negative curvature
        "type": "circle", "z": [105, 148.5], "r": 132, "inside": true
      },
      "seeds": [
        {"id": "s0", "z": [80,110], "r": 45, "fixed": true,  "feature": "eye"},
        ...
      ],
      "tangencies": [["s0","s1"], ["s0","outer"], ...],
      "search": {"free_ids": ["s1"], "bounds": {"r": [25,55]},
                 "r_min": 1.5, "max_gen_in_objective": 4}
    }

``"outer"`` in a tangency pair refers to the boundary circle.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from geometry import Circle
from packing import Rect, a4_clip


@dataclass
class Seed:
    id: str
    z: complex
    r: float
    fixed: bool = False
    feature: str = "eye"

    def to_circle(self, *, inside: bool = False, depth: int = 0) -> Circle:
        return Circle.from_center(self.z, self.r, inside=inside, depth=depth,
                                  feature=self.feature)


@dataclass
class Config:
    clip: Rect
    boundary: Seed | None          # enclosing circle, or None to pack seed gaps only
    seeds: list[Seed]
    tangencies: list[tuple[str, str]]
    search: dict = field(default_factory=dict)
    landscape: bool = False

    # -- convenience views ---------------------------------------------------
    def by_id(self) -> dict[str, Seed]:
        return {s.id: s for s in self.seeds}

    def outer_circle(self) -> Circle | None:
        return self.boundary.to_circle(inside=True) if self.boundary else None

    def seed_circles(self) -> list[Circle]:
        return [s.to_circle() for s in self.seeds]

    def free_ids(self) -> list[str]:
        return list(self.search.get("free_ids", []))

    @property
    def r_min(self) -> float:
        return float(self.search.get("r_min", 1.5))


def _z(arr) -> complex:
    return complex(float(arr[0]), float(arr[1]))


def load(path: str | Path) -> Config:
    data = json.loads(Path(path).read_text())

    paper = data.get("paper", "a4")
    if paper != "a4":
        raise ValueError(f"only paper='a4' is supported (got {paper!r})")
    margin = float(data.get("margin", 20.0))
    landscape = bool(data.get("landscape", False))
    clip = a4_clip(margin=margin, landscape=landscape)

    # Boundary is optional: omit it (or set "type": "none") to pack only the gaps
    # between mutually tangent seed circles - a freer, non-circular layout.
    b = data.get("boundary")
    if b is None or b.get("type") == "none":
        boundary = None
    elif b.get("type", "circle") != "circle":
        raise ValueError("boundary.type must be 'circle' or 'none' (lines are "
                         "handled via the margin clip, not Descartes)")
    else:
        boundary = Seed(id="outer", z=_z(b["z"]), r=float(b["r"]),
                        fixed=True, feature="boundary")

    seeds = [Seed(id=s["id"], z=_z(s["z"]), r=float(s["r"]),
                  fixed=bool(s.get("fixed", False)),
                  feature=s.get("feature", "eye"))
             for s in data["seeds"]]

    tangencies = [tuple(pair) for pair in data.get("tangencies", [])]
    search = dict(data.get("search", {}))

    cfg = Config(clip=clip, boundary=boundary, seeds=seeds,
                 tangencies=tangencies, search=search, landscape=landscape)
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    ids = {s.id for s in cfg.seeds}
    if len(ids) != len(cfg.seeds):
        raise ValueError("duplicate seed id")
    if "outer" in ids:
        raise ValueError("'outer' is reserved for the boundary circle")

    # tangency references resolve ("outer" only when a boundary exists)
    valid = ids | ({"outer"} if cfg.boundary else set())
    for a, b in cfg.tangencies:
        for ref in (a, b):
            if ref not in valid:
                extra = "" if cfg.boundary else " (no boundary: 'outer' is invalid)"
                raise ValueError(f"tangency references unknown id {ref!r}{extra}")

    # fixed (per-seed) and free_ids (flat) must be consistent: a free seed is
    # not fixed and vice-versa.  Redundant on purpose (one documents intent, the
    # other drives the optimizer) - so verify they agree.
    free = set(cfg.free_ids())
    unknown = free - ids
    if unknown:
        raise ValueError(f"free_ids references unknown seeds: {sorted(unknown)}")
    for s in cfg.seeds:
        if s.fixed and s.id in free:
            raise ValueError(f"seed {s.id!r} is both fixed and in free_ids")
        if (not s.fixed) and free and s.id not in free:
            raise ValueError(
                f"seed {s.id!r} is not fixed yet absent from free_ids; mark it "
                "fixed=true or add it to search.free_ids")

    # Seeds ideally sit inside the drawable clip, but a seed poking past the
    # margins is allowed - it is simply discarded at render (esp. with no
    # boundary, where snapping can push seeds outward).  Warn rather than fail.
    outside = [s.id for s in cfg.seeds
               if not cfg.clip.contains_disk(s.to_circle(), slack=1e-6)]
    if outside:
        print(f"warning: seeds extend past the margin clip (will be discarded "
              f"at render): {outside}", file=sys.stderr)


if __name__ == "__main__":
    import sys
    cfg = load(sys.argv[1] if len(sys.argv) > 1 else "seeds/irregular_frame.json")
    print("clip:", cfg.clip)
    print("boundary:", cfg.outer_circle())
    for s in cfg.seeds:
        print(f"  {s.id}: z={s.z}, r={s.r}, fixed={s.fixed}, feature={s.feature}")
    print("tangencies:", cfg.tangencies)
    print("CONFIG LOADS AND VALIDATES")
