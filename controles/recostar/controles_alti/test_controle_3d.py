"""
Tests unitaires du controle de conformite 3D (controle_3d).

Couvre les cas nominaux et les cas limites :
- detection des entites 2D pour chaque type de geometrie
- exclusion des entites 3D conformes
- gestion des geometries nulles ou vides
- exclusion des fichiers d'ecarts de l'analyse
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_3d import (
    EXTENSION_GEOJSON,
    FICHIER_SORTIE,
    PREFIXE_ECARTS,
    PRIORITE_ANOMALIE,
    _entite_est_2d,
    _extraire_points_geometrie,
    _obtenir_id_feature,
    construire_geojson_ecarts,
    detecter_entites_2d,
    executer_controle_cli,
    lister_fichiers_geojson,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #


def _construire_feature(
    identifiant: str,
    type_geom: str,
    coordonnees: Any,
) -> dict[str, Any]:
    """Construit une feature GeoJSON minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": type_geom, "coordinates": coordonnees},
    }


def _ecrire_collection(chemin: str, features: list[dict[str, Any]]) -> None:
    """Ecrit un FeatureCollection GeoJSON sur disque pour les tests."""
    collection = {"type": "FeatureCollection", "features": features}
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Tests de l'extraction des points
# --------------------------------------------------------------------------- #


class TestExtrairePointsGeometrie:
    """Tests de l'extraction des points selon le type de geometrie."""

    def test_point_3d(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        assert _extraire_points_geometrie(geom) == [[1.0, 2.0, 3.0]]

    def test_point_2d(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0]}
        assert _extraire_points_geometrie(geom) == [[1.0, 2.0]]

    def test_linestring(self) -> None:
        geom = {"type": "LineString", "coordinates": [[0, 0, 1], [1, 1, 2]]}
        assert len(_extraire_points_geometrie(geom)) == 2

    def test_polygon(self) -> None:
        anneau = [[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 0, 1]]
        geom = {"type": "Polygon", "coordinates": [anneau]}
        assert len(_extraire_points_geometrie(geom)) == 4

    def test_multipoint(self) -> None:
        geom = {"type": "MultiPoint", "coordinates": [[0, 0, 1], [1, 1]]}
        points = _extraire_points_geometrie(geom)
        assert len(points) == 2

    def test_multilinestring(self) -> None:
        geom = {
            "type": "MultiLineString",
            "coordinates": [[[0, 0, 1], [1, 1, 2]], [[2, 2], [3, 3]]],
        }
        assert len(_extraire_points_geometrie(geom)) == 4

    def test_multipolygon(self) -> None:
        anneau = [[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 0, 1]]
        geom = {"type": "MultiPolygon", "coordinates": [[anneau]]}
        assert len(_extraire_points_geometrie(geom)) == 4

    def test_geometrie_sans_coordonnees(self) -> None:
        geom = {"type": "Point"}
        assert _extraire_points_geometrie(geom) == []

    def test_type_inconnu(self) -> None:
        geom = {"type": "GeometryCollection", "coordinates": []}
        assert _extraire_points_geometrie(geom) == []


# --------------------------------------------------------------------------- #
# Tests de la detection 2D
# --------------------------------------------------------------------------- #


class TestEntiteEst2D:
    """Tests de la detection d'entites sans composante Z."""

    def test_point_3d_est_conforme(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        assert _entite_est_2d(geom) is False

    def test_point_2d_est_non_conforme(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0]}
        assert _entite_est_2d(geom) is True

    def test_linestring_mixte_est_non_conforme(self) -> None:
        # Un seul point 2D suffit a rendre l'entite non conforme
        geom = {
            "type": "LineString",
            "coordinates": [[0, 0, 1], [1, 1], [2, 2, 3]],
        }
        assert _entite_est_2d(geom) is True

    def test_linestring_entierement_3d_est_conforme(self) -> None:
        geom = {
            "type": "LineString",
            "coordinates": [[0, 0, 1], [1, 1, 2], [2, 2, 3]],
        }
        assert _entite_est_2d(geom) is False

    def test_geometrie_nulle_retourne_false(self) -> None:
        geom: dict[str, Any] = {"type": "Point"}
        assert _entite_est_2d(geom) is False

    def test_polygon_2d(self) -> None:
        anneau = [[0, 0], [1, 0], [1, 1], [0, 0]]
        geom = {"type": "Polygon", "coordinates": [anneau]}
        assert _entite_est_2d(geom) is True

    def test_multipolygon_3d_conforme(self) -> None:
        anneau = [[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 0, 1]]
        geom = {"type": "MultiPolygon", "coordinates": [[anneau]]}
        assert _entite_est_2d(geom) is False


# --------------------------------------------------------------------------- #
# Tests de la detection sur une collection de features
# --------------------------------------------------------------------------- #


