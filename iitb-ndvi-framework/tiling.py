"""Tiling helpers for India grid generation."""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

import ee
import geopandas as gpd
import requests
import matplotlib.pyplot as plt
from matplotlib import patches

import config
from gee_auth import authenticate_gee

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(name)s - %(message)s",
	)


def generate_india_grid(tile_size_deg: float = 2.0) -> list[dict[str, Any]]:
	"""Generate a regular grid of tiles covering the India bounding box."""
	lon_min, lat_min, lon_max, lat_max = config.INDIA_BBOX

	lon_steps = int(math.ceil((lon_max - lon_min) / tile_size_deg))
	lat_steps = int(math.ceil((lat_max - lat_min) / tile_size_deg))

	tiles: list[dict[str, Any]] = []
	for lon_idx in range(lon_steps):
		for lat_idx in range(lat_steps):
			tile_lon_min = lon_min + (lon_idx * tile_size_deg)
			tile_lat_min = lat_min + (lat_idx * tile_size_deg)
			tile_lon_max = min(tile_lon_min + tile_size_deg, lon_max)
			tile_lat_max = min(tile_lat_min + tile_size_deg, lat_max)

			tile_id = f"tile_{lon_idx:02d}_{lat_idx:02d}"
			geometry = ee.Geometry.Rectangle(
				[tile_lon_min, tile_lat_min, tile_lon_max, tile_lat_max]
			)
			tiles.append(
				{
					"tile_id": tile_id,
					"lon_min": tile_lon_min,
					"lat_min": tile_lat_min,
					"lon_max": tile_lon_max,
					"lat_max": tile_lat_max,
					"geometry": geometry,
				}
			)

	print(f"Generated {len(tiles)} tiles covering INDIA_BBOX.")
	return tiles


def filter_tiles_over_india(tiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Filter tiles to those intersecting the India boundary."""
	try:
		india_fc = ee.FeatureCollection(config.INDIA_BOUNDARY_ASSET).filter(
			ee.Filter.eq("country_na", "India")
		)
		india_geom = india_fc.geometry()
	except ee.EEException as exc:
		logger.exception("Failed to load India boundary: %s", exc)
		raise

	filtered_tiles: list[dict[str, Any]] = []
	for tile in tiles:
		tile_geom = tile["geometry"]
		try:
			intersects = (
				tile_geom.intersects(india_geom, ee.ErrorMargin(1)).getInfo()
			)
		except ee.EEException as exc:
			logger.exception("Tile intersection failed for %s: %s", tile["tile_id"], exc)
			raise

		if bool(intersects):
			filtered_tiles.append(tile)

	print(
		f"Tiles generated: {len(tiles)} | Tiles over India: {len(filtered_tiles)}"
	)
	return filtered_tiles


def save_tile_manifest(
	tiles: list[dict[str, Any]],
	output_path: str = "outputs/tile_manifest.json",
) -> None:
	"""Save tile metadata to a JSON manifest."""
	if tiles:
		tile_size_deg = round(tiles[0]["lon_max"] - tiles[0]["lon_min"], 6)
	else:
		tile_size_deg = config.TILE_DEGREE_SIZE

	manifest = {
		"timestamp": datetime.now(timezone.utc).isoformat(),
		"total_count": len(tiles),
		"tile_size_deg": tile_size_deg,
		"date_range": {"start": config.DATE_START, "end": config.DATE_END},
		"tiles": [
			{
				"tile_id": tile["tile_id"],
				"lon_min": tile["lon_min"],
				"lat_min": tile["lat_min"],
				"lon_max": tile["lon_max"],
				"lat_max": tile["lat_max"],
			}
			for tile in tiles
		],
	}

	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	with open(output_path, "w", encoding="utf-8") as file_handle:
		json.dump(manifest, file_handle, indent=2)

	print(f"Saved tile manifest to {output_path}.")


def load_tile_manifest(path: str) -> list[dict[str, Any]]:
	"""Load a tile manifest and reconstruct tile geometries."""
	with open(path, "r", encoding="utf-8") as file_handle:
		manifest = json.load(file_handle)

	tiles: list[dict[str, Any]] = []
	for tile in manifest.get("tiles", []):
		geometry = ee.Geometry.Rectangle(
			[tile["lon_min"], tile["lat_min"], tile["lon_max"], tile["lat_max"]]
		)
		tiles.append({**tile, "geometry": geometry})

	return tiles


def _load_india_outline() -> gpd.GeoDataFrame:
	"""Load the India outline from Natural Earth data."""
	cache_dir = os.path.join("outputs", "natural_earth")
	os.makedirs(cache_dir, exist_ok=True)
	zip_path = os.path.join(cache_dir, "ne_110m_admin_0_countries.zip")

	if not os.path.exists(zip_path):
		url = "https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip"
		response = requests.get(url, timeout=60)
		response.raise_for_status()
		with open(zip_path, "wb") as file_handle:
			file_handle.write(response.content)

	world = gpd.read_file(f"zip://{zip_path}")
	return world[world["ADMIN"] == "India"]


def visualize_tile_grid(
	tiles: list[dict[str, Any]],
	output_path: str = "outputs/tile_grid.png",
) -> None:
	"""Visualize the tile grid over India and save to PNG."""
	if not tiles:
		raise ValueError("No tiles provided for visualization.")

	india = _load_india_outline()

	fig, ax = plt.subplots(figsize=(10, 10))
	india.plot(ax=ax, color="#E8E8E8", edgecolor="#333333")

	cmap = plt.get_cmap("Greens")
	total_tiles = len(tiles)
	for idx, tile in enumerate(tiles):
		lon_min = tile["lon_min"]
		lat_min = tile["lat_min"]
		lon_max = tile["lon_max"]
		lat_max = tile["lat_max"]
		width = lon_max - lon_min
		height = lat_max - lat_min

		color = cmap(idx / max(1, total_tiles - 1))
		rect = patches.Rectangle(
			(lon_min, lat_min),
			width,
			height,
			linewidth=0.8,
			edgecolor=color,
			facecolor="none",
		)
		ax.add_patch(rect)

	ax.set_title("India NDVI Tile Grid")
	ax.set_xlabel("Longitude")
	ax.set_ylabel("Latitude")

	legend_patch = patches.Patch(color=cmap(0.7), label="Tiles over India")
	ax.legend(handles=[legend_patch], loc="lower left")
	ax.text(
		0.02,
		0.98,
		f"Tile count: {total_tiles}",
		transform=ax.transAxes,
		ha="left",
		va="top",
		fontsize=10,
		bbox={"facecolor": "white", "alpha": 0.6, "edgecolor": "none"},
	)

	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	plt.tight_layout()
	plt.savefig(output_path, dpi=300)
	plt.close(fig)

	print(f"Saved tile grid visualization to {output_path}.")


if __name__ == "__main__":
	authenticate_gee()
	grid_tiles = generate_india_grid(config.TILE_DEGREE_SIZE)
	india_tiles = filter_tiles_over_india(grid_tiles)
	save_tile_manifest(india_tiles)
	visualize_tile_grid(india_tiles)
