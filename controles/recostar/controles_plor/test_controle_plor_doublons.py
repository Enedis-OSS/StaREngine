"""
Tests unitaires du controle des doublons de points leves (controle_plor_doublons).

Couvre les cas nominaux et les cas limites :
- indexation des features par coordonnees
- detection des groupes de doublons
- gestion des geometries absentes, 2D ou non-Point
- propagation du CRS dans le GeoJSON de sortie
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_plor_doublons import (
    CHAMP_TYPE_LEVE,
    FICHIER_PLOR,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    champ_type_leve_present,
    construire_geojson_ecarts,
    detecter_doublons,
    executer_controle_cli,
    indexer_points_par_coordonnees,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #


def _construire_point(
    identifiant: str,
    coordonnees: list[float],
    type_leve: str | None = None,
) -> dict[str, Any]:
    """Construit une feature point PLOR minimale pour les tests."""
    proprietes: dict[str, Any] = {"id": identifiant}
    if type_leve is not None:
        proprietes[CHAMP_TYPE_LEVE] = type_leve
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "Point", "coordinates": coordonnees},
    }


# --------------------------------------------------------------------------- #
# Tests de l'indexation par coordonnees
# --------------------------------------------------------------------------- #


class TestIndexerParCoordonnees:
    """Tests du regroupement des features par coordonnees (X, Y, Z)."""

    def test_deux_points_identiques_dans_meme_groupe(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0]),
            _construire_point("p2", [1.0, 2.0, 3.0]),
        ]
        index = indexer_points_par_coordonnees(features)
        assert len(index) == 1
        assert len(index[(1.0, 2.0, 3.0)]) == 2

    def test_deux_points_distincts_dans_groupes_separes(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0]),
            _construire_point("p2", [4.0, 5.0, 6.0]),
        ]
        index = indexer_points_par_coordonnees(features)
        assert len(index) == 2
        assert len(index[(1.0, 2.0, 3.0)]) == 1

    def test_point_2d_est_ignore(self) -> None:
        features = [_construire_point("p1", [1.0, 2.0])]
        index = indexer_points_par_coordonnees(features)
        assert len(index) == 0

    def test_geometrie_non_point_est_ignoree(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "l1"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
            },
        }
        index = indexer_points_par_coordonnees([feature])
        assert len(index) == 0

    def test_geometrie_absente_est_ignoree(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "p1"},
            "geometry": None,
        }
        index = indexer_points_par_coordonnees([feature])
        assert len(index) == 0

    def test_collection_vide(self) -> None:
        assert indexer_points_par_coordonnees([]) == {}

    def test_trois_points_superposes(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0]),
            _construire_point("p2", [1.0, 2.0, 3.0]),
            _construire_point("p3", [1.0, 2.0, 3.0]),
        ]
        index = indexer_points_par_coordonnees(features)
        assert len(index[(1.0, 2.0, 3.0)]) == 3

    def test_ecart_z_cree_groupes_differents(self) -> None:
        """Deux points identiques en X,Y mais differents en Z ne sont pas doublons."""
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0]),
            _construire_point("p2", [1.0, 2.0, 4.0]),
        ]
        index = indexer_points_par_coordonnees(features)
        assert len(index) == 2


# --------------------------------------------------------------------------- #
# Tests de la detection des doublons
# --------------------------------------------------------------------------- #


class TestDetecterDoublons:
    """Tests de l'identification des groupes de doublons."""

    def test_groupe_unique_non_doublon(self) -> None:
        index = {(1.0, 2.0, 3.0): [_construire_point("p1", [1.0, 2.0, 3.0])]}
        anomalies = detecter_doublons(index)
        assert anomalies == []

    def test_groupe_de_deux_produit_deux_anomalies(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0]),
            _construire_point("p2", [1.0, 2.0, 3.0]),
        ]
        index = {(1.0, 2.0, 3.0): features}
        anomalies = detecter_doublons(index)
        assert len(anomalies) == 2
        assert all(a["nb_doublons"] == 2 for a in anomalies)
        ids = {a["id_entite"] for a in anomalies}
        assert ids == {"p1", "p2"}

    def test_groupe_de_trois_produit_trois_anomalies(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0]),
            _construire_point("p2", [1.0, 2.0, 3.0]),
            _construire_point("p3", [1.0, 2.0, 3.0]),
        ]
        index = {(1.0, 2.0, 3.0): features}
        anomalies = detecter_doublons(index)
        assert len(anomalies) == 3
        assert all(a["nb_doublons"] == 3 for a in anomalies)

    def test_index_vide_aucune_anomalie(self) -> None:
        assert detecter_doublons({}) == []

    def test_coordonnees_propagees(self) -> None:
        features = [
            _construire_point("p1", [10.0, 20.0, 30.0]),
            _construire_point("p2", [10.0, 20.0, 30.0]),
        ]
        index = {(10.0, 20.0, 30.0): features}
        anomalies = detecter_doublons(index)
        assert all(a["coordonnees"] == [10.0, 20.0, 30.0] for a in anomalies)

    def test_melange_doublons_et_non_doublons(self) -> None:
        index = {
            (1.0, 2.0, 3.0): [
                _construire_point("p1", [1.0, 2.0, 3.0]),
                _construire_point("p2", [1.0, 2.0, 3.0]),
            ],
            (4.0, 5.0, 6.0): [_construire_point("p3", [4.0, 5.0, 6.0])],
        }
        anomalies = detecter_doublons(index)
        assert len(anomalies) == 2
        assert all(a["coordonnees"] == [1.0, 2.0, 3.0] for a in anomalies)


