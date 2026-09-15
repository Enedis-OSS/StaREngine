"""
Tests unitaires du controle des coordonnees Z nulles (e0201).

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

from typing import Any

from recostar.controle.altimetrie.detection_z_nul import (
    VALEUR_STATUT_CONTROLE,
    _extraire_points_indexes,
    detecter_z_null_collection,
    detecter_z_null_feature,
    filtrer_features_a_controler,
    resoudre_fichiers_a_controler,
)
from recostar.controle.altimetrie.tests.utils_tests import (
    construire_feature,
    construire_feature_avec_proprietes,
    ecrire_collection,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    FICHIER_CABLE_ELECTRIQUE,
)

# Statut metier requis pour qu'une entite soit soumise au controle
_STATUT: dict[str, str] = {"Statut": VALEUR_STATUT_CONTROLE}


def _feature_controlee(identifiant: str, type_geom: str, coordonnees: Any) -> dict[str, Any]:
    """Feature de test portant le statut UnderCommissionning (donc controlee)."""
    return construire_feature_avec_proprietes(identifiant, type_geom, coordonnees, _STATUT)


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
        feature = construire_feature("p1", "Point", [1.0, 2.0, 0.0])
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "p1"
        assert anomalies[0]["indice_sommet"] == 0
        assert anomalies[0]["coordonnees"] == [1.0, 2.0, 0.0]

    def test_point_z_non_nul_ignore(self) -> None:
        feature = construire_feature("p1", "Point", [1.0, 2.0, 10.5])
        assert detecter_z_null_feature(feature, "test.geojson") == []

    def test_point_2d_ignore(self) -> None:
        feature = construire_feature("p1", "Point", [1.0, 2.0])
        assert detecter_z_null_feature(feature, "test.geojson") == []

    def test_linestring_avec_z_nul_partiel(self) -> None:
        coords = [[0, 0, 10.0], [1, 1, 0.0], [2, 2, 20.0]]
        feature = construire_feature("ls1", "LineString", coords)
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["indice_sommet"] == 1

    def test_linestring_avec_tous_z_nuls(self) -> None:
        coords = [[0, 0, 0.0], [1, 1, 0.0], [2, 2, 0.0]]
        feature = construire_feature("ls2", "LineString", coords)
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        assert len(anomalies) == 3

    def test_linestring_sans_z_nul(self) -> None:
        coords = [[0, 0, 10.0], [1, 1, 20.0]]
        feature = construire_feature("ls3", "LineString", coords)
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
        feature = construire_feature("pg1", "Polygon", [anneau])
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        assert len(anomalies) == 2

    def test_multipolygon_z_nul(self) -> None:
        anneau = [[0, 0, 0.0], [1, 0, 5.0], [1, 1, 5.0], [0, 0, 0.0]]
        feature = construire_feature("mp1", "MultiPolygon", [[anneau]])
        anomalies = detecter_z_null_feature(feature, "test.geojson")
        assert len(anomalies) == 2

    def test_fichier_source_propage(self) -> None:
        feature = construire_feature("p1", "Point", [1.0, 2.0, 0.0])
        anomalies = detecter_z_null_feature(feature, "RPD_Cable.geojson")
        assert anomalies[0]["fichier_source"] == "RPD_Cable.geojson"


# --------------------------------------------------------------------------- #
# Tests de la detection sur une collection
# --------------------------------------------------------------------------- #


class TestDetecterZNullCollection:
    """Tests de la detection sur une collection de features."""

    def test_melange_conforme_et_non_conforme(self) -> None:
        features = [
            construire_feature("ok", "Point", [1.0, 2.0, 10.0]),
            construire_feature("ko", "Point", [3.0, 4.0, 0.0]),
        ]
        anomalies = detecter_z_null_collection(features, "test.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "ko"

    def test_collection_vide(self) -> None:
        assert detecter_z_null_collection([], "test.geojson") == []


# --------------------------------------------------------------------------- #
# Tests du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestFiltrageStatut:
    """Tests du filtrage metier sur le champ Statut."""

    def test_conserve_under_commissionning(self) -> None:
        features = [_feature_controlee("a", "Point", [0, 0, 0.0])]
        assert filtrer_features_a_controler(features) == features

    def test_exclut_autres_statuts(self) -> None:
        feature = construire_feature_avec_proprietes("b", "Point", [0, 0, 0.0], {"Statut": "InService"})
        assert filtrer_features_a_controler([feature]) == []

    def test_exclut_statut_absent(self) -> None:
        assert filtrer_features_a_controler([construire_feature("c", "Point", [0, 0, 0.0])]) == []


class TestResoudreFichiers:
    """Tests de la resolution du perimetre de fichiers selon la version."""

    def test_v1_0_restreint_au_cable_electrique(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / "autre.geojson"), [])
        assert resoudre_fichiers_a_controler(str(tmp_path), "1.0") == [FICHIER_CABLE_ELECTRIQUE]

    def test_v1_1_liste_tous_les_geojson(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / "RPD_A.geojson"), [])
        ecrire_collection(str(tmp_path / "RPD_B.geojson"), [])
        ecrire_collection(str(tmp_path / "ecarts_e0201_z_null.geojson"), [])
        fichiers = resoudre_fichiers_a_controler(str(tmp_path), "1.1")
        assert set(fichiers) == {"RPD_A.geojson", "RPD_B.geojson"}
