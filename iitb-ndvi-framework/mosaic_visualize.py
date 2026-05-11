"""Mosaic and visualization helpers for NDVI outputs."""

from __future__ import annotations

import logging
import os
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors
from matplotlib import patches

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _list_tif_files(tile_dir: str) -> list[str]:
    if not os.path.isdir(tile_dir):
        return []
    return [
        os.path.join(tile_dir, name)
        for name in sorted(os.listdir(tile_dir))
        if name.lower().endswith(".tif")
    ]


def mosaic_tiles(
    tile_dir: str = "outputs/tiles/",
    output_path: str = "outputs/india_ndvi_mosaic.tif",
) -> None:
    """Merge GeoTIFF tiles into a single mosaic and save as GeoTIFF."""
    tif_files = _list_tif_files(tile_dir)
    if not tif_files:
        raise FileNotFoundError(f"No GeoTIFF tiles found in {tile_dir}.")

    try:
        import rasterio
        from rasterio.merge import merge
    except ImportError as exc:
        raise ImportError("rasterio is required for mosaicking") from exc

    datasets = [rasterio.open(path) for path in tif_files]
    try:
        crs_set = {ds.crs.to_string() for ds in datasets if ds.crs}
        if not crs_set:
            raise ValueError("Missing CRS in one or more tiles.")
        if crs_set != {"EPSG:4326"}:
            raise ValueError(f"Unexpected CRS values: {crs_set}")

        mosaic, transform = merge(datasets)
        meta = datasets[0].meta.copy()
        meta.update(
            {
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": transform,
                "compress": "LZW",
            }
        )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with rasterio.open(output_path, "w", **meta) as dest:
            dest.write(mosaic)
    finally:
        for dataset in datasets:
            dataset.close()

    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    with rasterio.open(output_path) as dataset:
        res_x, res_y = dataset.res
    print(
        f"Mosaic saved: {output_path} ({file_size_mb:.2f} MB), "
        f"resolution={res_x:.6f} x {res_y:.6f}"
    )


