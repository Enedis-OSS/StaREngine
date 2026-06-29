"""
Tests unitaires du controle des doublons spatiaux (controle_e204).

Couvre les cas nominaux et cas limites :
- detection de version depuis les proprietes GeoJSON
- resolution de version (auto / explicite / repli par defaut)
- detection des doublons v1.1 (coordonnees seules)
- detection des doublons v1.0 (coordonnees + TypeLeve)
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from controle_e204 import (
    CHAMP_TYPE_LEVE,
    FICHIER_SORTIE,
    FICHIER_SOURCE,
    JETON_AUTO,
    PRIORITE_ANOMALIE,
    VERSION_DEFAUT,
    _cle_doublon_v1_0,
    _cle_doublon_v1_1,
    construire_geojson_ecarts,
    detecter_doublons_spatiaux,
    detecter_version_depuis_features,
    executer_controle_cli,
    resoudre_version,
)
from utils_tests import (
    construire_feature,
    construire_feature_avec_proprietes,
    ecrire_collection,
)

# ---------------------------------------------------------------------------
# Helpers specifiques a ce module
# ---------------------------------------------------------------------------

_COORDS_A = [1.0, 2.0, 3.0]
_COORDS_B = [4.0, 5.0, 6.0]
_TYPE_ALTITUDE = "AltitudeGeneratrice"
_TYPE_CHARGE = "ChargeGeneratrice"


def _feature_v1_1(identifiant: str, coordonnees: list[float]) -> dict[str, Any]:
    """Feature v1.1 : Point sans champ TypeLeve."""
    return construire_feature(identifiant, "Point", coordonnees)


def _feature_v1_0(
    identifiant: str,
    coordonnees: list[float],
    type_leve: str,
) -> dict[str, Any]:
    """Feature v1.0 : Point avec champ TypeLeve."""
    return construire_feature_avec_proprietes(identifiant, "Point", coordonnees, {CHAMP_TYPE_LEVE: type_leve})


def _ecrire_collection_v1_1(chemin: str, features: list[dict[str, Any]]) -> None:
    """Ecrit un fichier GeoJSON v1.1 (sans TypeLeve)."""
    ecrire_collection(chemin, features)


def _ecrire_collection_v1_0(chemin: str, features: list[dict[str, Any]]) -> None:
    """Ecrit un fichier GeoJSON v1.0 (avec TypeLeve dans les features)."""
    ecrire_collection(chemin, features)


# ---------------------------------------------------------------------------
# Tests de la detection de version
# ---------------------------------------------------------------------------


class TestDetecterVersionDepuisFeatures:
    """Tests de la deduction de la version a partir des proprietes GeoJSON."""

    def test_feature_avec_type_leve_retourne_v1_0(self) -> None:
        features = [_feature_v1_0("p1", _COORDS_A, _TYPE_ALTITUDE)]
        assert detecter_version_depuis_features(features) == "1.0"

    def test_features_sans_type_leve_retourne_none(self) -> None:
        features = [_feature_v1_1("p1", _COORDS_A)]
        assert detecter_version_depuis_features(features) is None

    def test_collection_vide_retourne_none(self) -> None:
        assert detecter_version_depuis_features([]) is None

    def test_au_moins_une_feature_avec_type_leve_suffit(self) -> None:
        features = [
            _feature_v1_1("p1", _COORDS_A),
            _feature_v1_0("p2", _COORDS_B, _TYPE_ALTITUDE),
        ]
        assert detecter_version_depuis_features(features) == "1.0"

    def test_type_leve_none_non_detecte(self) -> None:
        # TypeLeve absent des proprietes (pas TypeLeve: None)
        features = [construire_feature("p1", "Point", _COORDS_A)]
        assert detecter_version_depuis_features(features) is None


class TestResoudreVersion:
    """Tests de la resolution de la version effective."""

    def test_mode_auto_v1_0_detecte(self) -> None:
        features = [_feature_v1_0("p1", _COORDS_A, _TYPE_ALTITUDE)]
        assert resoudre_version(JETON_AUTO, features) == "1.0"

    def test_mode_auto_repli_v1_1_par_defaut(self) -> None:
        features = [_feature_v1_1("p1", _COORDS_A)]
        assert resoudre_version(JETON_AUTO, features) == VERSION_DEFAUT

    def test_mode_explicite_v1_0_ignore_detection(self) -> None:
        # Meme si les features ressemblent a v1.1, la version explicite prime
        features = [_feature_v1_1("p1", _COORDS_A)]
        assert resoudre_version("1.0", features) == "1.0"

    def test_mode_explicite_v1_1(self) -> None:
        features = [_feature_v1_0("p1", _COORDS_A, _TYPE_ALTITUDE)]
        assert resoudre_version("1.1", features) == "1.1"

    def test_mode_auto_collection_vide_repli_sur_defaut(self) -> None:
        assert resoudre_version(JETON_AUTO, []) == VERSION_DEFAUT


# ---------------------------------------------------------------------------
# Tests des extracteurs de cles
# ---------------------------------------------------------------------------


class TestExtracteursCles:
    """Tests des fonctions de construction de cles de doublon."""

    def test_cle_v1_1_retourne_tuple_coordonnees(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        cle = _cle_doublon_v1_1(geom, {})
        assert cle == (1.0, 2.0, 3.0)

    def test_cle_v1_1_coordonnees_absentes_retourne_none(self) -> None:
        geom: dict[str, Any] = {"type": "Point"}
        assert _cle_doublon_v1_1(geom, {}) is None

    def test_cle_v1_0_retourne_tuple_coords_et_type_leve(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        props = {CHAMP_TYPE_LEVE: _TYPE_ALTITUDE}
        cle = _cle_doublon_v1_0(geom, props)
        assert cle == ((1.0, 2.0, 3.0), _TYPE_ALTITUDE)

    def test_cle_v1_0_type_leve_absent_retourne_none_dans_tuple(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        cle = _cle_doublon_v1_0(geom, {})
        assert cle == ((1.0, 2.0, 3.0), None)

    def test_cle_v1_0_coordonnees_absentes_retourne_none(self) -> None:
        geom: dict[str, Any] = {"type": "Point"}
        assert _cle_doublon_v1_0(geom, {}) is None


# ---------------------------------------------------------------------------
# Tests de la detection des doublons v1.1
# ---------------------------------------------------------------------------


class TestDetecterDoublonsV1_1:
    """Tests de la detection des doublons en mode version 1.1."""

    def test_deux_points_memes_coords_produisent_anomalie(self) -> None:
        features = [
            _feature_v1_1("p1", _COORDS_A),
            _feature_v1_1("p2", _COORDS_A),
        ]
        anomalies = detecter_doublons_spatiaux(features, "1.1")
        assert len(anomalies) == 1
        assert anomalies[0]["nb_points"] == 2
        assert set(anomalies[0]["ids_entites"]) == {"p1", "p2"}
        assert anomalies[0]["coordonnees"] == _COORDS_A

    def test_deux_points_coords_differentes_pas_anomalie(self) -> None:
        features = [
            _feature_v1_1("p1", _COORDS_A),
            _feature_v1_1("p2", _COORDS_B),
        ]
        assert detecter_doublons_spatiaux(features, "1.1") == []

    def test_trois_points_memes_coords_un_groupe(self) -> None:
        features = [
            _feature_v1_1("p1", _COORDS_A),
            _feature_v1_1("p2", _COORDS_A),
            _feature_v1_1("p3", _COORDS_A),
        ]
        anomalies = detecter_doublons_spatiaux(features, "1.1")
        assert len(anomalies) == 1
        assert anomalies[0]["nb_points"] == 3

    def test_deux_groupes_distincts(self) -> None:
        features = [
            _feature_v1_1("p1", _COORDS_A),
            _feature_v1_1("p2", _COORDS_A),
            _feature_v1_1("p3", _COORDS_B),
            _feature_v1_1("p4", _COORDS_B),
        ]
        anomalies = detecter_doublons_spatiaux(features, "1.1")
        assert len(anomalies) == 2

    def test_collection_vide_retourne_liste_vide(self) -> None:
        assert detecter_doublons_spatiaux([], "1.1") == []

    def test_feature_sans_geometrie_ignoree(self) -> None:
        feature_sans_geom: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "p1"},
            "geometry": None,
        }
        features = [feature_sans_geom, _feature_v1_1("p2", _COORDS_A)]
        assert detecter_doublons_spatiaux(features, "1.1") == []

    def test_geometrie_non_point_ignoree(self) -> None:
        ligne = construire_feature("l1", "LineString", [_COORDS_A, _COORDS_B])
        features = [ligne, _feature_v1_1("p1", _COORDS_A)]
        assert detecter_doublons_spatiaux(features, "1.1") == []

    def test_coordonnees_2d_traitees_comme_cle(self) -> None:
        coords_2d = [1.0, 2.0]
        features = [
            construire_feature("p1", "Point", coords_2d),
            construire_feature("p2", "Point", coords_2d),
        ]
        anomalies = detecter_doublons_spatiaux(features, "1.1")
        assert len(anomalies) == 1


# ---------------------------------------------------------------------------
# Tests de la detection des doublons v1.0
# ---------------------------------------------------------------------------


class TestDetecterDoublonsV1_0:
    """Tests de la detection des doublons en mode version 1.0."""

    def test_memes_coords_meme_type_leve_anomalie(self) -> None:
        features = [
            _feature_v1_0("p1", _COORDS_A, _TYPE_ALTITUDE),
            _feature_v1_0("p2", _COORDS_A, _TYPE_ALTITUDE),
        ]
        anomalies = detecter_doublons_spatiaux(features, "1.0")
        assert len(anomalies) == 1
        assert anomalies[0]["type_leve"] == _TYPE_ALTITUDE

    def test_memes_coords_types_leve_differents_pas_anomalie(self) -> None:
        features = [
            _feature_v1_0("p1", _COORDS_A, _TYPE_ALTITUDE),
            _feature_v1_0("p2", _COORDS_A, _TYPE_CHARGE),
        ]
        assert detecter_doublons_spatiaux(features, "1.0") == []

    def test_deux_groupes_type_leve_distincts(self) -> None:
        features = [
            _feature_v1_0("p1", _COORDS_A, _TYPE_ALTITUDE),
            _feature_v1_0("p2", _COORDS_A, _TYPE_ALTITUDE),
            _feature_v1_0("p3", _COORDS_B, _TYPE_CHARGE),
            _feature_v1_0("p4", _COORDS_B, _TYPE_CHARGE),
        ]
        anomalies = detecter_doublons_spatiaux(features, "1.0")
        assert len(anomalies) == 2

    def test_coords_identiques_type_leve_none_anomalie(self) -> None:
        # Deux features sans TypeLeve : meme cle (coords, None) → doublon
        features = [
            construire_feature("p1", "Point", _COORDS_A),
            construire_feature("p2", "Point", _COORDS_A),
        ]
        anomalies = detecter_doublons_spatiaux(features, "1.0")
        assert len(anomalies) == 1
        assert anomalies[0]["type_leve"] is None

    def test_anomalie_contient_coordonnees(self) -> None:
        features = [
            _feature_v1_0("p1", _COORDS_A, _TYPE_ALTITUDE),
            _feature_v1_0("p2", _COORDS_A, _TYPE_ALTITUDE),
        ]
        anomalies = detecter_doublons_spatiaux(features, "1.0")
        assert anomalies[0]["coordonnees"] == _COORDS_A


# ---------------------------------------------------------------------------
# Tests du GeoJSON de sortie
# ---------------------------------------------------------------------------


class TestConstruireGeojsonEcarts:
    """Tests de la construction du GeoJSON de sortie."""

    def test_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([], "1.1")
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_structure_feature_v1_1(self) -> None:
        anomalies = [
            {
                "coordonnees": _COORDS_A,
                "ids_entites": ["p1", "p2"],
                "nb_points": 2,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies, "1.1")
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1

        feature = geojson["features"][0]
        assert feature["geometry"] == {"type": "Point", "coordinates": _COORDS_A}

        props = feature["properties"]
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["type_anomalie"] == "doublons_spatiaux"
        assert props["version"] == "1.1"
        assert props["nb_points"] == 2
        assert "p1" in props["ids_entites"]
        assert "p2" in props["ids_entites"]
        assert CHAMP_TYPE_LEVE not in props

    def test_structure_feature_v1_0_inclut_type_leve(self) -> None:
        anomalies = [
            {
                "coordonnees": _COORDS_A,
                "ids_entites": ["p1", "p2"],
                "nb_points": 2,
                "type_leve": _TYPE_ALTITUDE,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies, "1.0")
        props = geojson["features"][0]["properties"]
        assert props[CHAMP_TYPE_LEVE] == _TYPE_ALTITUDE
        assert props["version"] == "1.0"

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], "1.1", crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        geojson = construire_geojson_ecarts([], "1.1")
        assert "crs" not in geojson

    def test_ids_entites_serialises_en_chaine(self) -> None:
        anomalies = [
            {
                "coordonnees": _COORDS_A,
                "ids_entites": ["abc", "def"],
                "nb_points": 2,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies, "1.1")
        ids_str = geojson["features"][0]["properties"]["ids_entites"]
        assert isinstance(ids_str, str)
        assert "abc" in ids_str
        assert "def" in ids_str


# ---------------------------------------------------------------------------
# Tests CLI bout en bout
# ---------------------------------------------------------------------------


@pytest.fixture
def repertoire_v1_1_sans_doublon(tmp_path: Any) -> str:
    """Repertoire contenant un fichier v1.1 sans doublons."""
    features = [
        _feature_v1_1("p1", [1.0, 2.0, 3.0]),
        _feature_v1_1("p2", [4.0, 5.0, 6.0]),
    ]
    _ecrire_collection_v1_1(str(tmp_path / FICHIER_SOURCE), features)
    return str(tmp_path)


@pytest.fixture
def repertoire_v1_1_avec_doublon(tmp_path: Any) -> str:
    """Repertoire contenant un fichier v1.1 avec un doublon."""
    features = [
        _feature_v1_1("p1", _COORDS_A),
        _feature_v1_1("p2", _COORDS_A),
        _feature_v1_1("p3", _COORDS_B),
    ]
    _ecrire_collection_v1_1(str(tmp_path / FICHIER_SOURCE), features)
    return str(tmp_path)


@pytest.fixture
def repertoire_v1_0_avec_doublon(tmp_path: Any) -> str:
    """Repertoire contenant un fichier v1.0 avec un doublon (meme TypeLeve)."""
    features = [
        _feature_v1_0("p1", _COORDS_A, _TYPE_ALTITUDE),
        _feature_v1_0("p2", _COORDS_A, _TYPE_ALTITUDE),  # doublon
        _feature_v1_0("p3", _COORDS_A, _TYPE_CHARGE),  # pas doublon (TypeLeve different)
    ]
    _ecrire_collection_v1_0(str(tmp_path / FICHIER_SOURCE), features)
    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_fichier_source_absent_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_v1_1_sans_doublon(self, repertoire_v1_1_sans_doublon: str) -> None:
        resultat = executer_controle_cli(repertoire_v1_1_sans_doublon)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_points_en_doublon"] == 0
        assert resultat["version_detectee"] == "1.1"

    def test_v1_1_avec_doublon_detecte(self, repertoire_v1_1_avec_doublon: str) -> None:
        resultat = executer_controle_cli(repertoire_v1_1_avec_doublon)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_points_en_doublon"] == 2
        assert resultat["version_detectee"] == "1.1"
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_v1_0_doublon_meme_type_leve(self, repertoire_v1_0_avec_doublon: str) -> None:
        resultat = executer_controle_cli(repertoire_v1_0_avec_doublon, version="1.0")
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1
        assert resultat["version_detectee"] == "1.0"

    def test_v1_0_auto_detects_version(self, repertoire_v1_0_avec_doublon: str) -> None:
        # La version 1.0 doit etre detectable automatiquement (TypeLeve present)
        resultat = executer_controle_cli(repertoire_v1_0_avec_doublon)
        assert resultat["version_detectee"] == "1.0"

    def test_v1_0_coords_identiques_type_leve_different_pas_doublon(self, tmp_path: Any) -> None:
        features = [
            _feature_v1_0("p1", _COORDS_A, _TYPE_ALTITUDE),
            _feature_v1_0("p2", _COORDS_A, _TYPE_CHARGE),
        ]
        _ecrire_collection_v1_0(str(tmp_path / FICHIER_SOURCE), features)
        resultat = executer_controle_cli(str(tmp_path), version="1.0")
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_ecrit_fichier_geojson_sortie(self, repertoire_v1_1_avec_doublon: str) -> None:
        executer_controle_cli(repertoire_v1_1_avec_doublon)
        chemin_sortie = os.path.join(repertoire_v1_1_avec_doublon, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)

        with open(chemin_sortie, encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 1

    def test_repertoire_sortie_distinct(self, repertoire_v1_1_avec_doublon: str, tmp_path: Any) -> None:
        dossier_sortie = str(tmp_path / "sortie")
        resultat = executer_controle_cli(repertoire_v1_1_avec_doublon, dossier_sortie)
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))

    def test_version_explicite_1_1_force_comportement_v1_1(self, repertoire_v1_0_avec_doublon: str) -> None:
        # En forcant v1.1 sur un fichier v1.0, tous les points aux memes coords
        # (quelque soit TypeLeve) sont des doublons : 3 features sur _COORDS_A
        resultat = executer_controle_cli(repertoire_v1_0_avec_doublon, version="1.1")
        assert resultat["succes"] is True
        # p1, p2, p3 sont tous sur _COORDS_A → un groupe de 3
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_points_en_doublon"] == 3
