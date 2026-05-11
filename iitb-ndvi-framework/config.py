"""Configuration constants for the NDVI mapping framework."""

DATE_START = "2024-01-01"
DATE_END = "2024-03-31"

# [lon_min, lat_min, lon_max, lat_max]
INDIA_BBOX = [68.0, 8.0, 97.5, 37.5]

# Each tile is a 2 deg x 2 deg grid cell.
TILE_DEGREE_SIZE = 2.0

# Sentinel-2 resolution in meters.
EXPORT_SCALE = 10

# Earth Engine export folder.
EXPORT_FOLDER = "IITB_NDVI_India"

SENTINEL2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
INDIA_BOUNDARY_ASSET = "USDOS/LSIB_SIMPLE/2017"

# Max cloud probability percentage for filtering.
MAX_CLOUD_PROBABILITY = 20
