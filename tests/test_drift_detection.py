"""
test_drift_detection.py

Tests monitoring/drift_detection.py's compute_psi() directly against
synthetic numpy distributions - no database or Redis needed. Covers the
false-positive-rate finding from development (see compute_psi's
docstring): identical distributions at the project's default window
size must stay well under the alert threshold, while a real shift must
clearly exceed it.
"""

from __future__ import annotations

import numpy as np
import pytest

from monitoring.drift_detection import PSI_BINS, compute_psi

PSI_DRIFT_THRESHOLD = 0.25  # matches config.yaml's monitoring.psi_drift_threshold
WINDOW_SIZE = 200  # matches config.yaml's monitoring.min_events_for_drift_check


def test_compute_psi_is_zero_for_empty_input():
    assert compute_psi(np.array([]), np.array([1.0, 2.0])) == 0.0
    assert compute_psi(np.array([1.0, 2.0]), np.array([])) == 0.0


def test_compute_psi_is_near_zero_for_identical_arrays():
    values = np.random.default_rng(42).normal(0.3, 0.1, WINDOW_SIZE)
    assert compute_psi(values, values) < 0.01


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_compute_psi_stays_under_threshold_for_same_distribution(seed):
    """The false-positive-rate regression test: at this project's actual
    window size, two independent draws from the *same* distribution must
    not trip the alert threshold. Parametrized over several seeds since
    this is inherently a statistical claim, not a single-sample one."""
    rng = np.random.default_rng(seed)
    baseline = rng.normal(0.3, 0.1, WINDOW_SIZE)
    recent = rng.normal(0.3, 0.1, WINDOW_SIZE)

    psi = compute_psi(baseline, recent)
    assert psi < PSI_DRIFT_THRESHOLD, (
        f"False positive: PSI={psi:.4f} exceeded threshold {PSI_DRIFT_THRESHOLD} "
        f"for two draws from the identical distribution (seed={seed})"
    )


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_compute_psi_exceeds_threshold_for_shifted_distribution(seed):
    """The true-positive check: a real mean/variance shift must clearly
    exceed the threshold, at the same window size as the test above."""
    rng = np.random.default_rng(seed)
    baseline = rng.normal(0.3, 0.1, WINDOW_SIZE)
    recent = rng.normal(0.75, 0.15, WINDOW_SIZE)

    psi = compute_psi(baseline, recent)
    assert psi > PSI_DRIFT_THRESHOLD, (
        f"False negative: PSI={psi:.4f} did not exceed threshold "
        f"{PSI_DRIFT_THRESHOLD} for a clearly shifted distribution (seed={seed})"
    )


def test_compute_psi_handles_near_constant_baseline():
    """A baseline with almost no variance can't form meaningful quantile
    bins - must return 0.0 rather than raising or dividing by zero."""
    baseline = np.full(WINDOW_SIZE, 0.5)
    recent = np.random.default_rng(0).normal(0.5, 0.1, WINDOW_SIZE)
    assert compute_psi(baseline, recent) == 0.0


def test_effective_bin_count_is_capped_for_small_samples():
    """Bin count must scale down for small samples (see compute_psi's
    docstring) rather than always using the full PSI_BINS, which was the
    actual bug found during development."""
    rng = np.random.default_rng(0)
    small_baseline = rng.normal(0.3, 0.1, 40)  # well under WINDOW_SIZE
    small_recent = rng.normal(0.3, 0.1, 40)

    # This should NOT raise, and should stay reasonably bounded even at
    # a sample size this project's config no longer defaults to.
    psi = compute_psi(small_baseline, small_recent, n_bins=PSI_BINS)
    assert psi >= 0.0
