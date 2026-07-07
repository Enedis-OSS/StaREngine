"""Utilitaires GeoJSON — delegue vers le module commun utils_geojson_commun."""

import os as _os
import sys as _sys

_controle_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _controle_dir not in _sys.path:
    _sys.path.insert(0, _controle_dir)

from utils_geojson_commun import (  # noqa: E402, F401
    EXTENSION_GEOJSON,
    PREFIXE_ECARTS,
    ecrire_geojson,
    lire_geojson,
    lister_fichiers_geojson,
    obtenir_id_feature,
)
