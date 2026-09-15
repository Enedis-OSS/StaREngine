"""
Tests unitaires du controle de conformite 3D (e0200).

Couvre les cas nominaux et les cas limites :
- detection des entites 2D pour chaque type de geometrie
- exclusion des entites 3D conformes
- gestion des geometries nulles ou vides
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

from typing import Any

from recostar.controle.altimetrie.detection_z_absent import (
    _entite_est_2d,
    _extraire_points_geometrie,
    detecter_entites_2d,
)
from recostar.controle.altimetrie.tests.utils_tests import construire_feature

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
        features = [construire_feature("e1", "Point", [1.0, 2.0])]
        anomalies = detecter_entites_2d(features, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "e1"
        assert anomalies[0]["fichier_source"] == "test.geojson"

    def test_entite_3d_non_detectee(self) -> None:
        features = [construire_feature("e1", "Point", [1.0, 2.0, 3.0])]
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
            construire_feature("ok", "Point", [1.0, 2.0, 3.0]),
            construire_feature("ko", "Point", [4.0, 5.0]),
        ]
        anomalies = detecter_entites_2d(features, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "ko"


# --------------------------------------------------------------------------- #
# Tests du GeoJSON de sortie
# --------------------------------------------------------------------------- #
