"""
Tests des utilitaires d'emprise DR communs (utils_emprise_dr_commun.py).

Couvre la mutualisation entre le controle E-5106 (entites hors emprise) et le
controle E-3304 (cables HTB dans l'emprise) :
  - unicite du module commun, sans relais dans les familles
  - chargement des emprises Polygon et MultiPolygon
  - resolution complete d'un numero d'affaire vers ses emprises
"""

import json
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.emprise_dr import (
    charger_emprises_dr,
    point_dans_emprises,
    resoudre_emprises_affaire,
)

# Racine du paquet de controle (repertoire parent de tests/).
_RACINE_CONTROLE = Path(__file__).resolve().parent.parent


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


class TestUniciteDuModuleCommun:
    """Le module commun doit rester l'unique implementation, sans module-relais.

    Les familles ont longtemps porte un `utils_emprise_dr.py` qui se contentait de
    reexporter ce module : un detour impose par les imports a plat, ou tous les
    relais partageaient le meme nom et se masquaient dans sys.modules. Depuis le
    passage en paquets, chaque famille importe directement
    `recostar.controle.fonctions_communes.emprise_dr`.

    Ce garde interdit la reapparition d'un tel relais : il reintroduirait une
    seconde adresse pour la meme logique, donc un risque de divergence.
    """

    def test_aucun_module_relais_dans_les_familles(self) -> None:
        relais = sorted(_RACINE_CONTROLE.glob("*/utils_emprise_dr.py"))
        assert relais == [], f"module-relais a supprimer : {[str(c) for c in relais]}"

    def test_module_commun_importable_a_son_adresse_canonique(self) -> None:
        """L'adresse unique du module doit rester resolvable par les familles."""
        from importlib import import_module

        assert import_module("recostar.controle.fonctions_communes.emprise_dr") is not None


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
