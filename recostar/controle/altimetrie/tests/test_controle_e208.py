"""
Tests unitaires du controle E208 (rattachement des sommets de cables aux points
de leve : superposition exacte et egalite stricte X, Y, Z).

Couvre :
- indexation des points de leve par XY (Point 3D seulement, ensemble de Z) ;
- extraction des sommets (LineString / MultiLineString aplati) ;
- classification d'un sommet (conforme / point_leve_absent / coordonnees_differentes) ;
- detection sur une liste de cables (id, couche, indice conserves) ;
- construction du GeoJSON de sortie ;
- execution CLI bout en bout : perimetre par version, filtre Statut, rapport.
"""

from __future__ import annotations

import json
import os
from typing import Any

from controle_e202 import (
    FICHIER_AERIEN,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_CABLE_TELECOM,
    FICHIER_CABLE_TERRE,
)
from controle_e204 import CHAMP_TYPE_LEVE, VERSION_DEFAUT
from controle_e205 import FICHIER_GEOM_SUPP, FICHIER_POINT_LEVE
from controle_e208 import (
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    TYPE_ANO_ABSENT,
    TYPE_ANO_COORD,
    IndexGeomSupp,
    _classifier_sommet,
    _extraire_sommets_cable,
    charger_geometries_supplementaires,
    construire_geojson_ecarts,
    detecter_sommets_incoherents,
    executer_controle_cli,
    indexer_points_leve_par_xy,
)
from utils_tests import (
    construire_feature,
    construire_feature_avec_proprietes,
    ecrire_collection,
)

CHAMP_STATUT = "Statut"
STATUT_CONTROLE = "UnderCommissionning"


def _feature_point_leve(
    identifiant: str,
    coords: list[float],
    avec_type_leve: bool = False,
) -> dict[str, Any]:
    """Feature point de leve Point, avec ou sans champ TypeLeve (discriminant v1.0)."""
    if avec_type_leve:
        return construire_feature_avec_proprietes(
            identifiant, "Point", coords, {CHAMP_TYPE_LEVE: "AltitudeGeneratrice"}
        )
    return construire_feature(identifiant, "Point", coords)


def _feature_cable(
    identifiant: str,
    type_geom: str,
    coords: Any,
    statut: str | None = STATUT_CONTROLE,
) -> dict[str, Any]:
    """Feature cable (LineString/MultiLineString) avec statut optionnel."""
    props: dict[str, Any] = {}
    if statut is not None:
        props[CHAMP_STATUT] = statut
    return construire_feature_avec_proprietes(identifiant, type_geom, coords, props)


# ---------------------------------------------------------------------------
# Tests de indexer_points_leve_par_xy
# ---------------------------------------------------------------------------


class TestIndexerPointsLeveParXy:
    def test_point_3d_indexe(self) -> None:
        index = indexer_points_leve_par_xy([_feature_point_leve("p1", [1.0, 2.0, 3.0])])
        assert index == {(1.0, 2.0): {3.0}}

    def test_point_2d_ignore(self) -> None:
        index = indexer_points_leve_par_xy([_feature_point_leve("p1", [1.0, 2.0])])
        assert index.get((1.0, 2.0)) is None

    def test_geometrie_non_point_ignoree(self) -> None:
        ligne = construire_feature("l1", "LineString", [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        assert indexer_points_leve_par_xy([ligne]) == {}

    def test_plusieurs_z_meme_xy(self) -> None:
        features = [
            _feature_point_leve("p1", [1.0, 2.0, 3.0]),
            _feature_point_leve("p2", [1.0, 2.0, 4.0]),
        ]
        assert indexer_points_leve_par_xy(features)[(1.0, 2.0)] == {3.0, 4.0}

    def test_collection_vide(self) -> None:
        assert indexer_points_leve_par_xy([]) == {}


# ---------------------------------------------------------------------------
# Tests de _extraire_sommets_cable
# ---------------------------------------------------------------------------


class TestExtraireSommetsCable:
    def test_linestring(self) -> None:
        geom = {"type": "LineString", "coordinates": [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]]}
        assert _extraire_sommets_cable(geom) == [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]]

    def test_multilinestring_aplati(self) -> None:
        geom = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]],
                [[2.0, 2.0, 3.0], [3.0, 3.0, 4.0]],
            ],
        }
        sommets = _extraire_sommets_cable(geom)
        assert len(sommets) == 4
        assert sommets[2] == [2.0, 2.0, 3.0]

    def test_type_non_gere(self) -> None:
        assert _extraire_sommets_cable({"type": "Point", "coordinates": [0.0, 0.0, 0.0]}) == []

    def test_coordonnees_absentes(self) -> None:
        assert _extraire_sommets_cable({"type": "LineString"}) == []


