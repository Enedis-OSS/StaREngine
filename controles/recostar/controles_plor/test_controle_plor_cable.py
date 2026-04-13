"""
Tests unitaires du controle de superposition PLOR/cables.

Couvre les cas nominaux et les cas limites :
- extraction des sommets 3D tous types de geometries
- detection des points PLOR hors cables
- exclusion des points PLOR superposes a d'autres entites RPD
- propagation du CRS dans le GeoJSON de sortie
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_plor_cable import (
    FICHIER_CABLES,
    FICHIER_PLOR,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    _extraire_sommets_geometrie,
    collecter_sommets_rpd,
    construire_geojson_ecarts,
    detecter_points_hors_cables,
    executer_controle_cli,
    extraire_sommets_features,
    lister_fichiers_rpd,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #


def _construire_point_plor(
    identifiant: str, coordonnees: list[float]
) -> dict[str, Any]:
    """Construit une feature point PLOR minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "Point", "coordinates": coordonnees},
    }


def _construire_cable(
    identifiant: str, coordonnees: list[list[float]]
) -> dict[str, Any]:
    """Construit une feature cable electrique minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


# --------------------------------------------------------------------------- #
# Tests d'extraction des sommets (tous types de geometries)
# --------------------------------------------------------------------------- #


class TestExtraireSommetsGeometrie:
    """Tests unitaires de l'extraction des sommets 3D par type de geometrie."""

    def test_point_3d(self) -> None:
        sommets: set[tuple[float, float, float]] = set()
        geom = {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        _extraire_sommets_geometrie(geom, sommets)
        assert sommets == {(1.0, 2.0, 3.0)}

    def test_point_2d_est_ignore(self) -> None:
        sommets: set[tuple[float, float, float]] = set()
        geom = {"type": "Point", "coordinates": [1.0, 2.0]}
        _extraire_sommets_geometrie(geom, sommets)
        assert len(sommets) == 0

    def test_linestring(self) -> None:
        sommets: set[tuple[float, float, float]] = set()
        geom = {
            "type": "LineString",
            "coordinates": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        }
        _extraire_sommets_geometrie(geom, sommets)
        assert sommets == {(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)}

    def test_polygon(self) -> None:
        sommets: set[tuple[float, float, float]] = set()
        geom = {
            "type": "Polygon",
            "coordinates": [[[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 0, 1]]],
        }
        _extraire_sommets_geometrie(geom, sommets)
        assert (0, 0, 1) in sommets
        assert (1, 0, 1) in sommets

    def test_multipoint(self) -> None:
        sommets: set[tuple[float, float, float]] = set()
        geom = {
            "type": "MultiPoint",
            "coordinates": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        }
        _extraire_sommets_geometrie(geom, sommets)
        assert len(sommets) == 2

    def test_multilinestring(self) -> None:
        sommets: set[tuple[float, float, float]] = set()
        geom = {
            "type": "MultiLineString",
            "coordinates": [
                [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
                [[7.0, 8.0, 9.0]],
            ],
        }
        _extraire_sommets_geometrie(geom, sommets)
        assert len(sommets) == 3

    def test_multipolygon(self) -> None:
        sommets: set[tuple[float, float, float]] = set()
        geom = {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 0, 1]]]],
        }
        _extraire_sommets_geometrie(geom, sommets)
        assert (0, 0, 1) in sommets

    def test_coordonnees_absentes(self) -> None:
        sommets: set[tuple[float, float, float]] = set()
        geom: dict[str, Any] = {"type": "Point", "coordinates": None}
        _extraire_sommets_geometrie(geom, sommets)
        assert len(sommets) == 0