def visualize_ndvi_map(
    tif_path: str,
    output_png: str = "outputs/india_ndvi_map.png",
) -> None:
    """Render a national NDVI map from a GeoTIFF."""
    try:
        import rasterio
    except ImportError as exc:
        raise ImportError("rasterio is required for visualization") from exc

    with rasterio.open(tif_path) as dataset:
        ndvi = dataset.read(1).astype("float32")
        if dataset.nodata is not None:
            ndvi = np.ma.masked_equal(ndvi, dataset.nodata)
        extent = [
            dataset.bounds.left,
            dataset.bounds.right,
            dataset.bounds.bottom,
            dataset.bounds.top,
        ]

    fig, ax = plt.subplots(figsize=(10, 10))
    cmap = plt.get_cmap("RdYlGn")
    norm = colors.Normalize(vmin=-0.2, vmax=0.8)
    image = ax.imshow(
        ndvi,
        cmap=cmap,
        norm=norm,
        extent=extent,
        origin="upper",
    )
    ax.set_title("India NDVI Map (Sentinel-2, Jan-Mar 2024)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    colorbar = fig.colorbar(image, ax=ax, shrink=0.8)
    colorbar.set_label("NDVI")

    _add_north_arrow(ax)

    os.makedirs(os.path.dirname(output_png), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_png, dpi=300)
    plt.close(fig)
    logger.info("Saved NDVI map to %s", output_png)


def visualize_sample_tile(tile_tif: str, output_png: str) -> None:
    """Render a single tile NDVI image with subtitle."""
    tile_id = os.path.splitext(os.path.basename(tile_tif))[0]
    try:
        import rasterio
    except ImportError as exc:
        raise ImportError("rasterio is required for visualization") from exc

    with rasterio.open(tile_tif) as dataset:
        ndvi = dataset.read(1).astype("float32")
        if dataset.nodata is not None:
            ndvi = np.ma.masked_equal(ndvi, dataset.nodata)
        extent = [
            dataset.bounds.left,
            dataset.bounds.right,
            dataset.bounds.bottom,
            dataset.bounds.top,
        ]

    fig, ax = plt.subplots(figsize=(6, 6))
    cmap = plt.get_cmap("RdYlGn")
    norm = colors.Normalize(vmin=-0.2, vmax=0.8)
    image = ax.imshow(
        ndvi,
        cmap=cmap,
        norm=norm,
        extent=extent,
        origin="upper",
    )
    ax.set_title("Sample NDVI Tile")
    ax.text(0.5, 1.02, tile_id, transform=ax.transAxes, ha="center", va="bottom")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    colorbar = fig.colorbar(image, ax=ax, shrink=0.8)
    colorbar.set_label("NDVI")

    _add_north_arrow(ax)

    os.makedirs(os.path.dirname(output_png), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_png, dpi=300)
    plt.close(fig)
    logger.info("Saved sample tile visualization to %s", output_png)


def generate_workflow_diagram(output_path: str = "outputs/workflow_diagram.png") -> None:
    """Generate a workflow flowchart for the NDVI pipeline."""
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.axis("off")

    steps = [
        "Sentinel-2 SR Collection",
        "Cloud Masking (SCL)",
        "Median Composite",
        "NDVI Calculation",
        "India Grid Tiling",
        "Parallel GEE Export",
        "Tile Mosaicking",
        "Final NDVI Map",
    ]

    colors_map = {
        "data": "#5B8FD1",
        "processing": "#6BBE7E",
        "output": "#F2A65A",
    }
    categories = [
        "data",
        "processing",
        "processing",
        "processing",
        "processing",
        "processing",
        "output",
        "output",
    ]

    x_start = 0.02
    x_step = 0.12
    y = 0.5
    box_width = 0.11
    box_height = 0.22

    box_positions: list[tuple[float, float]] = []
    for idx, step in enumerate(steps):
        x = x_start + idx * x_step
        box_positions.append((x, y))
        box = patches.FancyBboxPatch(
            (x, y),
            box_width,
            box_height,
            boxstyle="round,pad=0.02",
            linewidth=1.2,
            edgecolor="#333333",
            facecolor=colors_map[categories[idx]],
        )
        ax.add_patch(box)
        ax.text(
            x + box_width / 2,
            y + box_height / 2,
            step,
            ha="center",
            va="center",
            fontsize=9,
        )

    for idx in range(len(box_positions) - 1):
        x, y = box_positions[idx]
        arrow = patches.FancyArrowPatch(
            (x + box_width, y + box_height / 2),
            (x + x_step, y + box_height / 2),
            arrowstyle="->",
            mutation_scale=12,
            linewidth=1.0,
            color="#333333",
        )
        ax.add_patch(arrow)

    ax.text(
        0.72,
        0.18,
        "GEE limits: ~60 tiles, 10GB export cap",
        fontsize=9,
        color="#333333",
        ha="center",
        va="center",
        bbox={"facecolor": "#FFFFFF", "edgecolor": "#AAAAAA", "boxstyle": "round"},
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info("Saved workflow diagram to %s", output_path)


def _add_north_arrow(ax: plt.Axes) -> None:
    ax.annotate(
        "N",
        xy=(0.95, 0.1),
        xytext=(0.95, 0.2),
        xycoords="axes fraction",
        textcoords="axes fraction",
        ha="center",
        va="center",
        arrowprops={"arrowstyle": "-|>", "lw": 1.5},
    )


def _print_checklist(entries: Iterable[str]) -> None:
    print("Checklist of generated files:")
    for entry in entries:
        print(f"[x] {entry}")


if __name__ == "__main__":
    outputs: list[str] = []

    generate_workflow_diagram()
    outputs.append("outputs/workflow_diagram.png")

    tile_dir = "outputs/tiles/"
    mosaic_path = "outputs/india_ndvi_mosaic.tif"
    mosaic_tiles(tile_dir=tile_dir, output_path=mosaic_path)
    outputs.append(mosaic_path)

    map_path = "outputs/india_ndvi_map.png"
    visualize_ndvi_map(mosaic_path, output_png=map_path)
    outputs.append(map_path)

    tile_files = _list_tif_files(tile_dir)
    if tile_files:
        sample_path = "outputs/sample_tile.png"
        visualize_sample_tile(tile_files[0], output_png=sample_path)
        outputs.append(sample_path)

    _print_checklist(outputs)