# --------------------------------------------------------------------------- #
# Tests du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestGeojsonSortie:
    """Tests de la serialisation des doublons en FeatureCollection."""

    def test_structure_geojson_conforme(self) -> None:
        anomalies = [
            {"id_entite": "p1", "coordonnees": [1.0, 2.0, 3.0], "nb_doublons": 2},
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1
        feature = geojson["features"][0]
        assert feature["geometry"] == {
            "type": "Point",
            "coordinates": [1.0, 2.0, 3.0],
        }
        props = feature["properties"]
        assert props["id_entite"] == "p1"
        assert props["nb_doublons"] == 2
        assert props["type_anomalie"] == "doublon_geometrique"
        assert props["priorite"] == PRIORITE_ANOMALIE

    def test_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_priorite_est_information(self) -> None:
        anomalies = [
            {"id_entite": "p1", "coordonnees": [0.0, 0.0, 0.0], "nb_doublons": 2},
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["features"][0]["properties"]["priorite"] == "information"

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson


# --------------------------------------------------------------------------- #
# Tests CLI bout en bout avec tmp_path
# --------------------------------------------------------------------------- #


@pytest.fixture
def repertoire_test(tmp_path: Any) -> str:
    """Prepare un repertoire avec un fichier PLOR contenant des doublons."""
    crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
    plor_collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "crs": crs,
        "features": [
            _construire_point("p1", [1.0, 2.0, 3.0]),
            _construire_point("p2", [1.0, 2.0, 3.0]),
            _construire_point("p3", [4.0, 5.0, 6.0]),
            _construire_point("p4", [7.0, 8.0, 9.0]),
            _construire_point("p5", [7.0, 8.0, 9.0]),
            _construire_point("p6", [7.0, 8.0, 9.0]),
        ],
    }
    (tmp_path / FICHIER_PLOR).write_text(json.dumps(plor_collection), encoding="utf-8")
    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_execution_ecrit_fichier_sortie(self, repertoire_test: str) -> None:
        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        assert resultat["nombre_points_plor"] == 6
        assert resultat["nombre_groupes_doublons"] == 2
        # p1+p2 (2) + p4+p5+p6 (3) = 5 anomalies
        assert resultat["nombre_anomalies"] == 5
        chemin_sortie = os.path.join(repertoire_test, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)
        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 5

    def test_crs_propage_dans_sortie(self, repertoire_test: str) -> None:
        executer_controle_cli(repertoire_test)
        chemin_sortie = os.path.join(repertoire_test, FICHIER_SORTIE)
        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert "crs" in contenu
        assert contenu["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::2154"

    def test_repertoire_sortie_distinct(
        self, repertoire_test: str, tmp_path: Any
    ) -> None:
        dossier_sortie = tmp_path / "sortie"
        resultat = executer_controle_cli(repertoire_test, str(dossier_sortie))
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(str(dossier_sortie), FICHIER_SORTIE))

    def test_repertoire_inexistant_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path / "inexistant"))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_fichier_plor_manquant_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert FICHIER_PLOR in resultat["erreur"]

    def test_aucun_doublon_si_tous_distincts(self, tmp_path: Any) -> None:
        plor: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [
                _construire_point("p1", [1.0, 2.0, 3.0]),
                _construire_point("p2", [4.0, 5.0, 6.0]),
            ],
        }
        (tmp_path / FICHIER_PLOR).write_text(json.dumps(plor), encoding="utf-8")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_groupes_doublons"] == 0