class TestDetecterEntites2D:
    """Tests de la detection sur une collection de features."""

    def test_entite_2d_detectee(self) -> None:
        features = [_construire_feature("e1", "Point", [1.0, 2.0])]
        anomalies = detecter_entites_2d(features, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "e1"
        assert anomalies[0]["fichier_source"] == "test.geojson"

    def test_entite_3d_non_detectee(self) -> None:
        features = [_construire_feature("e1", "Point", [1.0, 2.0, 3.0])]
        anomalies = detecter_entites_2d(features, "test.geojson")
        assert anomalies == []

    def test_geometrie_nulle_ignoree(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "e1"},
            "geometry": None,
        }
        anomalies = detecter_entites_2d([feature], "test.geojson")
        assert anomalies == []

    def test_melange_2d_3d(self) -> None:
        features = [
            _construire_feature("ok", "Point", [1.0, 2.0, 3.0]),
            _construire_feature("ko", "Point", [4.0, 5.0]),
        ]
        anomalies = detecter_entites_2d(features, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "ko"


# --------------------------------------------------------------------------- #
# Tests du listing des fichiers
# --------------------------------------------------------------------------- #


class TestListerFichiersGeojson:
    """Tests du listing et filtrage des fichiers GeoJSON."""

    def test_exclut_fichiers_ecarts(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "ecarts_3d.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert "donnees.geojson" in fichiers
        assert "ecarts_3d.geojson" not in fichiers

    def test_exclut_non_geojson(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "readme.txt").write_text("texte", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert len(fichiers) == 1

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        assert lister_fichiers_geojson(str(tmp_path)) == []


# --------------------------------------------------------------------------- #
# Tests de l'identifiant
# --------------------------------------------------------------------------- #


class TestObtenirIdFeature:
    """Tests de l'extraction de l'identifiant metier."""

    def test_id_chaine(self) -> None:
        feature: dict[str, Any] = {"properties": {"id": "abc"}}
        assert _obtenir_id_feature(feature) == "abc"

    def test_id_entier(self) -> None:
        feature: dict[str, Any] = {"properties": {"id": 42}}
        assert _obtenir_id_feature(feature) == "42"

    def test_id_absent(self) -> None:
        feature: dict[str, Any] = {"properties": {}}
        assert _obtenir_id_feature(feature) is None

    def test_properties_absentes(self) -> None:
        feature: dict[str, Any] = {}
        assert _obtenir_id_feature(feature) is None


# --------------------------------------------------------------------------- #
# Tests du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestGeojsonSortie:
    """Tests de la serialisation des anomalies en FeatureCollection."""

    def test_structure_geojson_conforme(self) -> None:
        anomalies = [
            {
                "fichier_source": "test.geojson",
                "id_entite": "e1",
                "type_geometrie": "Point",
                "geometrie": {"type": "Point", "coordinates": [1.0, 2.0]},
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1

        feature = geojson["features"][0]
        assert feature["properties"]["fichier_source"] == "test.geojson"
        assert feature["properties"]["id_entite"] == "e1"
        assert feature["properties"]["type_geometrie"] == "Point"
        assert feature["properties"]["type_anomalie"] == "absence_coordonnee_z"
        assert feature["properties"]["priorite"] == "information"

    def test_feature_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson


# --------------------------------------------------------------------------- #
# Tests CLI bout en bout
# --------------------------------------------------------------------------- #


@pytest.fixture
def repertoire_test(tmp_path: Any) -> str:
    """Prepare un repertoire contenant des GeoJSON 3D et 2D."""
    # Fichier avec entites 3D conformes
    features_3d = [
        _construire_feature("pt-3d", "Point", [1.0, 2.0, 3.0]),
        _construire_feature("ls-3d", "LineString", [[0, 0, 1], [1, 1, 2]]),
    ]
    _ecrire_collection(str(tmp_path / "conforme.geojson"), features_3d)

    # Fichier avec entites 2D non conformes
    features_2d = [
        _construire_feature("pt-2d", "Point", [1.0, 2.0]),
        _construire_feature("ls-2d", "LineString", [[0, 0], [1, 1]]),
    ]
    _ecrire_collection(str(tmp_path / "non_conforme.geojson"), features_2d)

    # Fichier d'ecarts existant (doit etre ignore)
    _ecrire_collection(str(tmp_path / "ecarts_ancien.geojson"), [])

    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_execution_ecrit_fichier_sortie(self, repertoire_test: str) -> None:
        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 2
        assert resultat["fichiers_analyses"] == 2

        chemin_sortie = os.path.join(repertoire_test, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)

        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 2

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

    def test_aucun_geojson_retourne_erreur(self, tmp_path: Any) -> None:
        (tmp_path / "readme.txt").write_text("texte", encoding="utf-8")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False

    def test_aucune_anomalie_produit_collection_vide(self, tmp_path: Any) -> None:
        features_3d = [_construire_feature("ok", "Point", [1.0, 2.0, 3.0])]
        _ecrire_collection(str(tmp_path / "data.geojson"), features_3d)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
