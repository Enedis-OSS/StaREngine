"""
Tests unitaires du controle des coordonnees Z nulles (controle_z_null).

Couvre les cas nominaux et les cas limites :
- detection des sommets a Z nul pour chaque type de geometrie
- non-detection des sommets 3D conformes (Z != 0.0)
- non-detection des sommets 2D (pas de composante Z)
- gestion des geometries nulles ou vides
- extraction des points avec indices
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_z_null import (
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    Z_NULL,
    _extraire_points_indexes,
    _obtenir_id_feature,
    construire_geojson_ecarts,
    detecter_z_null_collection,
    detecter_z_null_feature,
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
# Tests de l'extraction des points avec indices
# --------------------------------------------------------------------------- #


class TestExtrairePointsIndexes:
    """Tests de l'extraction indexee des points selon le type de geometrie."""

    def test_point(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0, 0.0]}
        resultat = _extraire_points_indexes(geom)
        assert len(resultat) == 1
        assert resultat[0] == (0, [1.0, 2.0, 0.0])

    def test_linestring(self) -> None:
        geom = {"type": "LineString", "coordinates": [[0, 0, 1], [1, 1, 0.0]]}
        resultat = _extraire_points_indexes(geom)
        assert len(resultat) == 2
        assert resultat[0][0] == 0
        assert resultat[1][0] == 1

    def test_polygon(self) -> None:
        anneau = [[0, 0, 1], [1, 0, 0.0], [1, 1, 1], [0, 0, 1]]
        geom = {"type": "Polygon", "coordinates": [anneau]}
        resultat = _extraire_points_indexes(geom)
        assert len(resultat) == 4
        assert resultat[1][0] == 1

    def test_multipolygon(self) -> None:
        anneau = [[0, 0, 1], [1, 0, 0.0], [1, 1, 1], [0, 0, 1]]
        geom = {"type": "MultiPolygon", "coordinates": [[anneau]]}
        resultat = _extraire_points_indexes(geom)
        assert len(resultat) == 4

    def test_geometrie_sans_coordonnees(self) -> None:
        geom: dict[str, Any] = {"type": "Point"}
        assert _extraire_points_indexes(geom) == []

    def test_type_inconnu(self) -> None:
        geom = {"type": "GeometryCollection", "coordinates": []}
        assert _extraire_points_indexes(geom) == []


# --------------------------------------------------------------------------- #
# Tests de la detection Z nul par feature
# --------------------------------------------------------------------------- #


class TestDetecterZNullFeature:
    """Tests de la detection de Z=0.0 sur une feature individuelle."""

    def test_point_z_nul_detecte(self) -> None:
        feature = _construire_feature("p1", "Point", [1.0, 2.0, 0.0])
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "p1"
        assert anomalies[0]["indice_sommet"] == 0
        assert anomalies[0]["coordonnees"] == [1.0, 2.0, 0.0]

    def test_point_z_non_nul_ignore(self) -> None:
        feature = _construire_feature("p1", "Point", [1.0, 2.0, 10.5])
        assert detecter_z_null_feature(feature, "test.geojson") == []

    def test_point_2d_ignore(self) -> None:
        # Un sommet 2D n'a pas de Z a verifier
        feature = _construire_feature("p1", "Point", [1.0, 2.0])
        assert detecter_z_null_feature(feature, "test.geojson") == []

    def test_linestring_avec_z_nul_partiel(self) -> None:
        coords = [[0, 0, 10.0], [1, 1, 0.0], [2, 2, 20.0]]
        feature = _construire_feature("ls1", "LineString", coords)
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["indice_sommet"] == 1

    def test_linestring_avec_tous_z_nuls(self) -> None:
        coords = [[0, 0, 0.0], [1, 1, 0.0], [2, 2, 0.0]]
        feature = _construire_feature("ls2", "LineString", coords)
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        assert len(anomalies) == 3

    def test_linestring_sans_z_nul(self) -> None:
        coords = [[0, 0, 10.0], [1, 1, 20.0]]
        feature = _construire_feature("ls3", "LineString", coords)
        assert detecter_z_null_feature(feature, "test.geojson") == []

    def test_geometrie_nulle_ignoree(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "e1"},
            "geometry": None,
        }
        assert detecter_z_null_feature(feature, "test.geojson") == []

    def test_polygon_z_nul(self) -> None:
        anneau = [[0, 0, 0.0], [1, 0, 10.0], [1, 1, 10.0], [0, 0, 0.0]]
        feature = _construire_feature("pg1", "Polygon", [anneau])
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        # Indices 0 et 3 sont a Z=0.0
        assert len(anomalies) == 2

    def test_multipolygon_z_nul(self) -> None:
        anneau = [[0, 0, 0.0], [1, 0, 5.0], [1, 1, 5.0], [0, 0, 0.0]]
        feature = _construire_feature("mp1", "MultiPolygon", [[anneau]])
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        assert len(anomalies) == 2

    def test_fichier_source_propage(self) -> None:
        feature = _construire_feature("p1", "Point", [1.0, 2.0, 0.0])
        anomalies = detecter_z_null_feature(feature, "RPD_Cable.geojson")
        assert anomalies[0]["fichier_source"] == "RPD_Cable.geojson"


