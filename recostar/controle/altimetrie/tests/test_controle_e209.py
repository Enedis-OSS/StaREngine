"""
Tests unitaires du controle E209 (points de leve orphelins).

Couvre :
- chargement des geometries en 2D (tous types, Z ignore, malformees ignorees) ;
- chargement des autres fichiers (exclusion du fichier source et des ecarts_) ;
- detection des orphelins (superpose / non superpose / arbre vide) ;
- tolerance planimetrique de superposition (point entre deux sommets) ;
- exclusion des points de leve entre eux (meme fichier non pris en compte) ;
- construction du GeoJSON de sortie ;
- execution CLI bout en bout.
"""

from __future__ import annotations

import json
import os
from typing import Any

from controle_e209 import (
    FICHIER_SORTIE,
    FICHIER_SOURCE,
    PRIORITE_ANOMALIE,
    TOLERANCE_SUPERPOSITION,
    _charger_geometries_2d,
    charger_geometries_autres_fichiers,
    construire_geojson_ecarts,
    detecter_points_leve_orphelins,
    executer_controle_cli,
)
from utils_tests import construire_feature, ecrire_collection

# Carre 2D 1m x 1m : le point (0.5, 0.5) est a l'interieur.
_POLY_1M = [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]
_POINT_INTERIEUR = [0.5, 0.5, 3.0]
_POINT_EXTERIEUR = [50.0, 50.0, 3.0]

# Nom arbitraire d'un autre fichier metier (different du fichier source)
FICHIER_AUTRE = "RPD_Coffret_Reco.geojson"

# Segment horizontal de 10 m servant de reference aux tests de tolerance.
_SEGMENT_10M = [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]

# Coordonnees reelles issues de Echantillon3 (Nevoy_RecolementHTA), a l'origine
# de la regression : deux points de leve poses entre deux sommets de cable,
# declares orphelins a tort par l'ancien predicat « intersects ».
#
# Cas 1 (NumeroPoint 16) : milieu arithmetique exact du segment. Le point est
# mathematiquement colineaire, mais le calcul flottant laisse un residu de
# 4,3e-10 m.
_SEGMENT_CABLE_16 = [[668683.708, 6735670.352, 0.0], [668683.15, 6735670.596, 0.0]]
_POINT_LEVE_16 = [668683.429, 6735670.474, 0.0]

# Cas 2 (NumeroPoint 21) : milieu du segment arrondi au millimetre a la source,
# soit un ecart reel de 2,3e-4 m.
_SEGMENT_CABLE_21 = [[668683.578, 6735670.133, 0.0], [668683.031, 6735670.398, 0.0]]
_POINT_LEVE_21 = [668683.305, 6735670.265, 0.0]


def _feature_point(identifiant: str, coords: list[float]) -> dict[str, Any]:
    """Feature point de leve Point."""
    return construire_feature(identifiant, "Point", coords)


def _geometries(features: list[dict[str, Any]]) -> list[Any]:
    """Raccourci : charge les geometries 2D d'une liste de features."""
    return _charger_geometries_2d(features)


# ---------------------------------------------------------------------------
# Tests de _charger_geometries_2d
# ---------------------------------------------------------------------------


class TestChargerGeometries2d:
    def test_point_3d_force_2d(self) -> None:
        geoms = _charger_geometries_2d([_feature_point("p1", [1.0, 2.0, 3.0])])
        assert len(geoms) == 1
        assert geoms[0].has_z is False

    def test_polygone_charge(self) -> None:
        poly = construire_feature("gs1", "Polygon", _POLY_1M)
        assert len(_charger_geometries_2d([poly])) == 1

    def test_linestring_charge(self) -> None:
        ligne = construire_feature("l1", "LineString", [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]])
        assert len(_charger_geometries_2d([ligne])) == 1

    def test_geometrie_absente_ignoree(self) -> None:
        feature: dict[str, Any] = {"type": "Feature", "properties": {"id": "x"}, "geometry": None}
        assert _charger_geometries_2d([feature]) == []

    def test_collection_vide(self) -> None:
        assert _charger_geometries_2d([]) == []


# ---------------------------------------------------------------------------
# Tests de charger_geometries_autres_fichiers
# ---------------------------------------------------------------------------


