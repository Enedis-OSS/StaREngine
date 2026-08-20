"""Chargement securise et validation des resultats de longueurs au format JSON."""

import json
from pathlib import Path
from typing import Any


def charger_json_confine(repertoire_autorise: Path, chemin_fichier: Path) -> dict[str, Any]:
    """Charge un JSON en le confinant au repertoire autorise (anti-traversal)."""
    racine = Path(repertoire_autorise).resolve()
    cible = Path(chemin_fichier).resolve()

    if not cible.is_relative_to(racine):
        raise ValueError("Chemin de fichier hors du repertoire autorise")
    if cible.suffix.lower() != ".json":
        raise ValueError("Extension .json attendue")

    with cible.open(encoding="utf-8") as fichier:
        return json.load(fichier)


def valider_resultats_longueurs(donnees: dict[str, Any], max_elements: int = 5000) -> list[dict[str, Any]]:
    """Valide la cle 'resultats' (liste bornee) et la retourne."""
    resultats = donnees.get("resultats", [])
    if not isinstance(resultats, list):
        raise ValueError("'resultats' doit etre une liste")
    if len(resultats) > max_elements:
        raise ValueError("Trop d'elements dans 'resultats'")
    return resultats