# --------------------------------------------------------------------------- #
# Tests de la detection sur une collection
# --------------------------------------------------------------------------- #


class TestDetecterZNullCollection:
    """Tests de la detection sur une collection de features."""

    def test_melange_conforme_et_non_conforme(self) -> None:
        features = [
            _construire_feature("ok", "Point", [1.0, 2.0, 10.0]),
            _construire_feature("ko", "Point", [3.0, 4.0, 0.0]),
        ]
        anomalies = detecter_z_null_collection(features, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "ko"

    def test_collection_vide(self) -> None:
        assert detecter_z_null_collection([], "test.geojson") == []


# --------------------------------------------------------------------------- #
# Tests du listing des fichiers
# --------------------------------------------------------------------------- #


class TestListerFichiersGeojson:
    """Tests du listing et filtrage des fichiers GeoJSON."""

    def test_exclut_fichiers_ecarts(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "ecarts_z_null.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert "donnees.geojson" in fichiers
        assert "ecarts_z_null.geojson" not in fichiers

    def test_exclut_non_geojson(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "readme.txt").write_text("texte", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert len(fichiers) == 1


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
                "indice_sommet": 0,
                "coordonnees": [1.0, 2.0, 0.0],
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1

        feature = geojson["features"][0]
        props = feature["properties"]
        assert props["fichier_source"] == "test.geojson"
        assert props["id_entite"] == "e1"
        assert props["type_geometrie"] == "Point"
        assert props["indice_sommet"] == 0
        assert props["z_detecte"] == pytest.approx(0.0)
        assert props["type_anomalie"] == "z_null"
        assert props["priorite"] == "information"
        assert feature["geometry"] == {"type": "Point", "coordinates": [1.0, 2.0, 0.0]}

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
    """Prepare un repertoire contenant des GeoJSON avec sommets Z nuls."""
    # Fichier avec sommets Z nuls
    features_z_null = [
        _construire_feature("pt-z0", "Point", [1.0, 2.0, 0.0]),
        _construire_feature(
            "ls-z0", "LineString", [[0, 0, 0.0], [1, 1, 10.0], [2, 2, 0.0]]
        ),
    ]
    _ecrire_collection(str(tmp_path / "avec_z_null.geojson"), features_z_null)

    # Fichier entierement conforme
    features_ok = [
        _construire_feature("pt-ok", "Point", [1.0, 2.0, 5.0]),
        _construire_feature("ls-ok", "LineString", [[0, 0, 10.0], [1, 1, 20.0]]),
    ]
    _ecrire_collection(str(tmp_path / "conforme.geojson"), features_ok)

    # Fichier d'ecarts existant (doit etre ignore)
    _ecrire_collection(str(tmp_path / "ecarts_ancien.geojson"), [])

    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_execution_ecrit_fichier_sortie(self, repertoire_test: str) -> None:
        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        # 1 point Z=0 + 2 sommets Z=0 dans la ligne = 3 anomalies
        assert resultat["nombre_anomalies"] == 3
        assert resultat["fichiers_analyses"] == 2

        chemin_sortie = os.path.join(repertoire_test, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)

        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 3

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
        features_ok = [_construire_feature("ok", "Point", [1.0, 2.0, 10.0])]
        _ecrire_collection(str(tmp_path / "data.geojson"), features_ok)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