# ---------------------------------------------------------------------------
# Tests de _classifier_sommet
# ---------------------------------------------------------------------------


class TestClassifierSommet:
    _INDEX = {(0.0, 0.0): {1.0}}

    def test_conforme(self) -> None:
        assert _classifier_sommet([0.0, 0.0, 1.0], self._INDEX) is None

    def test_xy_absent(self) -> None:
        assert _classifier_sommet([9.0, 9.0, 1.0], self._INDEX) == TYPE_ANO_ABSENT

    def test_z_different(self) -> None:
        assert _classifier_sommet([0.0, 0.0, 5.0], self._INDEX) == TYPE_ANO_COORD

    def test_sommet_2d_xy_present(self) -> None:
        # XY superpose mais pas de Z : egalite stricte impossible.
        assert _classifier_sommet([0.0, 0.0], self._INDEX) == TYPE_ANO_COORD

    def test_sommet_malforme_ignore(self) -> None:
        assert _classifier_sommet([0.0], self._INDEX) is None


# ---------------------------------------------------------------------------
# Tests de detecter_sommets_incoherents
# ---------------------------------------------------------------------------


class TestDetecterSommetsIncoherents:
    def _index(self, points: list[list[float]]) -> dict[tuple[float, float], set[float]]:
        return indexer_points_leve_par_xy([_feature_point_leve(f"p{i}", c) for i, c in enumerate(points)])

    def test_cable_conforme_aucune_anomalie(self) -> None:
        cable = _feature_cable("c1", "LineString", [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]])
        index = self._index([[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]])
        assert detecter_sommets_incoherents([cable], index, set()) == []

    def test_sommet_sans_point_leve(self) -> None:
        cable = _feature_cable("c1", "LineString", [[0.0, 0.0, 1.0], [5.0, 5.0, 5.0]])
        index = self._index([[0.0, 0.0, 1.0]])
        anomalies = detecter_sommets_incoherents([cable], index, set())
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_ANO_ABSENT
        assert anomalies[0]["id_cable"] == "c1"
        assert anomalies[0]["indice_sommet"] == 1
        assert anomalies[0]["coordonnees"] == [5.0, 5.0, 5.0]

    def test_sommet_z_different(self) -> None:
        cable = _feature_cable("c1", "LineString", [[0.0, 0.0, 9.0], [1.0, 1.0, 2.0]])
        index = self._index([[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]])
        anomalies = detecter_sommets_incoherents([cable], index, set())
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_ANO_COORD
        assert anomalies[0]["indice_sommet"] == 0

    def test_multilinestring_indices_continus(self) -> None:
        cable = _feature_cable(
            "c1",
            "MultiLineString",
            [[[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]], [[8.0, 8.0, 8.0], [3.0, 3.0, 4.0]]],
        )
        index = self._index([[0.0, 0.0, 1.0], [1.0, 1.0, 2.0], [3.0, 3.0, 4.0]])
        anomalies = detecter_sommets_incoherents([cable], index, set())
        assert len(anomalies) == 1
        assert anomalies[0]["indice_sommet"] == 2  # 3e sommet aplati

    def test_cable_sans_geometrie_ignore(self) -> None:
        cable: dict[str, Any] = {"type": "Feature", "properties": {"id": "c1"}, "geometry": None}
        assert detecter_sommets_incoherents([cable], {}, set()) == []

    def test_cable_aerien_exclu(self) -> None:
        # Un cable reference par l'aerien est ignore, meme avec un sommet non leve.
        cable = _feature_cable("c1", "LineString", [[5.0, 5.0, 5.0], [6.0, 6.0, 6.0]])
        assert detecter_sommets_incoherents([cable], {}, {"c1"}) == []


# ---------------------------------------------------------------------------
# Tests de construire_geojson_ecarts
# ---------------------------------------------------------------------------


