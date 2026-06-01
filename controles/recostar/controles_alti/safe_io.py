"""Chargement securise de fichiers JSON/GeoJSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def safe_load_json(base_dir: str | Path, file_path: str | Path) -> dict[str, Any]:
    """Charge un fichier JSON ou GeoJSON de manière sécurisée.

    Args:
        base_dir: Repertoire de reference autorise.
        file_path: Chemin du fichier a charger.

    Raises:
        ValueError: Chemin hors du repertoire autorise ou extension invalide.
    """
    root = Path(base_dir).resolve()
    target = Path(file_path).resolve()

    if root not in target.parents:
        raise ValueError(f"Chemin non autorise : {file_path}")

    if target.suffix.lower() not in (".json", ".geojson"):
        raise ValueError(f"Extension non autorisee : {target.suffix}")

    with target.open(encoding="utf-8") as fichier:
        return json.load(fichier)
