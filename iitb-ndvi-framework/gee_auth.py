"""Authentication helpers for Google Earth Engine (GEE)."""

from __future__ import annotations

from typing import Optional

import ee


DEFAULT_GEE_PROJECT = "electionguide-ai-494621"


def _extract_project_name(root_id: str) -> str:
    """Extract the GEE project name from an asset root id string."""
    parts = root_id.split("/")
    if len(parts) >= 2 and parts[0] == "projects":
        return parts[1]
    return "unknown"


def authenticate_gee(project: Optional[str] = None) -> None:
    """Authenticate and initialize the Earth Engine API."""
    if not project:
        project = DEFAULT_GEE_PROJECT
    try:
        if project:
            ee.Initialize(project=project)
        else:
            ee.Initialize()
    except ee.EEException:
        ee.Authenticate()
        if project:
            ee.Initialize(project=project)
        else:
            ee.Initialize()

    project_name = "IITB NVDI Framework"
    try:
        roots = ee.data.getAssetRoots()
        if roots:
            project_name = _extract_project_name(roots[0].get("id", ""))
    except Exception:
        project_name = "unknown"

    print(f"GEE initialized successfully (project: {project_name}).")


def verify_gee_connection() -> None:
    """Verify GEE access by printing the first Sentinel-2 image id."""
    collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    first_image = collection.first()
    image_id = first_image.id().getInfo()
    print(f"GEE access verified. First image ID: {image_id}")


if __name__ == "__main__":
    authenticate_gee()
    verify_gee_connection()