class TestConstruireGeojsonEcarts:
    def test_collection_vide(self) -> None:
        assert construire_geojson_ecarts([], "1.1") == {"type": "FeatureCollection", "features": []}

    def test_structure_feature(self) -> None:
        anomalies = [
            {
                "id_cable": "c1",
                "couche": "RPD_CableElectrique_Reco",
                "indice_sommet": 2,
                "coordonnees": [1.0, 2.0, 3.0],
                "type_anomalie": TYPE_ANO_ABSENT,
            }
        ]
        feat = construire_geojson_ecarts(anomalies, "1.0")["features"][0]
        assert feat["geometry"] == {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        props = feat["properties"]
        assert props["id_cable"] == "c1"
        assert props["couche"] == "RPD_CableElectrique_Reco"
        assert props["indice_sommet"] == 2
        assert props["type_anomalie"] == TYPE_ANO_ABSENT
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["version"] == "1.0"

    def test_crs_propage(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], "1.1", crs=crs)["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        assert "crs" not in construire_geojson_ecarts([], "1.1")


# ---------------------------------------------------------------------------
# Helpers CLI
# ---------------------------------------------------------------------------


def _feature_aerien(cables_href: str) -> dict[str, Any]:
    """Feature cheminement aerien referencant un ou plusieurs cables (separes par des espaces)."""
    return construire_feature_avec_proprietes(
        "a1", "LineString", [[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]], {"cables_href": cables_href}
    )


def _ecrire_sources(
    repertoire: str,
    points: list[dict[str, Any]],
    electrique: list[dict[str, Any]] | None = None,
    terre: list[dict[str, Any]] | None = None,
    telecom: list[dict[str, Any]] | None = None,
    aerien: list[dict[str, Any]] | None = None,
    geomsupp: list[dict[str, Any]] | None = None,
) -> None:
    """Ecrit les fichiers sources presents dans le repertoire de test."""
    ecrire_collection(os.path.join(repertoire, FICHIER_POINT_LEVE), points)
    if electrique is not None:
        ecrire_collection(os.path.join(repertoire, FICHIER_CABLE_ELECTRIQUE), electrique)
    if terre is not None:
        ecrire_collection(os.path.join(repertoire, FICHIER_CABLE_TERRE), terre)
    if telecom is not None:
        ecrire_collection(os.path.join(repertoire, FICHIER_CABLE_TELECOM), telecom)
    if aerien is not None:
        ecrire_collection(os.path.join(repertoire, FICHIER_AERIEN), aerien)
    if geomsupp is not None:
        ecrire_collection(os.path.join(repertoire, FICHIER_GEOM_SUPP), geomsupp)


# ---------------------------------------------------------------------------
# Tests CLI bout en bout
# ---------------------------------------------------------------------------


class TestCli:
    def test_fichier_point_leve_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_aucune_couche_cable_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False

    def test_v1_0_sans_anomalie(self, tmp_path: Any) -> None:
        points = [
            _feature_point_leve("p1", [0.0, 0.0, 1.0], avec_type_leve=True),
            _feature_point_leve("p2", [1.0, 1.0, 2.0], avec_type_leve=True),
        ]
        cable = _feature_cable("c1", "LineString", [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]])
        _ecrire_sources(str(tmp_path), points, electrique=[cable], terre=[])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["version_detectee"] == "1.0"
        assert resultat["nombre_anomalies"] == 0
        assert resultat["couches_controlees"] == ["RPD_CableElectrique_Reco", "RPD_CableTerre_Reco"]

    def test_v1_0_anomalie_absent(self, tmp_path: Any) -> None:
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0], avec_type_leve=True)]
        cable = _feature_cable("c1", "LineString", [[0.0, 0.0, 1.0], [5.0, 5.0, 5.0]])
        _ecrire_sources(str(tmp_path), points, electrique=[cable], terre=[])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_sommets_sans_point_leve"] == 1
        assert resultat["nombre_sommets_coordonnees_differentes"] == 0

    def test_v1_0_anomalie_z_different(self, tmp_path: Any) -> None:
        points = [
            _feature_point_leve("p1", [0.0, 0.0, 1.0], avec_type_leve=True),
            _feature_point_leve("p2", [1.0, 1.0, 2.0], avec_type_leve=True),
        ]
        cable = _feature_cable("c1", "LineString", [[0.0, 0.0, 9.0], [1.0, 1.0, 2.0]])
        _ecrire_sources(str(tmp_path), points, electrique=[cable], terre=[])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_sommets_coordonnees_differentes"] == 1

    def test_v1_0_telecom_non_controle(self, tmp_path: Any) -> None:
        # En v1.0, la couche telecom n'est pas dans le perimetre.
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0], avec_type_leve=True)]
        telecom = [_feature_cable("t1", "LineString", [[5.0, 5.0, 5.0], [6.0, 6.0, 6.0]])]
        _ecrire_sources(str(tmp_path), points, electrique=[], terre=[], telecom=telecom)
        resultat = executer_controle_cli(str(tmp_path))
        assert "RPD_CableTelecommunication_Reco" not in resultat["couches_controlees"]
        assert resultat["nombre_anomalies"] == 0

    def test_v1_1_telecom_controle(self, tmp_path: Any) -> None:
        # Sans TypeLeve -> v1.1 : la couche telecom est controlee.
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0])]
        telecom = [_feature_cable("t1", "LineString", [[5.0, 5.0, 5.0], [6.0, 6.0, 6.0]])]
        _ecrire_sources(str(tmp_path), points, electrique=[], terre=[], telecom=telecom)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["version_detectee"] == VERSION_DEFAUT
        assert "RPD_CableTelecommunication_Reco" in resultat["couches_controlees"]
        assert resultat["nombre_anomalies"] == 2  # 2 sommets sans point de leve

    def test_statut_non_controle_ignore(self, tmp_path: Any) -> None:
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0])]
        cable = _feature_cable("c1", "LineString", [[5.0, 5.0, 5.0], [6.0, 6.0, 6.0]], statut="AutreStatut")
        _ecrire_sources(str(tmp_path), points, electrique=[cable], terre=[])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0

    def test_cable_aerien_exclu(self, tmp_path: Any) -> None:
        # Cable reference par l'aerien : exclu du controle malgre ses sommets non leves.
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0])]
        cable = _feature_cable("c1", "LineString", [[5.0, 5.0, 5.0], [6.0, 6.0, 6.0]])
        _ecrire_sources(str(tmp_path), points, electrique=[cable], aerien=[_feature_aerien("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["cables_exclus"] == 1
        assert resultat["nombre_anomalies"] == 0

    def test_sans_fichier_aerien_aucune_exclusion(self, tmp_path: Any) -> None:
        # L'absence du fichier aerien n'est pas bloquante : aucune exclusion.
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0])]
        cable = _feature_cable("c1", "LineString", [[5.0, 5.0, 5.0], [6.0, 6.0, 6.0]])
        _ecrire_sources(str(tmp_path), points, electrique=[cable])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["cables_exclus"] == 0
        assert resultat["nombre_anomalies"] == 2

    def test_version_explicite_surcharge(self, tmp_path: Any) -> None:
        # TypeLeve present (signal v1.0) mais version forcee a 1.1.
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0], avec_type_leve=True)]
        _ecrire_sources(str(tmp_path), points, electrique=[], terre=[], telecom=[])
        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat["version_detectee"] == "1.1"
        assert "RPD_CableTelecommunication_Reco" in resultat["couches_controlees"]

    def test_ecrit_fichier_sortie(self, tmp_path: Any) -> None:
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0])]
        cable = _feature_cable("c1", "LineString", [[5.0, 5.0, 5.0], [6.0, 6.0, 6.0]])
        _ecrire_sources(str(tmp_path), points, electrique=[cable], terre=[])
        executer_controle_cli(str(tmp_path))
        chemin = str(tmp_path / FICHIER_SORTIE)
        assert os.path.isfile(chemin)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 2

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0])]
        _ecrire_sources(str(tmp_path), points, electrique=[])
        dossier_sortie = str(tmp_path / "sortie")
        resultat = executer_controle_cli(str(tmp_path), dossier_sortie)
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))

    def test_rapport_inclut_priorite_et_version(self, tmp_path: Any) -> None:
        points = [_feature_point_leve("p1", [0.0, 0.0, 1.0])]
        _ecrire_sources(str(tmp_path), points, electrique=[])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["priorite"] == PRIORITE_ANOMALIE
        assert "version_detectee" in resultat