class TestChargerGeometriesAutresFichiers:
    def test_exclut_fichier_source(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [_feature_point("p1", [0.0, 0.0, 1.0])])
        ecrire_collection(str(tmp_path / FICHIER_AUTRE), [_feature_point("c1", [0.0, 0.0, 1.0])])
        geoms, nb = charger_geometries_autres_fichiers(str(tmp_path), FICHIER_SOURCE)
        # Seul le fichier autre est charge (1 geometrie), pas le fichier source
        assert nb == 1
        assert len(geoms) == 1

    def test_exclut_fichiers_ecarts(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_AUTRE), [_feature_point("c1", [0.0, 0.0, 1.0])])
        ecrire_collection(str(tmp_path / "ecarts_e200_3d.geojson"), [_feature_point("e1", [9.0, 9.0, 9.0])])
        geoms, nb = charger_geometries_autres_fichiers(str(tmp_path), FICHIER_SOURCE)
        assert nb == 1  # ecarts_ exclu par lister_fichiers_geojson
        assert len(geoms) == 1

    def test_aucun_autre_fichier(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [_feature_point("p1", [0.0, 0.0, 1.0])])
        geoms, nb = charger_geometries_autres_fichiers(str(tmp_path), FICHIER_SOURCE)
        assert nb == 0
        assert geoms == []


# ---------------------------------------------------------------------------
# Tests de detecter_points_leve_orphelins
# ---------------------------------------------------------------------------


class TestDetecterPointsLeveOrphelins:
    def test_point_superpose_polygone_conforme(self) -> None:
        points = [_feature_point("p1", _POINT_INTERIEUR)]
        autres = _geometries([construire_feature("gs1", "Polygon", _POLY_1M)])
        assert detecter_points_leve_orphelins(points, autres) == []

    def test_point_superpose_autre_point_conforme(self) -> None:
        points = [_feature_point("p1", [0.0, 0.0, 1.0])]
        autres = _geometries([construire_feature("c1", "Point", [0.0, 0.0, 9.0])])
        # Superposition planimetrique : le Z different n'empeche pas l'intersection
        assert detecter_points_leve_orphelins(points, autres) == []

    def test_point_non_superpose_orphelin(self) -> None:
        points = [_feature_point("p1", _POINT_EXTERIEUR)]
        autres = _geometries([construire_feature("gs1", "Polygon", _POLY_1M)])
        anomalies = detecter_points_leve_orphelins(points, autres)
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "p1"

    def test_arbre_vide_tous_orphelins(self) -> None:
        points = [_feature_point("p1", [0.0, 0.0, 1.0]), _feature_point("p2", [1.0, 1.0, 2.0])]
        assert len(detecter_points_leve_orphelins(points, [])) == 2

    def test_feature_non_point_ignoree(self) -> None:
        ligne = construire_feature("l1", "LineString", [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]])
        assert detecter_points_leve_orphelins([ligne], []) == []

    def test_anomalie_conserve_geometrie(self) -> None:
        points = [_feature_point("p1", _POINT_EXTERIEUR)]
        anomalies = detecter_points_leve_orphelins(points, [])
        assert anomalies[0]["geometrie"]["type"] == "Point"
        assert anomalies[0]["geometrie"]["coordinates"] == _POINT_EXTERIEUR

    def test_mix_conforme_et_orphelin(self) -> None:
        points = [
            _feature_point("p1", _POINT_INTERIEUR),  # conforme
            _feature_point("p2", _POINT_EXTERIEUR),  # orphelin
        ]
        autres = _geometries([construire_feature("gs1", "Polygon", _POLY_1M)])
        anomalies = detecter_points_leve_orphelins(points, autres)
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "p2"


# ---------------------------------------------------------------------------
# Tests de la tolerance planimetrique de superposition
# ---------------------------------------------------------------------------