# --------------------------------------------------------------------------- #
# Tests de la detection du champ TypeLeve
# --------------------------------------------------------------------------- #


class TestChampTypeLeve:
    """Tests de la detection de la presence du champ TypeLeve."""

    def test_champ_present_si_au_moins_une_feature(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
            _construire_point("p2", [1.0, 2.0, 3.0]),
        ]
        assert champ_type_leve_present(features) is True

    def test_champ_absent_si_aucune_feature(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0]),
            _construire_point("p2", [4.0, 5.0, 6.0]),
        ]
        assert champ_type_leve_present(features) is False

    def test_collection_vide(self) -> None:
        assert champ_type_leve_present([]) is False


# --------------------------------------------------------------------------- #
# Tests de la segmentation par TypeLeve
# --------------------------------------------------------------------------- #


class TestSegmentationTypeLeve:
    """Tests de l'indexation et detection segmentees par TypeLeve."""

    def test_meme_position_meme_type_sont_doublons(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
            _construire_point("p2", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
        ]
        index = indexer_points_par_coordonnees(features, segmenter_par_type=True)
        anomalies = detecter_doublons(index)
        assert len(anomalies) == 2
        assert all(a["coordonnees"] == [1.0, 2.0, 3.0] for a in anomalies)

    def test_meme_position_types_differents_pas_doublons(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
            _construire_point("p2", [1.0, 2.0, 3.0], "ChargeGeneratrice"),
        ]
        index = indexer_points_par_coordonnees(features, segmenter_par_type=True)
        anomalies = detecter_doublons(index)
        assert len(anomalies) == 0

    def test_positions_differentes_meme_type_pas_doublons(self) -> None:
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
            _construire_point("p2", [4.0, 5.0, 6.0], "AltitudeGeneratrice"),
        ]
        index = indexer_points_par_coordonnees(features, segmenter_par_type=True)
        anomalies = detecter_doublons(index)
        assert len(anomalies) == 0

    def test_mixte_doublons_et_non_doublons_par_type(self) -> None:
        """Deux AltitudeGeneratrice superposes + un ChargeGeneratrice au meme endroit."""
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
            _construire_point("p2", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
            _construire_point("p3", [1.0, 2.0, 3.0], "ChargeGeneratrice"),
        ]
        index = indexer_points_par_coordonnees(features, segmenter_par_type=True)
        anomalies = detecter_doublons(index)
        assert len(anomalies) == 2
        ids = {a["id_entite"] for a in anomalies}
        assert ids == {"p1", "p2"}

    def test_sans_segmentation_meme_position_types_differents_sont_doublons(
        self,
    ) -> None:
        """Sans segmentation, les types differents au meme endroit sont doublons."""
        features = [
            _construire_point("p1", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
            _construire_point("p2", [1.0, 2.0, 3.0], "ChargeGeneratrice"),
        ]
        index = indexer_points_par_coordonnees(features, segmenter_par_type=False)
        anomalies = detecter_doublons(index)
        assert len(anomalies) == 2


# --------------------------------------------------------------------------- #
# Tests CLI avec TypeLeve
# --------------------------------------------------------------------------- #


class TestCliTypeLeve:
    """Tests d'integration CLI avec le champ TypeLeve."""

    def test_doublons_segmentes_par_type(self, tmp_path: Any) -> None:
        """Meme coordonnees, types differents => pas doublons."""
        plor: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [
                _construire_point("p1", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
                _construire_point("p2", [1.0, 2.0, 3.0], "ChargeGeneratrice"),
            ],
        }
        (tmp_path / FICHIER_PLOR).write_text(json.dumps(plor), encoding="utf-8")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_doublons_meme_type_detectes(self, tmp_path: Any) -> None:
        """Meme coordonnees, meme type => doublons."""
        plor: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [
                _construire_point("p1", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
                _construire_point("p2", [1.0, 2.0, 3.0], "AltitudeGeneratrice"),
                _construire_point("p3", [1.0, 2.0, 3.0], "ChargeGeneratrice"),
            ],
        }
        (tmp_path / FICHIER_PLOR).write_text(json.dumps(plor), encoding="utf-8")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 2
        assert resultat["nombre_groupes_doublons"] == 1
