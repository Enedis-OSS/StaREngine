"""
Tests unitaires du controle de coherence des coordonnees (controle_proj_coordonnees).

Couvre les cas nominaux et les cas limites :
- calcul d'emprise projetee via pyproj (Lambert 93, CC, UTM, outre-mer)
- validation de coordonnees (finies, hors emprise, invalides)
- extraction indexee des sommets pour tous les types de geometrie
- detection des anomalies par feature et par collection
- gestion du CRS absent ou non interpretable
- construction du GeoJSON d'ecarts
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

import pytest

from controle_proj_coordonnees import (
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    TYPE_COORDONNEE_INVALIDE,
    TYPE_CRS_INDETERMINE,
    TYPE_HORS_EMPRISE,
    _construire_detail,
    _construire_geometrie_anomalie,
    construire_geojson_ecarts,
    controler_fichier,
    creer_anomalie_crs_indetermine,
    detecter_anomalies_collection,
    detecter_anomalies_feature,
    est_valeur_finie,
    executer_controle_cli,
    extraire_points_indexes,
    obtenir_emprise_projetee,
    verifier_point,
)

# --------------------------------------------------------------------------- #
# Helpers
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


def _creer_feature_point(
    x: float,
    y: float,
    z: float | None = None,
    identifiant: str | None = None,
) -> dict[str, Any]:
    """Construit une feature Point pour les tests."""
    coords: list[float] = [x, y] if z is None else [x, y, z]
    proprietes: dict[str, Any] = {}
    if identifiant is not None:
        proprietes["id"] = identifiant
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "Point", "coordinates": coords},
    }


def _ecrire_geojson_test(
    repertoire: str,
    nom: str,
    code_epsg: int | None,
    features: list[dict[str, Any]],
) -> None:
    """Ecrit un fichier GeoJSON de test dans le repertoire."""
    collection = _construire_collection(code_epsg, features)
    chemin = os.path.join(repertoire, nom)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def emprise_lambert93() -> tuple[float, float, float, float]:
    """Emprise projetee pour EPSG:2154 (Lambert 93)."""
    emprise = obtenir_emprise_projetee(2154)
    assert emprise is not None
    return emprise


@pytest.fixture
def emprise_simple() -> tuple[float, float, float, float]:
    """Emprise synthetique simple pour tests unitaires."""
    return (0.0, 0.0, 100.0, 100.0)


# --------------------------------------------------------------------------- #
# Tests obtenir_emprise_projetee
# --------------------------------------------------------------------------- #


class TestObtenirEmpriseProjetee:
    """Tests du calcul d'emprise projetee via pyproj."""

    def test_lambert93(self) -> None:
        """EPSG:2154 couvre la France metropolitaine."""
        emprise = obtenir_emprise_projetee(2154)
        assert emprise is not None
        x_min, y_min, x_max, y_max = emprise
        assert x_min < 200_000
        assert x_max > 1_000_000
        assert y_min < 6_100_000
        assert y_max > 7_000_000

    def test_cc46(self) -> None:
        """EPSG:3946 (CC46) a une emprise bien definie."""
        emprise = obtenir_emprise_projetee(3946)
        assert emprise is not None
        x_min, y_min, x_max, y_max = emprise
        assert x_min < x_max
        assert y_min < y_max

    def test_lambert93_v2b(self) -> None:
        """EPSG:9794 (RGF93LAMB93 V2b) est similaire a EPSG:2154."""
        emprise = obtenir_emprise_projetee(9794)
        assert emprise is not None

    @pytest.mark.parametrize("code_epsg", [3942, 3946, 3950])
    def test_coniques_conformes(self, code_epsg: int) -> None:
        """Les CC42-CC50 ont des emprises valides."""
        emprise = obtenir_emprise_projetee(code_epsg)
        assert emprise is not None

    @pytest.mark.parametrize("code_epsg", [9842, 9846, 9850])
    def test_coniques_conformes_v2b(self, code_epsg: int) -> None:
        """Les CC V2b ont des emprises valides."""
        emprise = obtenir_emprise_projetee(code_epsg)
        assert emprise is not None

    @pytest.mark.parametrize("code_epsg", [5490, 2972, 2975, 4471, 4467])
    def test_outre_mer(self, code_epsg: int) -> None:
        """Les CRS outre-mer ont des emprises valides."""
        emprise = obtenir_emprise_projetee(code_epsg)
        assert emprise is not None

    def test_code_inconnu(self) -> None:
        """Un code EPSG inconnu retourne None."""
        emprise = obtenir_emprise_projetee(99999)
        assert emprise is None

    def test_cache_coherent(self) -> None:
        """Le cache retourne le meme resultat pour un meme code."""
        r1 = obtenir_emprise_projetee(2154)
        r2 = obtenir_emprise_projetee(2154)
        assert r1 == r2

    def test_emprise_contient_coordonnees_reelles(self) -> None:
        """Les coordonnees reelles Lambert 93 sont dans l'emprise."""
        emprise = obtenir_emprise_projetee(2154)
        assert emprise is not None
        x_min, y_min, x_max, y_max = emprise
        # Coordonnees typiques de la region de test
        assert x_min < 850144.07 < x_max
        assert y_min < 6799950.49 < y_max


