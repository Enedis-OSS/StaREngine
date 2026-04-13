"""
Tests unitaires du controle des superpositions de cheminements.

Couvre les cas nominaux et les cas limites :
- extraction de segments depuis diverses geometries
- normalisation (symetrie) des segments
- indexation des segments par feature
- construction de la carte de superpositions
- gestion des geometries absentes ou non supportees
- propagation du CRS dans le GeoJSON de sortie
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_cheminement_superpose import (
    FICHIER_SORTIE,
    FICHIERS_CHEMINEMENTS,
    PRIORITE_ANOMALIE,
    construire_anomalies,
    construire_carte_superpositions,
    construire_geojson_ecarts,
    executer_controle_cli,
    extraire_segments_feature,
    extraire_segments_ligne,
    indexer_segments,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #

CRS_2154: dict[str, Any] = {
    "type": "name",
    "properties": {"name": "urn:ogc:def:crs:EPSG::2154"},
}


def _construire_linestring(
    identifiant: str,
    coordonnees: list[list[float]],
) -> dict[str, Any]:
    """Construit une feature LineString minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


def _construire_collection(
    features: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection GeoJSON minimal."""
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


# --------------------------------------------------------------------------- #
# Tests de l'extraction de segments
# --------------------------------------------------------------------------- #


class TestExtraireSegmentsLigne:
    """Tests de l'extraction de segments depuis une liste de coordonnees."""

    def test_ligne_deux_points(self) -> None:
        segments = extraire_segments_ligne([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        assert len(segments) == 1

    def test_ligne_trois_points(self) -> None:
        segments = extraire_segments_ligne(
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]
        )
        assert len(segments) == 2

    def test_segment_degenere_ignore(self) -> None:
        segments = extraire_segments_ligne(
            [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
        )
        assert len(segments) == 1

    def test_un_seul_point_aucun_segment(self) -> None:
        segments = extraire_segments_ligne([[1.0, 2.0, 3.0]])
        assert len(segments) == 0

    def test_liste_vide_aucun_segment(self) -> None:
        segments = extraire_segments_ligne([])
        assert len(segments) == 0

    def test_direction_inverse_produit_meme_segment(self) -> None:
        """Un segment (A, B) et (B, A) sont normalises identiquement."""
        seg_ab = extraire_segments_ligne([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        seg_ba = extraire_segments_ligne([[4.0, 5.0, 6.0], [1.0, 2.0, 3.0]])
        assert seg_ab == seg_ba


class TestExtraireSegmentsFeature:
    """Tests de l'extraction de segments depuis une feature GeoJSON."""

    def test_linestring(self) -> None:
        feature = _construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        segments = extraire_segments_feature(feature)
        assert len(segments) == 1

    def test_multilinestring(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "f1"},
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [
                    [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
                    [[7.0, 8.0, 9.0], [10.0, 11.0, 12.0]],
                ],
            },
        }
        segments = extraire_segments_feature(feature)
        assert len(segments) == 2

    def test_geometrie_absente(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "f1"},
            "geometry": None,
        }
        assert extraire_segments_feature(feature) == set()

    def test_type_non_supporte_point(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "f1"},
            "geometry": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }
        assert extraire_segments_feature(feature) == set()

    def test_coordonnees_absentes(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "f1"},
            "geometry": {"type": "LineString"},
        }
        assert extraire_segments_feature(feature) == set()


# --------------------------------------------------------------------------- #
# Tests de l'indexation des segments
# --------------------------------------------------------------------------- #


class TestIndexerSegments:
    """Tests de l'indexation des segments par feature."""

    def test_deux_features_segment_commun(self) -> None:
        f1 = _construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        f2 = _construire_linestring("f2", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        entrees = [(f1, "fichier1.geojson"), (f2, "fichier2.geojson")]
        index = indexer_segments(entrees)
        assert len(index) == 1
        refs = list(index.values())[0]
        assert sorted(refs) == [0, 1]

    def test_deux_features_segments_distincts(self) -> None:
        f1 = _construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        f2 = _construire_linestring("f2", [[7.0, 8.0, 9.0], [10.0, 11.0, 12.0]])
        entrees = [(f1, "fichier1.geojson"), (f2, "fichier2.geojson")]
        index = indexer_segments(entrees)
        assert len(index) == 2
        for refs in index.values():
            assert len(refs) == 1

    def test_collection_vide(self) -> None:
        assert indexer_segments([]) == {}

    def test_segment_inverse_meme_reference(self) -> None:
        """Deux features dont les segments sont en sens inverse se referencent."""
        f1 = _construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        f2 = _construire_linestring("f2", [[4.0, 5.0, 6.0], [1.0, 2.0, 3.0]])
        entrees = [(f1, "a.geojson"), (f2, "b.geojson")]
        index = indexer_segments(entrees)
        assert len(index) == 1
        assert sorted(list(index.values())[0]) == [0, 1]


# --------------------------------------------------------------------------- #
# Tests de la carte de superpositions
# --------------------------------------------------------------------------- #


class TestCarteSuperpositions:
    """Tests de la construction de la carte de superpositions."""

    def test_segment_partage_par_deux(self) -> None:
        index: dict[Any, list[int]] = {((1.0,), (2.0,)): [0, 1]}
        carte = construire_carte_superpositions(index)
        assert carte == {0: {1}, 1: {0}}

    def test_aucun_segment_partage(self) -> None:
        index: dict[Any, list[int]] = {
            ((1.0,), (2.0,)): [0],
            ((3.0,), (4.0,)): [1],
        }
        carte = construire_carte_superpositions(index)
        assert carte == {}

    def test_trois_features_partagent_segment(self) -> None:
        index: dict[Any, list[int]] = {((1.0,), (2.0,)): [0, 1, 2]}
        carte = construire_carte_superpositions(index)
        assert carte == {0: {1, 2}, 1: {0, 2}, 2: {0, 1}}

    def test_superpositions_multiples_segments(self) -> None:
        """Deux features partagent deux segments differents."""
        index: dict[Any, list[int]] = {
            ((1.0,), (2.0,)): [0, 1],
            ((3.0,), (4.0,)): [0, 1],
        }
        carte = construire_carte_superpositions(index)
        assert carte == {0: {1}, 1: {0}}

    def test_index_vide(self) -> None:
        assert construire_carte_superpositions({}) == {}


# --------------------------------------------------------------------------- #
# Tests de la construction des anomalies
# --------------------------------------------------------------------------- #


class TestConstruireAnomalies:
    """Tests de la construction de la liste d'anomalies."""

    def test_anomalie_contient_id_et_fichier(self) -> None:
        f1 = _construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        f2 = _construire_linestring("f2", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        entrees = [(f1, "fichier1.geojson"), (f2, "fichier2.geojson")]
        carte: dict[int, set[int]] = {0: {1}, 1: {0}}
        anomalies = construire_anomalies(carte, entrees)
        assert len(anomalies) == 2
        assert anomalies[0]["id_entite"] == "f1"
        assert anomalies[0]["fichier_source"] == "fichier1.geojson"
        assert anomalies[0]["ids_superposes"] == ["f2"]

    def test_aucune_superposition(self) -> None:
        assert construire_anomalies({}, []) == []

    def test_ordre_tri_par_indice(self) -> None:
        f1 = _construire_linestring("f1", [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        f2 = _construire_linestring("f2", [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        f3 = _construire_linestring("f3", [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        entrees = [(f1, "a.geojson"), (f2, "b.geojson"), (f3, "c.geojson")]
        carte: dict[int, set[int]] = {2: {0, 1}, 0: {1, 2}, 1: {0, 2}}
        anomalies = construire_anomalies(carte, entrees)
        ids = [a["id_entite"] for a in anomalies]
        assert ids == ["f1", "f2", "f3"]


# --------------------------------------------------------------------------- #
# Tests du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestGeojsonSortie:
    """Tests de la serialisation des superpositions en FeatureCollection."""

    def test_structure_geojson_conforme(self) -> None:
        f1 = _construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        anomalies = [
            {
                "id_entite": "f1",
                "fichier_source": "fichier.geojson",
                "ids_superposes": ["f2"],
                "feature": f1,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1
        props = geojson["features"][0]["properties"]
        assert props["id_entite"] == "f1"
        assert props["fichier_source"] == "fichier.geojson"
        assert props["nb_superpositions"] == 1
        assert props["type_anomalie"] == "superposition_cheminement"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert geojson["features"][0]["geometry"]["type"] == "LineString"

    def test_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_priorite_est_bloquant(self) -> None:
        f1 = _construire_linestring("f1", [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        anomalies = [
            {
                "id_entite": "f1",
                "fichier_source": "f.geojson",
                "ids_superposes": ["f2"],
                "feature": f1,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["features"][0]["properties"]["priorite"] == "bloquant"

    def test_crs_propage_si_present(self) -> None:
        geojson = construire_geojson_ecarts([], crs=CRS_2154)
        assert geojson["crs"] == CRS_2154

    def test_crs_absent_si_non_fourni(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson

    def test_ids_superposes_formates_en_chaine(self) -> None:
        f1 = _construire_linestring("f1", [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        anomalies = [
            {
                "id_entite": "f1",
                "fichier_source": "f.geojson",
                "ids_superposes": ["f2", "f3"],
                "feature": f1,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        props = geojson["features"][0]["properties"]
        assert props["ids_superposes"] == "f2, f3"
        assert props["nb_superpositions"] == 2


# --------------------------------------------------------------------------- #
# Tests CLI bout en bout avec tmp_path
# --------------------------------------------------------------------------- #


@pytest.fixture
def repertoire_test(tmp_path: Any) -> str:
    """Prepare un repertoire avec des fichiers de cheminement superposes."""
    fourreau = _construire_collection(
        [_construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])],
        crs=CRS_2154,
    )
    pleine_terre = _construire_collection(
        [
            _construire_linestring("pt1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
            _construire_linestring("pt2", [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]]),
        ]
    )
    (tmp_path / FICHIERS_CHEMINEMENTS[0]).write_text(
        json.dumps(fourreau), encoding="utf-8"
    )
    (tmp_path / FICHIERS_CHEMINEMENTS[1]).write_text(
        json.dumps(pleine_terre), encoding="utf-8"
    )
    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_execution_ecrit_fichier_sortie(self, repertoire_test: str) -> None:
        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        assert resultat["nombre_entites"] == 3
        assert resultat["nombre_fichiers"] == 2
        assert resultat["nombre_anomalies"] == 2
        chemin = os.path.join(repertoire_test, FICHIER_SORTIE)
        assert os.path.isfile(chemin)
        with open(chemin, "r", encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 2

    def test_crs_propage_dans_sortie(self, repertoire_test: str) -> None:
        executer_controle_cli(repertoire_test)
        chemin = os.path.join(repertoire_test, FICHIER_SORTIE)
        with open(chemin, "r", encoding="utf-8") as f:
            contenu = json.load(f)
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

    def test_aucun_fichier_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "Aucun fichier" in resultat["erreur"]

    def test_aucune_anomalie_si_segments_distincts(self, tmp_path: Any) -> None:
        fourreau = _construire_collection(
            [_construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])],
        )
        pleine_terre = _construire_collection(
            [_construire_linestring("pt1", [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]])],
        )
        (tmp_path / FICHIERS_CHEMINEMENTS[0]).write_text(
            json.dumps(fourreau), encoding="utf-8"
        )
        (tmp_path / FICHIERS_CHEMINEMENTS[1]).write_text(
            json.dumps(pleine_terre), encoding="utf-8"
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_superposition_intra_fichier(self, tmp_path: Any) -> None:
        """Deux entites du meme fichier avec segment commun."""
        pleine_terre = _construire_collection(
            [
                _construire_linestring("pt1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
                _construire_linestring("pt2", [[4.0, 5.0, 6.0], [1.0, 2.0, 3.0]]),
            ]
        )
        (tmp_path / FICHIERS_CHEMINEMENTS[1]).write_text(
            json.dumps(pleine_terre), encoding="utf-8"
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 2

    def test_superposition_partielle(self, tmp_path: Any) -> None:
        """Deux lignes partagent un segment sur plusieurs."""
        fourreau = _construire_collection(
            [
                _construire_linestring(
                    "f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]
                ),
            ]
        )
        pleine_terre = _construire_collection(
            [
                _construire_linestring(
                    "pt1", [[4.0, 5.0, 6.0], [7.0, 8.0, 9.0], [10.0, 11.0, 12.0]]
                ),
            ]
        )
        (tmp_path / FICHIERS_CHEMINEMENTS[0]).write_text(
            json.dumps(fourreau), encoding="utf-8"
        )
        (tmp_path / FICHIERS_CHEMINEMENTS[1]).write_text(
            json.dumps(pleine_terre), encoding="utf-8"
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 2

    def test_un_seul_fichier_avec_superpositions(self, tmp_path: Any) -> None:
        """Un seul fichier present avec deux features superposees."""
        fourreau = _construire_collection(
            [
                _construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
                _construire_linestring("f2", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
            ]
        )
        (tmp_path / FICHIERS_CHEMINEMENTS[0]).write_text(
            json.dumps(fourreau), encoding="utf-8"
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_fichiers"] == 1
        assert resultat["nombre_anomalies"] == 2

    def test_trois_fichiers_presents(self, tmp_path: Any) -> None:
        """Trois fichiers charges, superposition entre fourreau et protection."""
        fourreau = _construire_collection(
            [_construire_linestring("f1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])],
        )
        pleine_terre = _construire_collection(
            [_construire_linestring("pt1", [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]])],
        )
        protection = _construire_collection(
            [_construire_linestring("pm1", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])],
        )
        (tmp_path / FICHIERS_CHEMINEMENTS[0]).write_text(
            json.dumps(fourreau), encoding="utf-8"
        )
        (tmp_path / FICHIERS_CHEMINEMENTS[1]).write_text(
            json.dumps(pleine_terre), encoding="utf-8"
        )
        (tmp_path / FICHIERS_CHEMINEMENTS[2]).write_text(
            json.dumps(protection), encoding="utf-8"
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_fichiers"] == 3
        assert resultat["nombre_anomalies"] == 2
