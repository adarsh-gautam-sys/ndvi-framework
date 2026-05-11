# IITB NDVI Framework

Automated NDVI mapping framework for India using Google Earth Engine (Sentinel-2, 10m). This repository provides the project scaffold, configuration, and Earth Engine authentication entrypoint.

## Setup

1. Create a Google Cloud project and enable the Earth Engine API.
2. Ensure your Earth Engine account has access to the project.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Authentication

Run the entrypoint once to authenticate and verify access. It will open a browser for OAuth if required.

```bash
python main.py
```

## Configuration

Key parameters live in `config.py`, including date range, India bounding box, tile size, export scale, and Sentinel-2 collection.

## Outputs

Exports and derived outputs should be placed under `outputs/`.
