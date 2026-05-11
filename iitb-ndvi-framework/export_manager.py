"""Export orchestration utilities for Earth Engine tasks."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import ee
from tqdm import tqdm

import config
from gee_auth import authenticate_gee
from sentinel2_processing import create_ndvi_composite
from tiling import load_tile_manifest

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(name)s - %(message)s",
	)

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
RETRY_SUMMARY: Optional[dict[str, list[str]]] = None


def submit_export_task(
	tile: dict[str, Any],
	ndvi_image: ee.Image,
	scale: int = config.EXPORT_SCALE,
) -> ee.batch.Task:
	"""Submit a single NDVI export task for a tile and start it."""
	try:
		task = ee.batch.Export.image.toDrive(
			image=ndvi_image,
			description=tile["tile_id"],
			folder=config.EXPORT_FOLDER,
			scale=scale,
			region=tile["geometry"],
			maxPixels=1e13,
			fileFormat="GeoTIFF",
			crs="EPSG:4326",
		)
		task.start()
		logger.info("Submitted export task %s (id=%s).", tile["tile_id"], task.id)
		return task
	except ee.EEException as exc:
		logger.exception("Failed to submit export for %s: %s", tile.get("tile_id"), exc)
		raise


def submit_all_tiles(tiles: list[dict[str, Any]]) -> dict[str, ee.batch.Task]:
	"""Submit NDVI export tasks for all tiles and persist task ids."""
	tasks: dict[str, ee.batch.Task] = {}
	if not tiles:
		logger.warning("No tiles provided for export submission.")
		return tasks

	output_path = "outputs/task_ids.json"
	os.makedirs(os.path.dirname(output_path), exist_ok=True)

	with tqdm(total=len(tiles), desc="Submitting export tasks") as progress:
		for tile in tiles:
			tile_id = tile["tile_id"]
			try:
				ndvi_image = create_ndvi_composite(
					tile["geometry"],
					config.DATE_START,
					config.DATE_END,
				)
				tasks[tile_id] = submit_export_task(tile, ndvi_image)
			except ee.EEException as exc:
				logger.exception("Submission failed for %s: %s", tile_id, exc)
			progress.update(1)
			time.sleep(0.5)

	payload = {
		"timestamp": datetime.now(timezone.utc).isoformat(),
		"task_ids": {tile_id: task.id for tile_id, task in tasks.items()},
	}
	with open(output_path, "w", encoding="utf-8") as file_handle:
		json.dump(payload, file_handle, indent=2)
	logger.info("Saved task ids to %s.", output_path)

	return tasks


def monitor_tasks(
	tasks: dict[str, ee.batch.Task],
	poll_interval_sec: int = 30,
) -> dict[str, list[str]]:
	"""Monitor tasks until completion and return summary lists."""
	if not tasks:
		return {"completed": [], "failed": [], "cancelled": []}

	start_times = {tile_id: time.monotonic() for tile_id in tasks}
	last_states = {tile_id: None for tile_id in tasks}

	os.makedirs("outputs", exist_ok=True)
	failed_log_path = "outputs/failed_tasks.log"

	while True:
		completed: list[str] = []
		failed: list[str] = []
		cancelled: list[str] = []

		lines = ["tile_id | state | elapsed_sec"]
		for tile_id, task in tasks.items():
			status = task.status()
			state = status.get("state", "UNKNOWN")
			elapsed = time.monotonic() - start_times[tile_id]
			lines.append(f"{tile_id} | {state} | {elapsed:.0f}")

			if state == "COMPLETED":
				completed.append(tile_id)
			elif state == "FAILED":
				failed.append(tile_id)
				if last_states[tile_id] != "FAILED":
					error_message = status.get("error_message", "unknown error")
					with open(failed_log_path, "a", encoding="utf-8") as file_handle:
						file_handle.write(f"{tile_id}: {error_message}\n")
			elif state == "CANCELLED":
				cancelled.append(tile_id)

			last_states[tile_id] = state

		logger.info("Task status:\n%s", "\n".join(lines))

		if len(completed) + len(failed) + len(cancelled) == len(tasks):
			return {"completed": completed, "failed": failed, "cancelled": cancelled}

		time.sleep(poll_interval_sec)


def retry_failed_tasks(failed_tile_ids: list[str], tiles: list[dict[str, Any]]) -> None:
	"""Retry failed tiles up to two times and log retry attempts."""
	global RETRY_SUMMARY

	if not failed_tile_ids:
		logger.info("No failed tiles to retry.")
		RETRY_SUMMARY = {"completed": [], "failed": [], "cancelled": []}
		return

	tile_lookup = {tile["tile_id"]: tile for tile in tiles}
	remaining = list(dict.fromkeys(failed_tile_ids))
	final_summary = {"completed": [], "failed": remaining, "cancelled": []}

	for attempt in range(1, 3):
		if not remaining:
			break

		logger.info("Retry attempt %d for %d tiles.", attempt, len(remaining))
		tasks: dict[str, ee.batch.Task] = {}
		for tile_id in remaining:
			tile = tile_lookup.get(tile_id)
			if not tile:
				logger.warning("Tile %s not found in manifest. Skipping.", tile_id)
				continue
			try:
				ndvi_image = create_ndvi_composite(
					tile["geometry"],
					config.DATE_START,
					config.DATE_END,
				)
				tasks[tile_id] = submit_export_task(tile, ndvi_image)
			except ee.EEException as exc:
				logger.exception("Retry submission failed for %s: %s", tile_id, exc)
			time.sleep(0.5)

		if not tasks:
			break

		summary = monitor_tasks(tasks)
		remaining = summary["failed"] + summary["cancelled"]
		final_summary = summary

	if remaining:
		logger.error("Retries exhausted for tiles: %s", ", ".join(remaining))

	RETRY_SUMMARY = final_summary
	logger.info("Retry summary: %s", final_summary)


def load_and_resume(task_ids_path: str = "outputs/task_ids.json") -> None:
	"""Load saved task ids and resume monitoring existing tasks."""
	authenticate_gee()
	with open(task_ids_path, "r", encoding="utf-8") as file_handle:
		payload = json.load(file_handle)

	task_ids: dict[str, str] = payload.get("task_ids", {})
	if not task_ids:
		logger.warning("No task ids found in %s.", task_ids_path)
		return

	tasks_by_id = {task.id: task for task in ee.batch.Task.list()}
	tasks: dict[str, ee.batch.Task] = {}

	for tile_id, task_id in task_ids.items():
		task = tasks_by_id.get(task_id)
		if not task:
			logger.warning("Task %s for tile %s not found.", task_id, tile_id)
			continue
		tasks[tile_id] = task

	logger.info("Resuming monitoring for %d tasks.", len(tasks))
	monitor_tasks(tasks)


if __name__ == "__main__":
	authenticate_gee()
	tiles = load_tile_manifest("outputs/tile_manifest.json")
	if not tiles:
		raise SystemExit("No tiles found. Run tiling.py to generate a manifest.")

	submitted_tasks = submit_all_tiles(tiles)
	summary = monitor_tasks(submitted_tasks)

	if summary["failed"]:
		retry_failed_tasks(summary["failed"], tiles)
		retry_summary = RETRY_SUMMARY or {"completed": [], "failed": [], "cancelled": []}
		final_summary = {
			"completed": summary["completed"] + retry_summary.get("completed", []),
			"failed": retry_summary.get("failed", []),
			"cancelled": retry_summary.get("cancelled", []),
		}
	else:
		final_summary = summary

	logger.info("Final summary: %s", final_summary)
