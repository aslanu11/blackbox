"""D3 acceptance — a synthetic test with a known H recovers points to under
2% error (of the floor edge), per calibrate.py's own "Done when".
"""

from __future__ import annotations

import numpy as np
import pytest

from blackbox import schemas as S
from blackbox.pipeline import calibrate as C


def _synthetic_camera_homography() -> np.ndarray:
    """floor -> image homography for a plausible tilted overhead camera."""
    # Simple projective camera: scale floor metres to a 1000x1000 image, then
    # apply mild keyphysical perspective skew so the fit isn't just an affine.
    scale = 1000.0 / S.FLOOR_M
    A = np.array(
        [
            [scale, 0.03 * scale, 40.0],
            [0.02 * scale, scale, 30.0],
            [0.00012, 0.00009, 1.0],
        ]
    )
    return A


def test_known_homography_recovers_points_under_two_percent():
    floor_to_image = _synthetic_camera_homography()
    image_to_floor_true = np.linalg.inv(floor_to_image)

    floor_pts = [pt for _, pt in C.CALIBRATION_POINTS]
    # A couple of extra interior points sharpen the fit, same as a human
    # clicking screw hazards in addition to the 4 corners.
    floor_pts = floor_pts + [(S.FLOOR_M / 2, S.FLOOR_M / 2), (S.FLOOR_M / 3, 2 * S.FLOOR_M / 3)]

    image_pts = C.apply_homography(floor_to_image, floor_pts)
    rng = np.random.default_rng(0)
    image_pts = image_pts + rng.normal(0.0, 0.5, image_pts.shape)  # ~0.5 px click jitter

    H, err_m = C.compute_homography(image_pts, floor_pts)

    assert err_m < 0.02 * S.FLOOR_M

    # And the fitted H should agree with the true image->floor map on a fresh
    # point that wasn't part of the fit.
    probe_floor = np.array([[5.0, 9.0]])
    probe_image = C.apply_homography(floor_to_image, probe_floor)
    recovered = C.apply_homography(H, probe_image)
    assert np.linalg.norm(recovered - probe_floor) < 0.02 * S.FLOOR_M

    true_recovered = C.apply_homography(image_to_floor_true, probe_image)
    assert np.linalg.norm(recovered - true_recovered) < 0.02 * S.FLOOR_M


def test_too_few_points_raises():
    with pytest.raises(ValueError):
        C.compute_homography([(0, 0), (1, 0), (1, 1)], [(0, 0), (1, 0), (1, 1)])


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        C.compute_homography([(0, 0), (1, 0), (1, 1), (0, 1)], [(0, 0), (1, 0), (1, 1)])
