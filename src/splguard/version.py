from __future__ import annotations

from importlib import metadata


def get_version() -> str:
    try:
        return metadata.version("splguard")
    except metadata.PackageNotFoundError:
        return "0.1.0-dev"
