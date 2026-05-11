"""Entry point for the IITB NDVI mapping framework."""

from __future__ import annotations

from gee_auth import authenticate_gee, verify_gee_connection


def main() -> None:
    """Initialize Earth Engine and verify connectivity."""
    authenticate_gee()
    verify_gee_connection()


if __name__ == "__main__":
    main()
