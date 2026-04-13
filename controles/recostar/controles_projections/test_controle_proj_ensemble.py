"""
Tests unitaires du controle de coherence des projections (controle_proj_ensemble).

Couvre les cas nominaux et les cas limites :
- determination du CRS de reference par vote majoritaire
- detection des fichiers dont le CRS differe du CRS de reference
- gestion du CRS absent dans un ou plusieurs fichiers
- cas ou tous les fichiers sont coherents
- construction du GeoJSON d'ecarts
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_proj_ensemble import (
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    construire_geojson_ecarts,
    determiner_crs_reference,
    executer_controle_cli,
    formater_crs_reference,
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
# Tests de la determination du CRS de reference
# --------------------------------------------------------------------------- #


class TestDeterminerCrsReference:
    """Tests du vote majoritaire pour le CRS de reference."""

    def test_tous_identiques(self) -> None:
        codes = {"a.geojson": 2154, "b.geojson": 2154, "c.geojson": 2154}
        assert determiner_crs_reference(codes) == 2154

    def test_majorite_simple(self) -> None:
        codes = {"a.geojson": 2154, "b.geojson": 2154, "c.geojson": 3946}
        assert determiner_crs_reference(codes) == 2154

    def test_fichier_unique(self) -> None:
        codes = {"a.geojson": 3946}
        assert determiner_crs_reference(codes) == 3946

    def test_aucun_code_valide(self) -> None:
        codes: dict[str, int | None] = {
            "a.geojson": None,
            "b.geojson": None,
        }
        assert determiner_crs_reference(codes) is None

    def test_codes_none_exclus_du_vote(self) -> None:
        codes: dict[str, int | None] = {
            "a.geojson": 2154,
            "b.geojson": None,
            "c.geojson": 2154,
        }
        assert determiner_crs_reference(codes) == 2154

    def test_dictionnaire_vide(self) -> None:
        assert determiner_crs_reference({}) is None


# --------------------------------------------------------------------------- #
# Tests du formatage du CRS de reference
# --------------------------------------------------------------------------- #


class TestFormaterCrsReference:
    """Tests du formatage du code EPSG en chaine."""

    def test_code_valide(self) -> None:
        assert formater_crs_reference(2154) == "EPSG:2154"

    def test_code_none(self) -> None:
        assert formater_crs_reference(None) == "absent"


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
                "crs_detecte": "urn:ogc:def:crs:EPSG::3946",
                "crs_reference": "EPSG:2154",
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
        assert props["crs_detecte"] == "urn:ogc:def:crs:EPSG::3946"
        assert props["crs_reference"] == "EPSG:2154"
        assert props["type_anomalie"] == "projection_incoherente"
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
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def repertoire_coherent(tmp_path: Any) -> str:
    """Repertoire ou tous les fichiers partagent le meme CRS."""
    features_a = [_construire_feature("a1", "Point", [1.0, 2.0, 5.0])]
    features_b = [_construire_feature("b1", "Point", [3.0, 4.0, 10.0])]
    _ecrire_collection_fichier(str(tmp_path / "a.geojson"), 2154, features_a)
    _ecrire_collection_fichier(str(tmp_path / "b.geojson"), 2154, features_b)
    return str(tmp_path)


@pytest.fixture
def repertoire_incoherent(tmp_path: Any) -> str:
    """Repertoire avec un fichier ayant un CRS different de la majorite."""
    features_a = [_construire_feature("a1", "Point", [1.0, 2.0, 5.0])]
    features_b = [_construire_feature("b1", "Point", [3.0, 4.0, 10.0])]
    features_c = [
        _construire_feature("c1", "Point", [5.0, 6.0, 15.0]),
        _construire_feature("c2", "LineString", [[0, 0, 1], [1, 1, 2]]),
    ]
    _ecrire_collection_fichier(str(tmp_path / "a.geojson"), 2154, features_a)
    _ecrire_collection_fichier(str(tmp_path / "b.geojson"), 2154, features_b)
    _ecrire_collection_fichier(str(tmp_path / "c.geojson"), 3946, features_c)
    return str(tmp_path)


# --------------------------------------------------------------------------- #
# Tests CLI bout en bout
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_tous_coherents_zero_anomalie(self, repertoire_coherent: str) -> None:
        resultat = executer_controle_cli(repertoire_coherent)
        assert resultat["succes"] is True
        assert resultat["fichiers_conformes"] == 2
        assert resultat["fichiers_non_conformes"] == 0
        assert resultat["nombre_anomalies"] == 0
        assert resultat["crs_reference"] == "EPSG:2154"

    def test_fichier_incoherent_detecte(self, repertoire_incoherent: str) -> None:
        resultat = executer_controle_cli(repertoire_incoherent)
        assert resultat["succes"] is True
        assert resultat["fichiers_conformes"] == 2
        assert resultat["fichiers_non_conformes"] == 1
        # c.geojson a 2 entites
        assert resultat["nombre_anomalies"] == 2
        assert resultat["crs_reference"] == "EPSG:2154"

    def test_fichier_sortie_ecrit(self, repertoire_incoherent: str) -> None:
        executer_controle_cli(repertoire_incoherent)
        chemin_sortie = os.path.join(repertoire_incoherent, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)

        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 2

    def test_priorite_bloquant_dans_ecarts(self, repertoire_incoherent: str) -> None:
        executer_controle_cli(repertoire_incoherent)
        chemin_sortie = os.path.join(repertoire_incoherent, FICHIER_SORTIE)
        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        for feature in contenu["features"]:
            assert feature["properties"]["priorite"] == "bloquant"

    def test_crs_reference_dans_ecarts(self, repertoire_incoherent: str) -> None:
        executer_controle_cli(repertoire_incoherent)
        chemin_sortie = os.path.join(repertoire_incoherent, FICHIER_SORTIE)
        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        for feature in contenu["features"]:
            assert feature["properties"]["crs_reference"] == "EPSG:2154"

    def test_repertoire_sortie_distinct(
        self, repertoire_incoherent: str, tmp_path: Any
    ) -> None:
        dossier_sortie = tmp_path / "sortie"
        resultat = executer_controle_cli(repertoire_incoherent, str(dossier_sortie))
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

    def test_crs_absent_dans_un_fichier(self, tmp_path: Any) -> None:
        features_ok = [_construire_feature("ok", "Point", [1.0, 2.0])]
        features_ko = [_construire_feature("ko", "Point", [3.0, 4.0])]
        _ecrire_collection_fichier(str(tmp_path / "a.geojson"), 2154, features_ok)
        _ecrire_collection_fichier(str(tmp_path / "b.geojson"), None, features_ko)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichiers_non_conformes"] == 1
        assert resultat["nombre_anomalies"] == 1
        assert resultat["crs_reference"] == "EPSG:2154"

    def test_tous_crs_absents(self, tmp_path: Any) -> None:
        features_a = [_construire_feature("a1", "Point", [1.0, 2.0])]
        features_b = [_construire_feature("b1", "Point", [3.0, 4.0])]
        _ecrire_collection_fichier(str(tmp_path / "a.geojson"), None, features_a)
        _ecrire_collection_fichier(str(tmp_path / "b.geojson"), None, features_b)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        # Tous coherents (tous absents) : reference = None
        assert resultat["crs_reference"] == "absent"
        assert resultat["fichiers_conformes"] == 2
        assert resultat["nombre_anomalies"] == 0

    def test_fichier_unique_toujours_conforme(self, tmp_path: Any) -> None:
        features = [_construire_feature("e1", "Point", [1.0, 2.0])]
        _ecrire_collection_fichier(str(tmp_path / "seul.geojson"), 3946, features)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichiers_conformes"] == 1
        assert resultat["fichiers_non_conformes"] == 0

    def test_detail_fichiers_present(self, repertoire_incoherent: str) -> None:
        resultat = executer_controle_cli(repertoire_incoherent)
        assert "detail" in resultat
        assert len(resultat["detail"]) == 3
        for detail in resultat["detail"]:
            assert "fichier" in detail
            assert "conforme" in detail
            assert "code_epsg" in detail
