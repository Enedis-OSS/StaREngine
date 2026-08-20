"""Utilitaires d'emprise DR — delegue vers le module commun utils_emprise_dr_commun."""

import os as _os
import sys as _sys

_controle_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _controle_dir not in _sys.path:
    _sys.path.insert(0, _controle_dir)

from utils_emprise_dr_commun import (  # noqa: E402, F401
    CHEMIN_EMPRISE_DR,
    CHEMIN_REFERENCE_DR,
    CRS_EMPRISE,
    EXTRACTEURS_XY,
    NUMERO_AFFAIRE_EXCLU,
    PREFIXES_AFFAIRE_EXCLUS,
    affaire_exclue_du_controle,
    appliquer_transformation,
    calculer_bbox,
    charger_emprises_dr,
    charger_references,
    construire_index,
    creer_transformateur,
    extraire_nom_crs,
    extraire_point_representatif,
    extraire_prefixe,
    point_dans_anneau,
    point_dans_emprise,
    point_dans_emprises,
    point_dans_polygon,
    resoudre_emprises_affaire,
    resoudre_repertoires,
)
