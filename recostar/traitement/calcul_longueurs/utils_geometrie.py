"""Utilitaires geometriques — delegue vers recostar.controle.fonctions_communes.geometrie.

Le module commun appartient au paquet `recostar.controle.fonctions_communes`.
Ce domaine conservant des imports a plat, la racine du depot est ajoutee a
sys.path (calcul_longueurs/ -> traitement/ -> recostar/ -> racine) avant
l'import absolu du paquet.

La correction des altitudes nulles est partagee avec les controles E-5100, E-4200
et E-4201 :
la definition de la longueur d'un cable doit etre unique entre le livrable des
longueurs et les controles qui la verifient.
"""

import os as _os
import sys as _sys

_racine_depot = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
if _racine_depot not in _sys.path:
    _sys.path.insert(0, _racine_depot)

from recostar.controle.fonctions_communes.geometrie import (  # noqa: E402, F401
    TOLERANCE_SUPERPOSITION,
    corriger_z_nuls,
    est_z_nul,
    extraire_extremites,
    extraire_parties_lineaires,
    recoller_parties_lineaires,
)
