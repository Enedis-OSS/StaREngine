"""
Tests unitaires du controle des projections (controle_proj).

Couvre les cas nominaux et les cas limites :
- extraction du code EPSG depuis les formats URN OGC et court
- gestion du CRS absent, malformate ou non interpretable
- verification d'appartenance aux projections autorisees
- controle de projection par fichier (conforme / non conforme)
- listing et filtrage des fichiers GeoJSON
- construction du GeoJSON d'ecarts
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_proj import (
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    PROJECTIONS_AUTORISEES,
    _extraire_nom_crs_brut,
    _obtenir_id_feature,
    construire_geojson_ecarts,
    controler_projection_fichier,
    est_projection_autorisee,
    executer_controle_cli,
    extraire_code_epsg,
    lister_fichiers_geojson,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de collections GeoJSON pour les tests
# --------------------------------------------------------------------------- #


def _construire_collection(
    code_epsg: int | None,
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construit une collection GeoJSON avec un CRS EPSG donne."""
    collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": features or [],
    }
    if code_epsg is not None:
        collection["crs"] = {
            "type": "name",
            "properties": {
                "name": f"urn:ogc:def:crs:EPSG::{code_epsg}",
            },
        }
    return collection


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


def _ecrire_collection_fichier(
    chemin: str,
    code_epsg: int | None,
    features: list[dict[str, Any]] | None = None,
) -> None:
    """Ecrit une collection GeoJSON sur disque pour les tests."""
    collection = _construire_collection(code_epsg, features)
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Tests de l'extraction du code EPSG
# --------------------------------------------------------------------------- #


class TestExtraireCodeEpsg:
    """Tests de l'extraction du code EPSG depuis le CRS."""

    def test_urn_ogc_standard(self) -> None:
        collection = _construire_collection(2154)
        assert extraire_code_epsg(collection) == 2154

    def test_format_epsg_court(self) -> None:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "EPSG:3946"},
            },
            "features": [],
        }
        assert extraire_code_epsg(collection) == 3946

    def test_crs_absent(self) -> None:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
        }
        assert extraire_code_epsg(collection) is None

    def test_crs_sans_properties(self) -> None:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "crs": {"type": "name"},
            "features": [],
        }
        assert extraire_code_epsg(collection) is None

    def test_crs_properties_sans_name(self) -> None:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {}},
            "features": [],
        }
        assert extraire_code_epsg(collection) is None

    def test_crs_name_format_inconnu(self) -> None:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "WGS84"},
            },
            "features": [],
        }
        assert extraire_code_epsg(collection) is None

    def test_crs_name_non_chaine(self) -> None:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": 2154},
            },
            "features": [],
        }
        assert extraire_code_epsg(collection) is None

    def test_crs_non_dict(self) -> None:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "crs": "EPSG:2154",
            "features": [],
        }
        assert extraire_code_epsg(collection) is None


# --------------------------------------------------------------------------- #
# Tests de l'extraction du CRS brut
# --------------------------------------------------------------------------- #


class TestExtraireNomCrsBrut:
    """Tests de l'extraction de la valeur brute du CRS."""

    def test_crs_present(self) -> None:
        collection = _construire_collection(2154)
        assert _extraire_nom_crs_brut(collection) == "urn:ogc:def:crs:EPSG::2154"

    def test_crs_absent(self) -> None:
        collection: dict[str, Any] = {"type": "FeatureCollection", "features": []}
        assert _extraire_nom_crs_brut(collection) == "absent"

    def test_crs_sans_name(self) -> None:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {}},
            "features": [],
        }
        assert _extraire_nom_crs_brut(collection) == "absent"


# --------------------------------------------------------------------------- #
# Tests de la verification d'appartenance aux projections
# --------------------------------------------------------------------------- #