# ---------------------------------------------------------------------------
# Exception : extremite en contact avec une geometrie supplementaire
# ---------------------------------------------------------------------------


def charger_geometries_supplementaires_depuis(features: list[dict[str, Any]]) -> list[Any]:
    """Convertit des features en geometries Shapely 2D (equivalent en memoire du chargement)."""
    from shapely import force_2d
    from shapely.geometry import shape

    return [force_2d(shape(f["geometry"])) for f in features]


def _carre(cx: float, cy: float, demi: float = 1.0) -> dict[str, Any]:
    """Feature Polygon carree centree sur (cx, cy), pour simuler une geom. supp."""
    anneau = [
        [cx - demi, cy - demi],
        [cx + demi, cy - demi],
        [cx + demi, cy + demi],
        [cx - demi, cy + demi],
        [cx - demi, cy - demi],
    ]
    return {
        "type": "Feature",
        "properties": {"id": "gs1"},
        "geometry": {"type": "Polygon", "coordinates": [anneau]},
    }


def _cable_3_sommets() -> dict[str, Any]:
    """Cable UnderCommissionning : extremites (0,0) et (100,0), intermediaire (50,0)."""
    return _feature_cable("c1", "LineString", [[0.0, 0.0, 10.0], [50.0, 0.0, 10.0], [100.0, 0.0, 10.0]])


