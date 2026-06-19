"""Headless checks for the de-Blendered voxel pipeline (no Blender, no GUI).

Run: ``python test_voxels.py`` (needs numpy; the maze/voxel code is otherwise
dependency-free).
"""
import random

import numpy as np

from scipy import ndimage

from maze import Maze
from voxels import (PositionGrid, drop, flood_fill_3d,
                    _NEIGHBOR_KERNEL, _BELOW_KERNEL)


def _solid_grid(nx, ny, nz, floor_thickness=2):
    """A solid block of voxels with stable_z/floor_z set, for erosion tests."""
    g = PositionGrid(nx, ny, nz)
    g.stable_z = floor_thickness + 1
    g.floor_z = floor_thickness
    g.fill_box(0, nx, 0, ny, 0, nz)
    return g


def test_from_maze_nonempty():
    random.seed(7)
    m = Maze(13, 13)            # make_foundation needs a reasonably large maze
    m.gen_rooms()
    g = PositionGrid(8, 8, 8)
    g.fromMaze(m, room_size=12, wall_thickness=3, wall_height=18, floor_thickness=10)
    assert g.all_occupied_positions, "fromMaze produced no voxels"
    assert all(isinstance(v, int) and v >= 0 for p in g.all_occupied_positions for v in p)
    print(f"ok: fromMaze -> {len(g.all_occupied_positions)} voxels")


def test_flood_fill_connectivity():
    grid = np.zeros((3, 3, 4))
    grid[1, 1, 0] = 1          # floor voxel (connected)
    grid[1, 1, 1] = 1          # sits on the floor voxel
    grid[0, 0, 3] = 1          # floating, disconnected
    filled = flood_fill_3d(grid, seed_z=0, fill_value=2)
    assert filled[1, 1, 0] == 2 and filled[1, 1, 1] == 2, "floor column not filled"
    assert filled[0, 0, 3] == 1, "floating voxel should remain unfilled"
    print("ok: flood_fill marks the floor-connected component")


def test_decay_texture_reproducible():
    def run(seed):
        g = _solid_grid(6, 6, 6)
        g.decay_texture(2, np.random.default_rng(seed), lambda x, y: 0.0,
                        noise_influence=2.0)
        return g.all_occupied_positions

    assert run(123) == run(123), "decay_texture not reproducible for a fixed seed"
    print("ok: decay_texture reproducible under a seeded Generator")


def test_neighbor_kernel_matches_reference():
    """The convolution neighbour count must equal the old per-voxel reference."""
    occ = np.random.default_rng(0).random((6, 6, 6)) < 0.5
    g = PositionGrid(6, 6, 6)
    g.all_occupied_positions = {(int(x), int(y), int(z))
                                for x, y, z in np.argwhere(occ)}
    occf = occ.astype(float)
    total = (ndimage.correlate(occf, _NEIGHBOR_KERNEL, mode="constant", cval=0.0)
             + 6.0 * (ndimage.correlate(occf, _BELOW_KERNEL, mode="constant", cval=0.0) > 8.5))
    for (x, y, z) in g.all_occupied_positions:
        n, b = g._count_neighbors((x, y, z))
        ref = n + (6 if b == 9 else 0)
        assert abs(total[x, y, z] - ref) < 1e-9, ((x, y, z), total[x, y, z], ref)
    print("ok: convolution neighbour count matches _count_neighbors")


def test_drop_rests_on_floor():
    """A floating voxel in an empty column lands exactly on the floor, no gap."""
    floor_z = 3
    grid = np.zeros((3, 3, 12))
    # Wall off the centre column so the voxel can't tumble: it falls straight.
    for x in range(3):
        for y in range(3):
            if (x, y) != (1, 1):
                grid[x, y, :] = 1
    grid[1, 1, 9] = 1
    drop(1, 1, 9, grid, floor_z, rng=lambda: 0.0)
    assert grid[1, 1, 9] == 0, "voxel not removed from its old position"
    assert grid[1, 1, floor_z] == 3, "voxel did not rest on the floor"
    assert not any(grid[1, 1, z] == 3 for z in range(floor_z)), "voxel fell below floor"
    print("ok: dropped voxel rests directly on the floor")


def test_drop_rests_on_solid():
    """A floating voxel stacks directly on top of solid below it."""
    floor_z = 1
    grid = np.zeros((3, 3, 10))
    for x in range(3):
        for y in range(3):
            if (x, y) != (1, 1):
                grid[x, y, :] = 1
    grid[1, 1, 0] = 1       # solid support at z=0
    grid[1, 1, 7] = 1       # floating voxel above it
    drop(1, 1, 7, grid, floor_z, rng=lambda: 0.0)
    assert grid[1, 1, 1] == 3, "voxel did not stack on the solid cell below"
    print("ok: dropped voxel stacks on solid")


def test_decay_keeps_floor():
    g = _solid_grid(6, 6, 8, floor_thickness=2)
    before = len(g.all_occupied_positions)
    floor = {p for p in g.all_occupied_positions if p[2] <= g.stable_z}
    # Sketch-like regime: the floor's +30 stability bonus dominates, so the floor
    # survives while exposed surface voxels erode.
    g.decay_texture(3, np.random.default_rng(1), lambda x, y: 0.0,
                    noise_influence=3.5, noise_offset=-0.8, neighbor_baseline=-9)
    assert floor <= g.all_occupied_positions, "floor voxels were eroded away"
    assert len(g.all_occupied_positions) < before, "nothing eroded"
    print("ok: decay_texture preserves the floor while eroding the surface")


if __name__ == "__main__":
    test_from_maze_nonempty()
    test_flood_fill_connectivity()
    test_decay_texture_reproducible()
    test_neighbor_kernel_matches_reference()
    test_drop_rests_on_floor()
    test_drop_rests_on_solid()
    test_decay_keeps_floor()
    print("\nall voxel tests passed")