class TestEstProjectionAutorisee:
    """Tests de la verification d'appartenance aux projections autorisees."""

    @pytest.mark.parametrize("code_epsg", list(PROJECTIONS_AUTORISEES.keys()))
    def test_codes_autorises(self, code_epsg: int) -> None:
        assert est_projection_autorisee(code_epsg) is True

    def test_code_non_autorise(self) -> None:
        assert est_projection_autorisee(4326) is False

    def test_code_inexistant(self) -> None:
        assert est_projection_autorisee(0) is False


# --------------------------------------------------------------------------- #
# Tests de l'identifiant metier
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

    def test_properties_none(self) -> None:
        feature: dict[str, Any] = {"properties": None}
        assert _obtenir_id_feature(feature) is None


# --------------------------------------------------------------------------- #
# Tests du controle de projection par fichier
# --------------------------------------------------------------------------- #


class TestControlerProjectionFichier:
    """Tests du controle de projection sur un fichier."""

    def test_projection_conforme(self) -> None:
        features = [_construire_feature("e1", "Point", [1.0, 2.0, 3.0])]
        collection = _construire_collection(2154, features)
        resultat = controler_projection_fichier(collection, "test.geojson")
        assert resultat["conforme"] is True
        assert resultat["code_epsg"] == 2154
        assert resultat["alias"] == "RGF93LAMB93"
        assert resultat["entites_ecart"] == []

    def test_projection_cc46_conforme(self) -> None:
        features = [_construire_feature("e1", "Point", [1.0, 2.0])]
        collection = _construire_collection(3946, features)
        resultat = controler_projection_fichier(collection, "test.geojson")
        assert resultat["conforme"] is True
        assert resultat["alias"] == "CC46"

    def test_projection_non_conforme(self) -> None:
        features = [_construire_feature("e1", "Point", [1.0, 2.0, 3.0])]
        collection = _construire_collection(4326, features)
        resultat = controler_projection_fichier(collection, "test.geojson")
        assert resultat["conforme"] is False
        assert resultat["code_epsg"] == 4326
        assert resultat["alias"] is None
        assert len(resultat["entites_ecart"]) == 1

    def test_crs_absent(self) -> None:
        features = [_construire_feature("e1", "Point", [1.0, 2.0])]
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": features,
        }
        resultat = controler_projection_fichier(collection, "test.geojson")
        assert resultat["conforme"] is False
        assert resultat["code_epsg"] is None
        assert "absent" in resultat["message"].lower()

    def test_fichier_vide_non_conforme(self) -> None:
        collection = _construire_collection(9999)
        resultat = controler_projection_fichier(collection, "test.geojson")
        assert resultat["conforme"] is False
        assert resultat["entites_ecart"] == []

    def test_entites_ecart_contiennent_metadata(self) -> None:
        features = [
            _construire_feature("e1", "Point", [1.0, 2.0]),
            _construire_feature("e2", "LineString", [[0, 0], [1, 1]]),
        ]
        collection = _construire_collection(4326, features)
        resultat = controler_projection_fichier(collection, "data.geojson")
        ecarts = resultat["entites_ecart"]
        assert len(ecarts) == 2
        assert ecarts[0]["fichier_source"] == "data.geojson"
        assert ecarts[0]["id_entite"] == "e1"
        assert "4326" in ecarts[0]["crs_detecte"]

    def test_geometrie_preservee_dans_ecarts(self) -> None:
        geom = {"type": "Point", "coordinates": [10.0, 20.0, 30.0]}
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "g1"},
            "geometry": geom,
        }
        collection = _construire_collection(4326, [feature])
        resultat = controler_projection_fichier(collection, "test.geojson")
        assert resultat["entites_ecart"][0]["geometrie"] == geom


# --------------------------------------------------------------------------- #
# Tests du listing des fichiers
# --------------------------------------------------------------------------- #