class TestIndexGeomSupp:
    """Tests de IndexGeomSupp."""

    def test_contact_a_l_interieur(self) -> None:
        index = IndexGeomSupp(charger_geometries_supplementaires_depuis([_carre(0.0, 0.0)]))
        assert index.en_contact(0.0, 0.0) is True

    def test_contact_sur_le_bord(self) -> None:
        """Le predicat 'intersects' couvre le contour, pas seulement l'interieur."""
        index = IndexGeomSupp(charger_geometries_supplementaires_depuis([_carre(0.0, 0.0)]))
        assert index.en_contact(1.0, 0.0) is True

    def test_hors_contact(self) -> None:
        index = IndexGeomSupp(charger_geometries_supplementaires_depuis([_carre(0.0, 0.0)]))
        assert index.en_contact(50.0, 50.0) is False

    def test_index_vide_aucun_contact(self) -> None:
        """Aucune geometrie supplementaire : aucune exemption, sans erreur."""
        assert IndexGeomSupp([]).en_contact(0.0, 0.0) is False


class TestChargerGeometriesSupplementaires:
    """Tests de charger_geometries_supplementaires."""

    def test_fichier_absent_liste_vide(self, tmp_path: Any) -> None:
        assert charger_geometries_supplementaires(str(tmp_path)) == []

    def test_chargement(self, tmp_path: Any) -> None:
        ecrire_collection(os.path.join(str(tmp_path), FICHIER_GEOM_SUPP), [_carre(0.0, 0.0)])
        assert len(charger_geometries_supplementaires(str(tmp_path))) == 1

    def test_geometrie_absente_ignoree(self, tmp_path: Any) -> None:
        feature = {"type": "Feature", "properties": {"id": "x"}, "geometry": None}
        ecrire_collection(os.path.join(str(tmp_path), FICHIER_GEOM_SUPP), [feature])
        assert charger_geometries_supplementaires(str(tmp_path)) == []


