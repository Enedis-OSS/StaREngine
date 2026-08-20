"""Utilitaires geometriques — delegue vers le module commun utils_geometrie_commun.

Meme patron de delegation que les shims des domaines de controle, a ceci pres que
le module commun reside dans recostar/controle/ : le chemin remonte donc de deux
niveaux (calcul_longueurs/ -> traitement/ -> recostar/) avant de descendre dans
controle/.

La correction des altitudes nulles est partagee avec les controles E504 et E505 :
la definition de la longueur d'un cable doit etre unique entre le livrable des
longueurs et les controles qui la verifient.
"""

import os as _os
import sys as _sys

_recostar_dir = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_controle_dir = _os.path.join(_recostar_dir, "controle")
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