class TestListerFichiersGeojson:
    """Tests du listing et filtrage des fichiers GeoJSON."""

    def test_exclut_fichiers_ecarts(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "ecarts_proj.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert "donnees.geojson" in fichiers
        assert "ecarts_proj.geojson" not in fichiers

    def test_exclut_fichiers_ecart_singulier(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "ecart_proj_ensemble.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert "donnees.geojson" in fichiers
        assert "ecart_proj_ensemble.geojson" not in fichiers

    def test_exclut_non_geojson(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "readme.txt").write_text("texte", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert len(fichiers) == 1

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        assert lister_fichiers_geojson(str(tmp_path)) == []

    def test_tri_alphabetique(self, tmp_path: Any) -> None:
        (tmp_path / "b_data.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "a_data.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert fichiers == ["a_data.geojson", "b_data.geojson"]


# --------------------------------------------------------------------------- #
# Tests du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestGeojsonSortie:
    """Tests de la serialisation des ecarts en FeatureCollection."""

    def test_structure_geojson_conforme(self) -> None:
        anomalies = [
            {
                "fichier_source": "test.geojson",
                "id_entite": "e1",
                "crs_detecte": "urn:ogc:def:crs:EPSG::4326",
                "geometrie": {"type": "Point", "coordinates": [1.0, 2.0]},
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1

        feature = geojson["features"][0]
        props = feature["properties"]
        assert props["fichier_source"] == "test.geojson"
        assert props["id_entite"] == "e1"
        assert props["crs_detecte"] == "urn:ogc:def:crs:EPSG::4326"
        assert props["type_anomalie"] == "projection_non_conforme"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert feature["geometry"] == {"type": "Point", "coordinates": [1.0, 2.0]}

    def test_collection_vide(self) -> None:
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
# Tests CLI bout en bout avec tmp_path
# --------------------------------------------------------------------------- #


@pytest.fixture
def repertoire_test(tmp_path: Any) -> str:
    """Prepare un repertoire contenant des GeoJSON avec CRS varies."""
    # Fichier avec projection conforme
    features_ok = [_construire_feature("pt-ok", "Point", [1.0, 2.0, 5.0])]
    _ecrire_collection_fichier(str(tmp_path / "conforme.geojson"), 2154, features_ok)

    # Fichier avec projection non conforme
    features_ko = [
        _construire_feature("pt-ko", "Point", [3.0, 4.0, 10.0]),
        _construire_feature("ls-ko", "LineString", [[0, 0, 1], [1, 1, 2]]),
    ]
    _ecrire_collection_fichier(
        str(tmp_path / "non_conforme.geojson"), 4326, features_ko
    )

    # Fichier d'ecarts existant (doit etre ignore par le listing)
    _ecrire_collection_fichier(str(tmp_path / "ecarts_ancien.geojson"), 2154)

    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_execution_ecrit_fichier_sortie(self, repertoire_test: str) -> None:
        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        assert resultat["fichiers_conformes"] == 1
        assert resultat["fichiers_non_conformes"] == 1
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

    def test_tous_conformes_produit_collection_vide(self, tmp_path: Any) -> None:
        features = [_construire_feature("ok", "Point", [1.0, 2.0, 10.0])]
        _ecrire_collection_fichier(str(tmp_path / "data.geojson"), 2154, features)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["fichiers_conformes"] == 1
        assert resultat["fichiers_non_conformes"] == 0

    def test_crs_absent_detecte(self, tmp_path: Any) -> None:
        features = [_construire_feature("e1", "Point", [1.0, 2.0])]
        _ecrire_collection_fichier(str(tmp_path / "sans_crs.geojson"), None, features)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichiers_non_conformes"] == 1
        assert resultat["nombre_anomalies"] == 1

    def test_detail_fichiers_present(self, repertoire_test: str) -> None:
        resultat = executer_controle_cli(repertoire_test)
        assert "detail" in resultat
        assert len(resultat["detail"]) == 2
        for detail in resultat["detail"]:
            assert "fichier" in detail
            assert "conforme" in detail
            assert "message" in detail

    def test_priorite_bloquant_dans_ecarts(self, repertoire_test: str) -> None:
        executer_controle_cli(repertoire_test)
        chemin_sortie = os.path.join(repertoire_test, FICHIER_SORTIE)
        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        for feature in contenu["features"]:
            assert feature["properties"]["priorite"] == "bloquant"
