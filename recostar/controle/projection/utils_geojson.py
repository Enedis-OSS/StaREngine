"""
Utilitaires communs pour la manipulation de fichiers GeoJSON.

Centralise les fonctions de lecture, ecriture, listage et extraction
d'identifiant partagees par les differents controles de projection.
"""

import json
import os
from pathlib import Path
from typing import Any

# Extension des fichiers traites
EXTENSION_GEOJSON: str = ".geojson"

# Prefixe des fichiers d'ecarts (exclus de l'analyse)
PREFIXE_ECARTS: str = "ecarts_"


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Charge un fichier GeoJSON et retourne son contenu, ou None si absent."""
    chemin = str(Path(chemin).resolve())
    if not os.path.isfile(chemin):
        return None
    with open(chemin, encoding="utf-8") as fichier:
        return json.load(fichier)


def ecrire_geojson(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un FeatureCollection GeoJSON sur disque."""
    chemin = str(Path(chemin).resolve())
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


def lister_fichiers_geojson(repertoire: str) -> list[str]:
    """Liste les fichiers GeoJSON eligibles dans le repertoire.

    Exclut les fichiers d'ecarts (prefixe 'ecarts_') pour eviter
    l'analyse des sorties de controles precedents.
    """
    repertoire = str(Path(repertoire).resolve())
    fichiers: list[str] = []
    for nom in sorted(os.listdir(repertoire)):
        if not nom.lower().endswith(EXTENSION_GEOJSON):
            continue
        if nom.lower().startswith(PREFIXE_ECARTS):
            continue
        fichiers.append(nom)
    return fichiers


def obtenir_id_feature(feature: dict[str, Any]) -> str | None:
    """Retourne l'identifiant metier d'une feature GeoJSON."""
    proprietes = feature.get("properties") or {}
    valeur = proprietes.get("id")
    if isinstance(valeur, (str, int)):
        return str(valeur)
    return None
