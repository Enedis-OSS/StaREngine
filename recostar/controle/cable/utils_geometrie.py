"""Utilitaires geometriques — delegue vers le module commun utils_geometrie_commun."""

import os as _os
import sys as _sys

_controle_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _controle_dir not in _sys.path:
    _sys.path.insert(0, _controle_dir)

from utils_geometrie_commun import (  # noqa: E402, F401
    extraire_extremites,
    extraire_parties_lineaires,
)