class TestExtraireSommetsFeatures:
    """Tests de l'extraction des sommets a partir d'une liste de features."""

    def test_cable_linestring_extrait_sommets(self) -> None:
        cables = [_construire_cable("c1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])]
        sommets = extraire_sommets_features(cables)
        assert sommets == {(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)}

    def test_feature_point_extrait_sommet(self) -> None:
        features = [_construire_point_plor("p1", [1.0, 2.0, 3.0])]
        sommets = extraire_sommets_features(features)
        assert sommets == {(1.0, 2.0, 3.0)}

    def test_geometrie_absente_est_ignoree(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "c1"},
            "geometry": None,
        }
        sommets = extraire_sommets_features([feature])
        assert len(sommets) == 0

    def test_collection_vide(self) -> None:
        assert extraire_sommets_features([]) == set()


# --------------------------------------------------------------------------- #
# Tests de la detection des points PLOR hors cables
# --------------------------------------------------------------------------- #


class TestDetecterPointsHorsCables:
    """Tests de la logique de detection des ecarts PLOR/cables."""

    def test_point_sur_sommet_cable_est_conforme(self) -> None:
        sommets = {(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)}
        features = [_construire_point_plor("p1", [1.0, 2.0, 3.0])]
        anomalies = detecter_points_hors_cables(features, sommets, set())
        assert anomalies == []

    def test_point_hors_cable_est_detecte(self) -> None:
        sommets = {(1.0, 2.0, 3.0)}
        features = [_construire_point_plor("p1", [10.0, 20.0, 30.0])]
        anomalies = detecter_points_hors_cables(features, sommets, set())
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "p1"
        assert anomalies[0]["coordonnees"] == [10.0, 20.0, 30.0]

    def test_ecart_sur_z_uniquement_est_detecte(self) -> None:
        """Un point coincidant en X,Y mais pas en Z est non conforme."""
        sommets = {(1.0, 2.0, 3.0)}
        features = [_construire_point_plor("p1", [1.0, 2.0, 999.0])]
        anomalies = detecter_points_hors_cables(features, sommets, set())
        assert len(anomalies) == 1

    def test_ecart_sur_x_uniquement_est_detecte(self) -> None:
        sommets = {(1.0, 2.0, 3.0)}
        features = [_construire_point_plor("p1", [999.0, 2.0, 3.0])]
        anomalies = detecter_points_hors_cables(features, sommets, set())
        assert len(anomalies) == 1

    def test_point_2d_est_ignore(self) -> None:
        """Un point sans composante Z n'est pas analyse."""
        sommets = {(1.0, 2.0, 3.0)}
        features = [_construire_point_plor("p1", [1.0, 2.0])]
        anomalies = detecter_points_hors_cables(features, sommets, set())
        assert anomalies == []

    def test_geometrie_non_point_est_ignoree(self) -> None:
        sommets = {(1.0, 2.0, 3.0)}
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "l1"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
            },
        }
        anomalies = detecter_points_hors_cables([feature], sommets, set())
        assert anomalies == []

    def test_geometrie_absente_est_ignoree(self) -> None:
        sommets = {(1.0, 2.0, 3.0)}
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "p1"},
            "geometry": None,
        }
        anomalies = detecter_points_hors_cables([feature], sommets, set())
        assert anomalies == []

    def test_cables_vides_tout_est_en_ecart(self) -> None:
        """Si aucun sommet de cable ni RPD n'existe, tous les points sont en ecart."""
        features = [_construire_point_plor("p1", [1.0, 2.0, 3.0])]
        anomalies = detecter_points_hors_cables(features, set(), set())
        assert len(anomalies) == 1

    def test_melange_conformes_et_non_conformes(self) -> None:
        sommets = {(1.0, 2.0, 3.0)}
        features = [
            _construire_point_plor("ok", [1.0, 2.0, 3.0]),
            _construire_point_plor("ko", [9.0, 9.0, 9.0]),
        ]
        anomalies = detecter_points_hors_cables(features, sommets, set())
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "ko"

    def test_point_hors_cable_mais_sur_autre_rpd_est_exclu(self) -> None:
        """Un point absent des cables mais present sur un autre RPD est ignore."""
        sommets_cables = {(1.0, 2.0, 3.0)}
        sommets_autres = {(50.0, 60.0, 70.0)}
        features = [_construire_point_plor("p1", [50.0, 60.0, 70.0])]
        anomalies = detecter_points_hors_cables(
            features, sommets_cables, sommets_autres
        )
        assert anomalies == []

    def test_point_hors_cable_et_hors_autres_rpd_est_detecte(self) -> None:
        """Un point absent de tout fichier RPD est signale en anomalie."""
        sommets_cables = {(1.0, 2.0, 3.0)}
        sommets_autres = {(50.0, 60.0, 70.0)}
        features = [_construire_point_plor("p1", [99.0, 99.0, 99.0])]
        anomalies = detecter_points_hors_cables(
            features, sommets_cables, sommets_autres
        )
        assert len(anomalies) == 1


