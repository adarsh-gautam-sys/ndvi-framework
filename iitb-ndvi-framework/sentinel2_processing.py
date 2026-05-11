"""Sentinel-2 preprocessing utilities for NDVI workflows."""

from __future__ import annotations

import logging

import ee

import config
from gee_auth import authenticate_gee

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(name)s - %(message)s",
	)


def mask_s2_clouds(image: ee.Image) -> ee.Image:
	"""Mask Sentinel-2 SR clouds, shadows, cirrus, and snow using SCL."""
	try:
		scl = image.select("SCL")
		# SCL provides scene classes beyond QA60 bit flags, improving mask fidelity.
		mask = (
			scl.neq(3)
			.And(scl.neq(7))
			.And(scl.neq(8))
			.And(scl.neq(9))
			.And(scl.neq(10))
			.And(scl.neq(11))
		)
		return image.updateMask(mask)
	except ee.EEException as exc:
		logger.exception("Failed to mask clouds using SCL band: %s", exc)
		raise


def get_sentinel2_collection(
	geometry: ee.Geometry,
	date_start: str,
	date_end: str,
) -> ee.ImageCollection:
	"""Build a filtered, cloud-masked Sentinel-2 SR collection."""
	try:
		collection = (
			ee.ImageCollection(config.SENTINEL2_COLLECTION)
			.filterDate(date_start, date_end)
			.filterBounds(geometry)
			.filter(
				ee.Filter.lt(
					"CLOUDY_PIXEL_PERCENTAGE",
					config.MAX_CLOUD_PROBABILITY,
				)
			)
			.map(mask_s2_clouds)
		)
		return collection
	except ee.EEException as exc:
		logger.exception(
			"Failed to build Sentinel-2 collection for %s to %s: %s",
			date_start,
			date_end,
			exc,
		)
		raise


def compute_ndvi(image: ee.Image) -> ee.Image:
	"""Compute NDVI from B8 (NIR) and B4 (red) for one image."""
	try:
		ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI").clamp(-1, 1)
		return ndvi.copyProperties(image, ["system:time_start"])
	except ee.EEException as exc:
		logger.exception("Failed to compute NDVI: %s", exc)
		raise


def create_ndvi_composite(
	geometry: ee.Geometry,
	date_start: str,
	date_end: str,
) -> ee.Image:
	"""Create a median NDVI composite clipped to the geometry."""
	try:
		collection = get_sentinel2_collection(geometry, date_start, date_end).map(
			compute_ndvi
		)
		composite = collection.median().select("NDVI").clip(geometry)
		return composite
	except ee.EEException as exc:
		logger.exception("Failed to create NDVI composite: %s", exc)
		raise


def test_single_tile(
	lon_min: float,
	lat_min: float,
	lon_max: float,
	lat_max: float,
) -> None:
	"""Run a smoke test NDVI composite on a small tile."""
	geometry = ee.Geometry.Rectangle([lon_min, lat_min, lon_max, lat_max])
	try:
		image = create_ndvi_composite(geometry, config.DATE_START, config.DATE_END)
		band_names = image.bandNames().getInfo()
		projection = image.projection().getInfo()
		pixel_count = (
			image.select("NDVI")
			.reduceRegion(
				reducer=ee.Reducer.count(),
				geometry=geometry,
				scale=max(config.EXPORT_SCALE, 500),
				maxPixels=1e13,
				bestEffort=True,
			)
			.get("NDVI")
			.getInfo()
		)
		logger.info("NDVI composite band names: %s", band_names)
		logger.info("NDVI composite projection: %s", projection)
		logger.info("NDVI composite pixel count estimate: %s", pixel_count)
	except ee.EEException as exc:
		logger.exception("NDVI tile test failed: %s", exc)
		raise


if __name__ == "__main__":
	authenticate_gee()
	# Delhi region smoke test
	test_single_tile(77.0, 28.0, 77.2, 28.2)