# --------------------------------------------------------------------------- #
# Tests est_valeur_finie
# --------------------------------------------------------------------------- #


class TestEstValeurFinie:
    """Tests de la verification de valeurs finies."""

    @pytest.mark.parametrize("valeur", [0.0, 1.5, -100.0, 850000.0, 0, 42])
    def test_valeurs_finies(self, valeur: float | int) -> None:
        assert est_valeur_finie(valeur) is True

    @pytest.mark.parametrize("valeur", [float("nan"), float("inf"), float("-inf")])
    def test_valeurs_non_finies(self, valeur: float) -> None:
        assert est_valeur_finie(valeur) is False

    @pytest.mark.parametrize("valeur", [None, "abc", [], {}])
    def test_valeurs_non_numeriques(self, valeur: object) -> None:
        assert est_valeur_finie(valeur) is False


# --------------------------------------------------------------------------- #
# Tests verifier_point
# --------------------------------------------------------------------------- #


class TestVerifierPoint:
    """Tests de la verification d'un point par rapport a l'emprise."""

    def test_point_dans_emprise(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert verifier_point([50.0, 50.0], emprise_simple) is None

    def test_point_3d_dans_emprise(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        """La composante Z n'est pas verifiee."""
        assert verifier_point([50.0, 50.0, 999999.0], emprise_simple) is None

    def test_point_sur_limite_basse(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert verifier_point([0.0, 0.0], emprise_simple) is None

    def test_point_sur_limite_haute(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert verifier_point([100.0, 100.0], emprise_simple) is None

    def test_hors_emprise_x_positif(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert verifier_point([200.0, 50.0], emprise_simple) == TYPE_HORS_EMPRISE

    def test_hors_emprise_x_negatif(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert verifier_point([-10.0, 50.0], emprise_simple) == TYPE_HORS_EMPRISE

    def test_hors_emprise_y_positif(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert verifier_point([50.0, 200.0], emprise_simple) == TYPE_HORS_EMPRISE

    def test_hors_emprise_y_negatif(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert verifier_point([50.0, -10.0], emprise_simple) == TYPE_HORS_EMPRISE

    def test_coordonnee_nan(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert (
            verifier_point([float("nan"), 50.0], emprise_simple)
            == TYPE_COORDONNEE_INVALIDE
        )

    def test_coordonnee_inf(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert (
            verifier_point([float("inf"), 50.0], emprise_simple)
            == TYPE_COORDONNEE_INVALIDE
        )

    def test_coordonnees_insuffisantes(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert verifier_point([50.0], emprise_simple) == TYPE_COORDONNEE_INVALIDE

    def test_coordonnees_vides(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        assert verifier_point([], emprise_simple) == TYPE_COORDONNEE_INVALIDE

    def test_point_reel_lambert93(
        self, emprise_lambert93: tuple[float, float, float, float]
    ) -> None:
        """Coordonnees reelles Lambert 93 conformes."""
        assert verifier_point([850144.07, 6799950.49, 312.2], emprise_lambert93) is None

    def test_coordonnees_geographiques_dans_lambert93(
        self, emprise_lambert93: tuple[float, float, float, float]
    ) -> None:
        """Coordonnees geographiques dans un CRS projete -> hors emprise."""
        assert verifier_point([3.5, 43.2], emprise_lambert93) == TYPE_HORS_EMPRISE


# --------------------------------------------------------------------------- #
# Tests extraire_points_indexes
# --------------------------------------------------------------------------- #


class TestExtrairePointsIndexes:
    """Tests de l'extraction indexee des sommets selon le type de geometrie."""

    def test_point(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0]}
        result = extraire_points_indexes(geom)
        assert len(result) == 1
        assert result[0] == (0, [1.0, 2.0])

    def test_point_3d(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        result = extraire_points_indexes(geom)
        assert len(result) == 1
        assert result[0][1] == [1.0, 2.0, 3.0]

    def test_linestring(self) -> None:
        geom = {"type": "LineString", "coordinates": [[1, 2], [3, 4], [5, 6]]}
        result = extraire_points_indexes(geom)
        assert len(result) == 3
        assert result[0] == (0, [1, 2])
        assert result[2] == (2, [5, 6])

    def test_polygon(self) -> None:
        geom = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        }
        result = extraire_points_indexes(geom)
        assert len(result) == 4

    def test_multipoint(self) -> None:
        geom = {"type": "MultiPoint", "coordinates": [[1, 2], [3, 4]]}
        result = extraire_points_indexes(geom)
        assert len(result) == 2

    def test_multilinestring(self) -> None:
        geom = {
            "type": "MultiLineString",
            "coordinates": [[[1, 2], [3, 4]], [[5, 6]]],
        }
        result = extraire_points_indexes(geom)
        assert len(result) == 3
        # Indices sequentiels continus
        assert result[0][0] == 0
        assert result[1][0] == 1
        assert result[2][0] == 2

    def test_multipolygon(self) -> None:
        geom = {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
        }
        result = extraire_points_indexes(geom)
        assert len(result) == 4

    def test_sans_coordonnees(self) -> None:
        geom = {"type": "Point"}
        assert extraire_points_indexes(geom) == []

    def test_type_inconnu(self) -> None:
        geom = {"type": "GeometryCollection", "coordinates": []}
        assert extraire_points_indexes(geom) == []

    def test_coordonnees_none(self) -> None:
        geom = {"type": "Point", "coordinates": None}
        assert extraire_points_indexes(geom) == []


# --------------------------------------------------------------------------- #
# Tests detecter_anomalies_feature
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesFeature:
    """Tests de la detection d'anomalies par feature."""

    def test_feature_conforme(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        feature = _creer_feature_point(50.0, 50.0, identifiant="ok")
        anomalies, nb = detecter_anomalies_feature(
            feature, emprise_simple, "test.geojson"
        )
        assert anomalies == []
        assert nb == 1

    def test_feature_hors_emprise(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        feature = _creer_feature_point(200.0, 200.0, identifiant="ko")
        anomalies, nb = detecter_anomalies_feature(
            feature, emprise_simple, "test.geojson"
        )
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_HORS_EMPRISE
        assert anomalies[0]["fichier_source"] == "test.geojson"
        assert anomalies[0]["id_entite"] == "ko"
        assert nb == 1

    def test_feature_sans_geometrie(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {},
            "geometry": None,
        }
        anomalies, nb = detecter_anomalies_feature(
            feature, emprise_simple, "test.geojson"
        )
        assert anomalies == []
        assert nb == 0

    def test_linestring_mixte(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        """LineString avec un sommet conforme et un hors emprise."""
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "mix"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[50, 50, 10], [200, 200, 10], [75, 75, 10]],
            },
        }
        anomalies, nb = detecter_anomalies_feature(
            feature, emprise_simple, "test.geojson"
        )
        assert len(anomalies) == 1
        assert anomalies[0]["indice_sommet"] == 1
        assert nb == 3

    def test_feature_coordonnees_nan(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "nan"},
            "geometry": {
                "type": "Point",
                "coordinates": [float("nan"), 50.0],
            },
        }
        anomalies, _ = detecter_anomalies_feature(
            feature, emprise_simple, "test.geojson"
        )
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_COORDONNEE_INVALIDE

    def test_structure_anomalie(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        """Verifie que l'anomalie contient toutes les metadonnees attendues."""
        feature = _creer_feature_point(200.0, 200.0, z=5.0, identifiant="meta")
        anomalies, _ = detecter_anomalies_feature(
            feature, emprise_simple, "source.geojson"
        )
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["fichier_source"] == "source.geojson"
        assert a["id_entite"] == "meta"
        assert a["type_geometrie"] == "Point"
        assert a["indice_sommet"] == 0
        assert a["coordonnees"] == [200.0, 200.0, 5.0]
        assert a["type_anomalie"] == TYPE_HORS_EMPRISE


# --------------------------------------------------------------------------- #
# Tests detecter_anomalies_collection
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesCollection:
    """Tests de la detection d'anomalies par collection."""

    def test_collection_conforme(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        features = [
            _creer_feature_point(50, 50),
            _creer_feature_point(10, 10),
        ]
        anomalies, nb = detecter_anomalies_collection(
            features, emprise_simple, "f.geojson"
        )
        assert anomalies == []
        assert nb == 2

    def test_collection_avec_anomalies(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        features = [
            _creer_feature_point(50, 50),
            _creer_feature_point(200, 200),
        ]
        anomalies, nb = detecter_anomalies_collection(
            features, emprise_simple, "f.geojson"
        )
        assert len(anomalies) == 1
        assert nb == 2

    def test_collection_vide(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        anomalies, nb = detecter_anomalies_collection([], emprise_simple, "f.geojson")
        assert anomalies == []
        assert nb == 0

    def test_collection_toutes_anomalies(
        self, emprise_simple: tuple[float, float, float, float]
    ) -> None:
        features = [
            _creer_feature_point(200, 200),
            _creer_feature_point(-10, -10),
        ]
        anomalies, nb = detecter_anomalies_collection(
            features, emprise_simple, "f.geojson"
        )
        assert len(anomalies) == 2
        assert nb == 2


# --------------------------------------------------------------------------- #
# Tests creer_anomalie_crs_indetermine
# --------------------------------------------------------------------------- #


class TestCreerAnomalieCrsIndetermine:
    """Tests de la creation d'anomalie pour CRS indetermine."""

    def test_structure(self) -> None:
        anomalie = creer_anomalie_crs_indetermine("test.geojson")
        assert anomalie["fichier_source"] == "test.geojson"
        assert anomalie["type_anomalie"] == TYPE_CRS_INDETERMINE
        assert anomalie["coordonnees"] is None
        assert anomalie["id_entite"] is None
        assert anomalie["type_geometrie"] is None
        assert anomalie["indice_sommet"] is None


# --------------------------------------------------------------------------- #
# Tests _construire_geometrie_anomalie
# --------------------------------------------------------------------------- #


class TestConstruireGeometrieAnomalie:
    """Tests de la construction de geometrie pour anomalie."""

    def test_avec_coordonnees(self) -> None:
        geom = _construire_geometrie_anomalie([1.0, 2.0, 3.0])
        assert geom == {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}

    def test_sans_coordonnees(self) -> None:
        assert _construire_geometrie_anomalie(None) is None


# --------------------------------------------------------------------------- #
# Tests construire_geojson_ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de la construction du GeoJSON d'ecarts."""

    def test_ecarts_vides(self) -> None:
        result = construire_geojson_ecarts([])
        assert result["type"] == "FeatureCollection"
        assert result["features"] == []

    def test_ecart_hors_emprise(self) -> None:
        anomalies = [
            {
                "fichier_source": "f.geojson",
                "id_entite": "1",
                "type_geometrie": "Point",
                "indice_sommet": 0,
                "coordonnees": [200.0, 200.0],
                "type_anomalie": TYPE_HORS_EMPRISE,
            }
        ]
        result = construire_geojson_ecarts(anomalies)
        assert len(result["features"]) == 1
        feat = result["features"][0]
        assert feat["type"] == "Feature"
        assert feat["properties"]["priorite"] == PRIORITE_ANOMALIE
        assert feat["properties"]["type_anomalie"] == TYPE_HORS_EMPRISE
        assert feat["geometry"]["type"] == "Point"
        assert feat["geometry"]["coordinates"] == [200.0, 200.0]

    def test_ecart_crs_indetermine(self) -> None:
        anomalies = [
            {
                "fichier_source": "f.geojson",
                "id_entite": None,
                "type_geometrie": None,
                "indice_sommet": None,
                "coordonnees": None,
                "type_anomalie": TYPE_CRS_INDETERMINE,
            }
        ]
        result = construire_geojson_ecarts(anomalies)
        assert len(result["features"]) == 1
        assert result["features"][0]["geometry"] is None

    def test_priorite_bloquant(self) -> None:
        anomalies = [
            {
                "fichier_source": "f.geojson",
                "id_entite": "1",
                "type_geometrie": "Point",
                "indice_sommet": 0,
                "coordonnees": [1.0, 2.0],
                "type_anomalie": TYPE_HORS_EMPRISE,
            }
        ]
        result = construire_geojson_ecarts(anomalies)
        assert result["features"][0]["properties"]["priorite"] == "bloquant"

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        result = construire_geojson_ecarts([], crs=crs)
        assert result["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        result = construire_geojson_ecarts([])
        assert "crs" not in result


# --------------------------------------------------------------------------- #
# Tests _construire_detail
# --------------------------------------------------------------------------- #


class TestConstruireDetail:
    """Tests de la construction du detail de controle."""

    def test_structure_conforme(self) -> None:
        detail = _construire_detail("f.geojson", 2154, 100, 0, "conforme")
        assert detail["fichier"] == "f.geojson"
        assert detail["code_epsg"] == 2154
        assert detail["nb_sommets"] == 100
        assert detail["nb_anomalies"] == 0
        assert detail["statut"] == "conforme"

    def test_structure_crs_indetermine(self) -> None:
        detail = _construire_detail("f.geojson", None, 0, 1, "crs_indetermine")
        assert detail["code_epsg"] is None


# --------------------------------------------------------------------------- #
# Tests controler_fichier
# --------------------------------------------------------------------------- #


class TestControlerFichier:
    """Tests du controle d'un fichier individuel."""

    def test_fichier_conforme_lambert93(self) -> None:
        collection = _construire_collection(
            2154,
            [
                _creer_feature_point(850000.0, 6800000.0, z=310.0, identifiant="1"),
            ],
        )
        anomalies, detail = controler_fichier(collection, "test.geojson")
        assert anomalies == []
        assert detail["statut"] == "conforme"
        assert detail["nb_sommets"] == 1
        assert detail["nb_anomalies"] == 0

    def test_fichier_hors_emprise(self) -> None:
        """Coordonnees geographiques dans CRS projete."""
        collection = _construire_collection(
            2154,
            [
                _creer_feature_point(3.5, 43.2, identifiant="geo"),
            ],
        )
        anomalies, detail = controler_fichier(collection, "test.geojson")
        assert len(anomalies) == 1
        assert detail["statut"] == "anomalies_detectees"

    def test_fichier_crs_absent(self) -> None:
        collection = _construire_collection(
            None,
            [
                _creer_feature_point(1.0, 2.0),
            ],
        )
        anomalies, detail = controler_fichier(collection, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_CRS_INDETERMINE
        assert detail["statut"] == "crs_indetermine"

    def test_fichier_vide(self) -> None:
        """Fichier avec CRS valide mais sans features."""
        collection = _construire_collection(2154, [])
        anomalies, detail = controler_fichier(collection, "test.geojson")
        assert anomalies == []
        assert detail["statut"] == "conforme"
        assert detail["nb_sommets"] == 0

    def test_fichier_features_mixtes(self) -> None:
        """Certaines features conformes, d'autres non."""
        collection = _construire_collection(
            2154,
            [
                _creer_feature_point(850000.0, 6800000.0, identifiant="ok"),
                _creer_feature_point(3.5, 43.2, identifiant="ko"),
            ],
        )
        anomalies, detail = controler_fichier(collection, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "ko"
        assert detail["nb_sommets"] == 2


# --------------------------------------------------------------------------- #
# Tests executer_controle_cli
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Tests d'integration de l'execution CLI."""

    def test_repertoire_introuvable(self) -> None:
        result = executer_controle_cli("/chemin/inexistant/xyz")
        assert result["succes"] is False
        assert "introuvable" in result["erreur"]

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        result = executer_controle_cli(str(tmp_path))
        assert result["succes"] is False

    def test_fichier_conforme_lambert93(self, tmp_path: Any) -> None:
        _ecrire_geojson_test(
            str(tmp_path),
            "test.geojson",
            2154,
            [
                _creer_feature_point(850000.0, 6800000.0, z=310.0, identifiant="1"),
            ],
        )
        result = executer_controle_cli(str(tmp_path))
        assert result["succes"] is True
        assert result["fichiers_conformes"] == 1
        assert result["nombre_anomalies"] == 0

    def test_fichier_hors_emprise(self, tmp_path: Any) -> None:
        """Coordonnees geographiques dans CRS Lambert 93."""
        _ecrire_geojson_test(
            str(tmp_path),
            "test.geojson",
            2154,
            [
                _creer_feature_point(3.5, 43.2, identifiant="geo"),
            ],
        )
        result = executer_controle_cli(str(tmp_path))
        assert result["succes"] is True
        assert result["nombre_anomalies"] == 1
        assert result["fichiers_non_conformes"] == 1

    def test_fichier_crs_absent(self, tmp_path: Any) -> None:
        _ecrire_geojson_test(
            str(tmp_path),
            "test.geojson",
            None,
            [
                _creer_feature_point(850000.0, 6800000.0),
            ],
        )
        result = executer_controle_cli(str(tmp_path))
        assert result["succes"] is True
        assert result["nombre_anomalies"] == 1
        assert result["detail"][0]["statut"] == "crs_indetermine"

    def test_sortie_personnalisee(self, tmp_path: Any) -> None:
        dossier_entree = tmp_path / "entree"
        dossier_sortie = tmp_path / "sortie"
        dossier_entree.mkdir()
        _ecrire_geojson_test(
            str(dossier_entree),
            "test.geojson",
            2154,
            [
                _creer_feature_point(850000.0, 6800000.0),
            ],
        )
        result = executer_controle_cli(str(dossier_entree), str(dossier_sortie))
        assert result["succes"] is True
        assert os.path.exists(os.path.join(str(dossier_sortie), FICHIER_SORTIE))

    def test_sortie_par_defaut(self, tmp_path: Any) -> None:
        """Sans repertoire de sortie, le fichier est cree dans l'entree."""
        _ecrire_geojson_test(
            str(tmp_path),
            "test.geojson",
            2154,
            [
                _creer_feature_point(850000.0, 6800000.0),
            ],
        )
        result = executer_controle_cli(str(tmp_path))
        chemin_sortie = os.path.join(str(tmp_path), FICHIER_SORTIE)
        assert result["sortie"] == chemin_sortie
        assert os.path.exists(chemin_sortie)

    def test_fichier_ecarts_genere_correct(self, tmp_path: Any) -> None:
        """Le GeoJSON d'ecarts contient les bonnes anomalies."""
        _ecrire_geojson_test(
            str(tmp_path),
            "test.geojson",
            2154,
            [
                _creer_feature_point(3.5, 43.2, identifiant="geo"),
            ],
        )
        executer_controle_cli(str(tmp_path))
        chemin_ecarts = os.path.join(str(tmp_path), FICHIER_SORTIE)
        with open(chemin_ecarts, "r", encoding="utf-8") as f:
            ecarts = json.load(f)
        assert ecarts["type"] == "FeatureCollection"
        assert len(ecarts["features"]) == 1
        feat = ecarts["features"][0]
        assert feat["properties"]["priorite"] == PRIORITE_ANOMALIE
        assert feat["properties"]["type_anomalie"] == TYPE_HORS_EMPRISE

    def test_exclusion_fichiers_ecarts(self, tmp_path: Any) -> None:
        """Les fichiers d'ecarts sont exclus lors de re-executions."""
        _ecrire_geojson_test(
            str(tmp_path),
            "test.geojson",
            2154,
            [
                _creer_feature_point(850000.0, 6800000.0),
            ],
        )
        executer_controle_cli(str(tmp_path))
        # Re-execution : le fichier ecarts_ est exclu
        result = executer_controle_cli(str(tmp_path))
        assert result["fichiers_analyses"] == 1

    def test_plusieurs_fichiers_mixtes(self, tmp_path: Any) -> None:
        """Un fichier conforme, un non conforme."""
        _ecrire_geojson_test(
            str(tmp_path),
            "conforme.geojson",
            2154,
            [
                _creer_feature_point(850000.0, 6800000.0, identifiant="ok"),
            ],
        )
        _ecrire_geojson_test(
            str(tmp_path),
            "non_conforme.geojson",
            2154,
            [
                _creer_feature_point(3.5, 43.2, identifiant="ko"),
            ],
        )
        result = executer_controle_cli(str(tmp_path))
        assert result["fichiers_analyses"] == 2
        assert result["fichiers_conformes"] == 1
        assert result["fichiers_non_conformes"] == 1
        assert result["nombre_anomalies"] == 1

    def test_linestring_avec_sommet_hors_emprise(self, tmp_path: Any) -> None:
        """Un seul sommet d'une LineString est hors emprise."""
        features = [
            {
                "type": "Feature",
                "properties": {"id": "ls"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [850000.0, 6800000.0, 310.0],
                        [3.5, 43.2, 310.0],
                        [850100.0, 6800100.0, 310.0],
                    ],
                },
            }
        ]
        _ecrire_geojson_test(str(tmp_path), "test.geojson", 2154, features)
        result = executer_controle_cli(str(tmp_path))
        assert result["nombre_anomalies"] == 1
        # Le detail doit montrer 3 sommets verifies
        assert result["detail"][0]["nb_sommets"] == 3

    def test_priorite_bloquant_dans_ecarts(self, tmp_path: Any) -> None:
        """Toutes les anomalies ont la priorite bloquant."""
        _ecrire_geojson_test(
            str(tmp_path),
            "test.geojson",
            2154,
            [
                _creer_feature_point(3.5, 43.2),
                _creer_feature_point(-999.0, -999.0),
            ],
        )
        executer_controle_cli(str(tmp_path))
        chemin_ecarts = os.path.join(str(tmp_path), FICHIER_SORTIE)
        with open(chemin_ecarts, "r", encoding="utf-8") as f:
            ecarts = json.load(f)
        for feat in ecarts["features"]:
            assert feat["properties"]["priorite"] == "bloquant"

    def test_cc46_conforme(self, tmp_path: Any) -> None:
        """Coordonnees CC46 valides."""
        _ecrire_geojson_test(
            str(tmp_path),
            "test.geojson",
            3946,
            [
                _creer_feature_point(1700000.0, 5200000.0, identifiant="cc46"),
            ],
        )
        result = executer_controle_cli(str(tmp_path))
        assert result["nombre_anomalies"] == 0

    def test_cc46_hors_emprise(self, tmp_path: Any) -> None:
        """Coordonnees Lambert 93 dans un CRS CC46."""
        _ecrire_geojson_test(
            str(tmp_path),
            "test.geojson",
            3946,
            [
                _creer_feature_point(850000.0, 6800000.0, identifiant="l93_in_cc46"),
            ],
        )
        result = executer_controle_cli(str(tmp_path))
        assert result["nombre_anomalies"] == 1

    def test_fichier_features_sans_geometrie(self, tmp_path: Any) -> None:
        """Les features sans geometrie sont ignorees sans erreur."""
        features = [
            {
                "type": "Feature",
                "properties": {"id": "1"},
                "geometry": None,
            }
        ]
        _ecrire_geojson_test(str(tmp_path), "test.geojson", 2154, features)
        result = executer_controle_cli(str(tmp_path))
        assert result["succes"] is True
        assert result["nombre_anomalies"] == 0


# --------------------------------------------------------------------------- #
# Tests sur donnees reelles (optionnels)
# --------------------------------------------------------------------------- #


class TestDonneesReelles:
    """Tests sur les donnees reelles de test_conversion."""

    _REPERTOIRE_TEST: str = r"C:\Users\kevin\Downloads\test_conversion"

    @pytest.fixture
    def repertoire_reel(self) -> str:
        if not os.path.isdir(self._REPERTOIRE_TEST):
            pytest.skip("Donnees de test non disponibles")
        return self._REPERTOIRE_TEST

    def test_execution_sans_erreur(self, repertoire_reel: str, tmp_path: Any) -> None:
        result = executer_controle_cli(repertoire_reel, str(tmp_path))
        assert result["succes"] is True
        assert result["fichiers_analyses"] > 0

    def test_coordonnees_fichiers_source_coherentes(
        self, repertoire_reel: str, tmp_path: Any
    ) -> None:
        """Les fichiers source Lambert 93 ont des coordonnees coherentes.

        Les fichiers d'ecarts issus de controles precedents (ex: ecart_proj_ensemble)
        peuvent etre signales s'ils ne portent pas de CRS ; seuls les fichiers
        source RPD_* sont verifies comme conformes.
        """
        result = executer_controle_cli(repertoire_reel, str(tmp_path))
        fichiers_source = [
            d for d in result["detail"] if d["fichier"].startswith("RPD_")
        ]
        assert len(fichiers_source) > 0
        assert all(d["statut"] == "conforme" for d in fichiers_source)