class TestExceptionExtremiteGeomSupp:
    """Tests de l'exception d'extremite en contact avec une geometrie supplementaire."""

    def test_extremite_en_contact_exemptee(self) -> None:
        """Aucun point de leve, mais l'extremite touche une geometrie supplementaire."""
        index_gs = IndexGeomSupp(charger_geometries_supplementaires_depuis([_carre(0.0, 0.0)]))
        anomalies = detecter_sommets_incoherents([_cable_3_sommets()], {}, set(), index_gs)
        indices = {a["indice_sommet"] for a in anomalies}
        assert 0 not in indices  # extremite exemptee
        assert indices == {1, 2}  # intermediaire et autre extremite signalees

    def test_sommet_intermediaire_jamais_exempte(self) -> None:
        """L'exception ne vaut que pour les extremites (regle du controle)."""
        index_gs = IndexGeomSupp(charger_geometries_supplementaires_depuis([_carre(50.0, 0.0)]))
        anomalies = detecter_sommets_incoherents([_cable_3_sommets()], {}, set(), index_gs)
        assert 1 in {a["indice_sommet"] for a in anomalies}

    def test_deux_extremites_en_contact(self) -> None:
        geoms = charger_geometries_supplementaires_depuis([_carre(0.0, 0.0), _carre(100.0, 0.0)])
        anomalies = detecter_sommets_incoherents([_cable_3_sommets()], {}, set(), IndexGeomSupp(geoms))
        assert {a["indice_sommet"] for a in anomalies} == {1}

    def test_coordonnees_differentes_non_exemptee(self) -> None:
        """Un Z divergent reste signale : l'ouvrage est leve, mais mal."""
        index_points = {(0.0, 0.0): {99.0}}  # meme XY, Z different
        index_gs = IndexGeomSupp(charger_geometries_supplementaires_depuis([_carre(0.0, 0.0)]))
        anomalies = detecter_sommets_incoherents([_cable_3_sommets()], index_points, set(), index_gs)
        sommet0 = [a for a in anomalies if a["indice_sommet"] == 0]
        assert len(sommet0) == 1
        assert sommet0[0]["type_anomalie"] == TYPE_ANO_COORD

    def test_extremite_hors_contact_signalee(self) -> None:
        index_gs = IndexGeomSupp(charger_geometries_supplementaires_depuis([_carre(500.0, 500.0)]))
        anomalies = detecter_sommets_incoherents([_cable_3_sommets()], {}, set(), index_gs)
        assert {a["indice_sommet"] for a in anomalies} == {0, 1, 2}

    def test_sans_index_comportement_historique(self) -> None:
        """Regression : sans index, aucune exemption — comportement d'origine."""
        anomalies = detecter_sommets_incoherents([_cable_3_sommets()], {}, set())
        assert {a["indice_sommet"] for a in anomalies} == {0, 1, 2}

    def test_extremites_topologiques_multilinestring(self) -> None:
        """Les parties d'un MultiLineString ne sont ni ordonnees ni orientees.

        Parties : (10,0)->(20,0) et (30,0)->(20,0). Les vraies extremites sont
        (10,0) et (30,0) ; (20,0) est un raccord interne, jamais exempte.
        """
        cable = _feature_cable(
            "c1",
            "MultiLineString",
            [[[10.0, 0.0, 1.0], [20.0, 0.0, 1.0]], [[30.0, 0.0, 1.0], [20.0, 0.0, 1.0]]],
        )
        # Une geometrie supplementaire sur le raccord interne : aucune exemption
        index_gs = IndexGeomSupp(charger_geometries_supplementaires_depuis([_carre(20.0, 0.0)]))
        anomalies = detecter_sommets_incoherents([cable], {}, set(), index_gs)
        assert len(anomalies) == 4  # les 4 sommets restent signales

        # Une geometrie supplementaire sur une vraie extremite : elle est exemptee
        index_gs = IndexGeomSupp(charger_geometries_supplementaires_depuis([_carre(30.0, 0.0)]))
        anomalies = detecter_sommets_incoherents([cable], {}, set(), index_gs)
        assert len(anomalies) == 3


class TestCliExceptionGeomSupp:
    """Tests CLI de l'exception d'extremite."""

    def test_exemption_bout_en_bout(self, tmp_path: Any) -> None:
        points = [_feature_point_leve("p1", [50.0, 0.0, 10.0])]  # ne couvre que l'intermediaire
        _ecrire_sources(
            str(tmp_path),
            points,
            electrique=[_cable_3_sommets()],
            terre=[],
            geomsupp=[_carre(0.0, 0.0), _carre(100.0, 0.0)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["geometries_supplementaires_indexees"] == 2

    def test_sans_fichier_geomsupp_non_bloquant(self, tmp_path: Any) -> None:
        """Regression : l'absence du fichier conserve le comportement d'origine."""
        points = [_feature_point_leve("p1", [50.0, 0.0, 10.0])]
        _ecrire_sources(str(tmp_path), points, electrique=[_cable_3_sommets()], terre=[])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 2  # les deux extremites
        assert resultat["geometries_supplementaires_indexees"] == 0
