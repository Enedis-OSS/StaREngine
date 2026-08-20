"""Utilitaires geometriques — delegue vers le module commun utils_geometrie_commun.

Tous les shims utils_geometrie.py des domaines portent le meme nom de module :
dans un processus unique (pipeline_globale charge les cinq familles), le premier
charge occupe sys.modules et sert les autres. Ces shims doivent donc reexporter
le meme jeu de noms, faute de quoi un domaine perdrait silencieusement un symbole
que son voisin expose.
"""

import os as _os
import sys as _sys

_controle_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _controle_dir not in _sys.path:
    _sys.path.insert(0, _controle_dir)

from utils_geometrie_commun import (  # noqa: E402, F401
    TOLERANCE_SUPERPOSITION,
    corriger_z_nuls,
    est_z_nul,
    extraire_extremites,
    extraire_parties_lineaires,
    recoller_parties_lineaires,
)
