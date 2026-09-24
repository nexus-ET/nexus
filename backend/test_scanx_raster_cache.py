"""Locked raster scale and versioned extract replay rules."""

from app.constants.scanx import (
    SCANX_EXTRACTOR_VERSION,
    SCANX_RASTER_SCALE,
    SCANX_REPLAY_EXTRACT_CACHE,
)
from app.services.scanx_image_enhance import _compute_upscale


def test_raster_scale_is_single_value():
    assert SCANX_RASTER_SCALE == 2.0
    assert SCANX_EXTRACTOR_VERSION == "scanx-extract-2"
    assert SCANX_REPLAY_EXTRACT_CACHE is False


def test_upscale_ignores_dpi_metadata():
    low = _compute_upscale(800, 600, dpi_before=72)
    claimed_high = _compute_upscale(800, 600, dpi_before=600)
    assert low == claimed_high
    assert _compute_upscale(2000, 1600) == 1.0
