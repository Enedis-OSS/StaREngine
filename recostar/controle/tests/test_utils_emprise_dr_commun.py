"""
Tests des utilitaires d'emprise DR communs (utils_emprise_dr_commun.py).

Couvre la mutualisation entre le controle E303 (entites hors emprise) et le
controle E508 (cables HTB dans l'emprise) :
  - coherence des shims utils_emprise_dr.py de chaque domaine
  - chargement des emprises Polygon et MultiPolygon
  - resolution complete d'un numero d'affaire vers ses emprises
"""

import ast
import json
from pathlib import Path
from typing import Any

from utils_emprise_dr_commun import (
    charger_emprises_dr,
    point_dans_emprises,
    resoudre_emprises_affaire,
)

# Racine du paquet de controle (repertoire parent de tests/).
_RACINE_CONTROLE = Path(__file__).resolve().parent.parent


def _noms_reexportes(chemin: Path) -> set[str]:
    """Noms importes depuis utils_emprise_dr_commun par un shim de domaine."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    noms: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom) and noeud.module == "utils_emprise_dr_commun":
            noms.update(alias.name for alias in noeud.names)
    return noms


def _anneau(xmin: float, ymin: float, xmax: float, ymax: float) -> list[list[float]]:
    """Anneau rectangulaire ferme."""
    return [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]


def _ecrire_emprises(chemin: Path, features: list[dict[str, Any]]) -> None:
    """Ecrit un fichier d'emprises DR de test."""
    collection = {"type": "FeatureCollection", "features": features}
    chemin.write_text(json.dumps(collection), encoding="utf-8")


def _feature_emprise(code: str, geometrie: dict[str, Any]) -> dict[str, Any]:
    """Feature d'emprise DR portant son code code_dr_oa."""
    return {"type": "Feature", "properties": {"code_dr_oa": code}, "geometry": geometrie}


class TestCoherenceDesShims:
    """Les shims utils_emprise_dr.py doivent reexporter le meme jeu de noms.

    Ils portent tous le meme nom de module : dans un processus unique
    (pipeline_globale charge les cinq familles), le premier charge occupe
    sys.modules et sert les autres. Un shim exposant moins que son voisin
    provoque un ImportError a distance, dans le domaine charge en second.
    """

    def test_shims_identiques(self) -> None:
        shims = sorted(_RACINE_CONTROLE.glob("*/utils_emprise_dr.py"))
        assert len(shims) >= 2, "au moins deux domaines delèguent vers le module commun"
        reference = _noms_reexportes(shims[0])
        assert reference, f"{shims[0]} ne reexporte rien"
        for shim in shims[1:]:
            assert _noms_reexportes(shim) == reference, f"{shim.parent.name} diverge de {shims[0].parent.name}"

    def test_noms_reexportes_existent_dans_le_module_commun(self) -> None:
        """Un nom reexporte mais absent du module commun casserait tous les domaines."""
        import utils_emprise_dr_commun

        for shim in _RACINE_CONTROLE.glob("*/utils_emprise_dr.py"):
            for nom in _noms_reexportes(shim):
                assert hasattr(utils_emprise_dr_commun, nom), f"{nom} absent de utils_emprise_dr_commun"


class TestChargerEmprisesDr:
    """Chargement des emprises depuis le fichier de reference."""

    def test_fichier_absent(self, tmp_path: Path) -> None:
        emprises, erreur = charger_emprises_dr(str(tmp_path / "absent.geojson"), {"8A"})
        assert emprises == []
        assert erreur is not None

    def test_polygone_charge(self, tmp_path: Path) -> None:
        chemin = tmp_path / "emprise.geojson"
        geometrie = {"type": "Polygon", "coordinates": [_anneau(0, 0, 100, 100)]}
        _ecrire_emprises(chemin, [_feature_emprise("8A", geometrie)])
        emprises, erreur = charger_emprises_dr(str(chemin), {"8A"})
        assert erreur is None
        assert len(emprises) == 1
        assert emprises[0]["bbox"] == (0, 0, 100, 100)

    def test_multipolygone_charge_partie_par_partie(self, tmp_path: Path) -> None:
        """Une DR discontinue est stockee en MultiPolygon : chaque partie compte."""
        chemin = tmp_path / "emprise.geojson"
        geometrie = {
            "type": "MultiPolygon",
            "coordinates": [[_anneau(0, 0, 100, 100)], [_anneau(500, 500, 600, 600)]],
        }
        _ecrire_emprises(chemin, [_feature_emprise("4A", geometrie)])
        emprises, erreur = charger_emprises_dr(str(chemin), {"4A"})
        assert erreur is None
        assert len(emprises) == 2
        assert point_dans_emprises(50.0, 50.0, emprises) is True
        assert point_dans_emprises(550.0, 550.0, emprises) is True
        assert point_dans_emprises(300.0, 300.0, emprises) is False

    def test_code_dr_insensible_a_la_casse(self, tmp_path: Path) -> None:
        chemin = tmp_path / "emprise.geojson"
        geometrie = {"type": "Polygon", "coordinates": [_anneau(0, 0, 100, 100)]}
        _ecrire_emprises(chemin, [_feature_emprise("8a", geometrie)])
        emprises, erreur = charger_emprises_dr(str(chemin), {"8A"})
        assert erreur is None
        assert len(emprises) == 1

    def test_geometrie_non_surfacique_ignoree(self, tmp_path: Path) -> None:
        chemin = tmp_path / "emprise.geojson"
        geometrie = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
        _ecrire_emprises(chemin, [_feature_emprise("8A", geometrie)])
        emprises, erreur = charger_emprises_dr(str(chemin), {"8A"})
        assert emprises == []
        assert erreur is not None

    def test_code_inconnu_retourne_erreur(self, tmp_path: Path) -> None:
        chemin = tmp_path / "emprise.geojson"
        geometrie = {"type": "Polygon", "coordinates": [_anneau(0, 0, 100, 100)]}
        _ecrire_emprises(chemin, [_feature_emprise("8A", geometrie)])
        emprises, erreur = charger_emprises_dr(str(chemin), {"9Z"})
        assert emprises == []
        assert erreur is not None
        assert "9Z" in erreur


class TestResoudreEmprisesAffaire:
    """Resolution complete numero d'affaire -> emprises, sur le referentiel reel."""

    def test_format_invalide_retourne_erreur(self) -> None:
        emprises, codes, erreur = resoudre_emprises_affaire("FORMAT_INVALIDE")
        assert emprises == []
        assert codes == ""
        assert erreur is not None

    def test_trigramme_inconnu_retourne_erreur(self) -> None:
        _, _, erreur = resoudre_emprises_affaire("RAC-XYZ-25-001234")
        assert erreur is not None
        assert "XYZ" in erreur