# --------------------------------------------------------------------------- #
# Tests du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestGeojsonSortie:
    """Tests de la serialisation des anomalies en FeatureCollection."""

    def test_structure_geojson_conforme(self) -> None:
        anomalies = [
            {"id_entite": "p1", "coordonnees": [1.0, 2.0, 3.0]},
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1
        feature = geojson["features"][0]
        assert feature["geometry"] == {
            "type": "Point",
            "coordinates": [1.0, 2.0, 3.0],
        }
        assert feature["properties"]["id_entite"] == "p1"
        assert feature["properties"]["type_anomalie"] == "point_hors_cable"
        assert feature["properties"]["priorite"] == PRIORITE_ANOMALIE

    def test_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_priorite_est_bloquant(self) -> None:
        anomalies = [{"id_entite": "p1", "coordonnees": [0.0, 0.0, 0.0]}]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["features"][0]["properties"]["priorite"] == "bloquant"

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
    """Prepare un repertoire avec des fichiers PLOR, cables et autre RPD."""
    coordonnees_cable = [
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
        [7.0, 8.0, 9.0],
    ]
    cables_collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": [_construire_cable("cable-1", coordonnees_cable)],
    }
    # plor-ok : sur cable, plor-rpd : sur autre RPD, plor-ko : nulle part
    crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
    plor_collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "crs": crs,
        "features": [
            _construire_point_plor("plor-ok", [1.0, 2.0, 3.0]),
            _construire_point_plor("plor-rpd", [50.0, 60.0, 70.0]),
            _construire_point_plor("plor-ko", [99.0, 99.0, 99.0]),
        ],
    }
    # Fichier RPD supplémentaire contenant un point a (50, 60, 70)
    autre_rpd: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": [_construire_point_plor("support-1", [50.0, 60.0, 70.0])],
    }

    (tmp_path / FICHIER_CABLES).write_text(
        json.dumps(cables_collection), encoding="utf-8"
    )
    (tmp_path / FICHIER_PLOR).write_text(json.dumps(plor_collection), encoding="utf-8")
    (tmp_path / "RPD_Support_Reco.geojson").write_text(
        json.dumps(autre_rpd), encoding="utf-8"
    )
    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_execution_ecrit_fichier_sortie(self, repertoire_test: str) -> None:
        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        # plor-ok conforme (cable), plor-rpd exclu (autre RPD), plor-ko en ecart
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_points_plor"] == 3
        assert resultat["fichiers_rpd_analyses"] >= 1
        chemin_sortie = os.path.join(repertoire_test, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)
        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 1
        assert contenu["features"][0]["properties"]["id_entite"] == "plor-ko"

    def test_crs_propage_dans_sortie(self, repertoire_test: str) -> None:
        """Le CRS du fichier PLOR source est propage dans le GeoJSON de sortie."""
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
        cables_collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
        }
        (tmp_path / FICHIER_CABLES).write_text(
            json.dumps(cables_collection), encoding="utf-8"
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert FICHIER_PLOR in resultat["erreur"]

    def test_fichier_cables_manquant_retourne_erreur(self, tmp_path: Any) -> None:
        plor_collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
        }
        (tmp_path / FICHIER_PLOR).write_text(
            json.dumps(plor_collection), encoding="utf-8"
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert FICHIER_CABLES in resultat["erreur"]

    def test_aucune_anomalie_si_tous_conformes(self, tmp_path: Any) -> None:
        coords = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
        cables: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [_construire_cable("c1", coords)],
        }
        plor: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [
                _construire_point_plor("p1", [1.0, 2.0, 3.0]),
                _construire_point_plor("p2", [4.0, 5.0, 6.0]),
            ],
        }
        (tmp_path / FICHIER_CABLES).write_text(json.dumps(cables), encoding="utf-8")
        (tmp_path / FICHIER_PLOR).write_text(json.dumps(plor), encoding="utf-8")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