class TestToleranceSuperposition:
    """Verifie que la tolerance absorbe l'arrondi millimetrique de la donnee
    source sans masquer un point de leve reellement egare."""

    def _orphelins(self, coords_point: list[float], segment: list[list[float]]) -> int:
        """Nombre d'orphelins pour un point de leve face a un segment unique."""
        autres = _geometries([construire_feature("c1", "LineString", segment)])
        return len(detecter_points_leve_orphelins([_feature_point("p1", coords_point)], autres))

    def test_tolerance_vaut_un_millimetre(self) -> None:
        assert TOLERANCE_SUPERPOSITION == 0.001

    def test_point_au_milieu_exact_du_segment_conforme(self) -> None:
        # Regression Echantillon3 / NumeroPoint 16 : residu flottant de 4,3e-10 m
        assert self._orphelins(_POINT_LEVE_16, _SEGMENT_CABLE_16) == 0

    def test_point_au_milieu_arrondi_au_millimetre_conforme(self) -> None:
        # Regression Echantillon3 / NumeroPoint 21 : ecart reel de 2,3e-4 m
        assert self._orphelins(_POINT_LEVE_21, _SEGMENT_CABLE_21) == 0

    def test_point_a_la_tolerance_exacte_conforme(self) -> None:
        # dwithin est inclusif : une distance egale a la tolerance est acceptee
        assert self._orphelins([5.0, TOLERANCE_SUPERPOSITION, 0.0], _SEGMENT_10M) == 0

    def test_point_juste_au_dela_de_la_tolerance_orphelin(self) -> None:
        assert self._orphelins([5.0, 0.0011, 0.0], _SEGMENT_10M) == 1

    def test_point_ecarte_d_un_centimetre_reste_orphelin(self) -> None:
        # La tolerance ne doit pas absorber une vraie erreur de saisie terrain
        assert self._orphelins([5.0, 0.01, 0.0], _SEGMENT_10M) == 1

    def test_tolerance_appliquee_bout_en_bout(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [_feature_point("p1", _POINT_LEVE_16)])
        ecrire_collection(
            str(tmp_path / FICHIER_AUTRE),
            [construire_feature("c1", "LineString", _SEGMENT_CABLE_16)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0


# ---------------------------------------------------------------------------
# Tests de construire_geojson_ecarts
# ---------------------------------------------------------------------------


class TestConstruireGeojsonEcarts:
    def test_collection_vide(self) -> None:
        assert construire_geojson_ecarts([]) == {"type": "FeatureCollection", "features": []}

    def test_structure_feature(self) -> None:
        anomalies = [{"id_entite": "p1", "geometrie": {"type": "Point", "coordinates": _POINT_EXTERIEUR}}]
        feat = construire_geojson_ecarts(anomalies)["features"][0]
        assert feat["geometry"]["type"] == "Point"
        props = feat["properties"]
        assert props["id_entite"] == "p1"
        assert props["type_anomalie"] == "point_leve_orphelin"
        assert props["priorite"] == PRIORITE_ANOMALIE

    def test_crs_propage(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], crs=crs)["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        assert "crs" not in construire_geojson_ecarts([])

    def test_priorite_est_mineure(self) -> None:
        """Contrat explicite : un point leve orphelin est signale sans declasser la famille."""
        assert PRIORITE_ANOMALIE == "mineur"


# ---------------------------------------------------------------------------
# Tests CLI bout en bout
# ---------------------------------------------------------------------------


class TestCli:
    def test_repertoire_introuvable(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant/xyz")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichier_source_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_AUTRE), [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_point_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [_feature_point("p1", _POINT_INTERIEUR)])
        ecrire_collection(str(tmp_path / FICHIER_AUTRE), [construire_feature("gs1", "Polygon", _POLY_1M)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_points_controles"] == 1
        assert resultat["fichiers_analyses"] == 1

    def test_point_orphelin(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [_feature_point("p1", _POINT_EXTERIEUR)])
        ecrire_collection(str(tmp_path / FICHIER_AUTRE), [construire_feature("gs1", "Polygon", _POLY_1M)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_points_leve_entre_eux_non_comptes(self, tmp_path: Any) -> None:
        # Deux points de leve superposes : le meme fichier n'est pas pris en compte
        # -> les deux sont orphelins (aucun autre GeoJSON).
        points = [_feature_point("p1", [0.0, 0.0, 1.0]), _feature_point("p2", [0.0, 0.0, 5.0])]
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 2
        assert resultat["fichiers_analyses"] == 0

    def test_ecrit_fichier_sortie(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [_feature_point("p1", _POINT_EXTERIEUR)])
        ecrire_collection(str(tmp_path / FICHIER_AUTRE), [construire_feature("gs1", "Polygon", _POLY_1M)])
        executer_controle_cli(str(tmp_path))
        chemin = str(tmp_path / FICHIER_SORTIE)
        assert os.path.isfile(chemin)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 1

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [_feature_point("p1", _POINT_EXTERIEUR)])
        ecrire_collection(str(tmp_path / FICHIER_AUTRE), [construire_feature("gs1", "Polygon", _POLY_1M)])
        dossier_sortie = str(tmp_path / "sortie")
        resultat = executer_controle_cli(str(tmp_path), dossier_sortie)
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [_feature_point("p1", _POINT_INTERIEUR)])
        ecrire_collection(str(tmp_path / FICHIER_AUTRE), [construire_feature("gs1", "Polygon", _POLY_1M)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(os.path.join(str(tmp_path), FICHIER_SORTIE))

    def test_rapport_inclut_priorite(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["priorite"] == PRIORITE_ANOMALIE
