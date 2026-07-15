"""
Tests du controle E504 : densite de sommets des cables electriques.

Couvre :
  - le chargement des cables aeriens a exclure
  - l'extraction des parties (LineString / MultiLineString)
  - l'analyse des segments (distance 3D, seuil 15 m)
  - la detection des anomalies (filtre statut, exclusion aerienne)
  - la construction du GeoJSON d'ecarts
  - l'execution CLI complete
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import os
from typing import Any

from controle_e504 import (
    FICHIER_AERIEN,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    SEUIL_DISTANCE,
    STATUT_CONTROLE,
    TYPE_ANOMALIE,
    analyser_geometrie,
    charger_ids_cables_aeriens,
    compter_cables_controles,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
)
from utils_geometrie import extraire_parties_lineaires
from utils_tests import ecrire_collection

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ligne(sommets: list[list[float]]) -> dict[str, Any]:
    """Geometrie LineString a partir d'une liste de sommets."""
    return {"type": "LineString", "coordinates": sommets}


def _feature_cable(
    identifiant: str,
    sommets: list[list[float]],
    statut: str = STATUT_CONTROLE,
) -> dict[str, Any]:
    """Feature GeoJSON representant un cable electrique LineString."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "Statut": statut},
        "geometry": _ligne(sommets),
    }


def _feature_aerien(cables_href: Any) -> dict[str, Any]:
    """Feature GeoJSON minimale d'un cheminement aerien."""
    return {
        "type": "Feature",
        "properties": {"cables_href": cables_href},
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
    }


# Sommets espaces de 10 m (conforme) et de 20 m (non conforme), en 3D
_CONFORME = [[0.0, 0.0, 5.0], [10.0, 0.0, 5.0], [20.0, 0.0, 5.0]]
_NON_CONFORME = [[0.0, 0.0, 5.0], [20.0, 0.0, 5.0], [30.0, 0.0, 5.0]]


# --------------------------------------------------------------------------- #
# Exclusion aerienne
# --------------------------------------------------------------------------- #


class TestChargerIdsCablesAeriens:
    """Tests de charger_ids_cables_aeriens."""

    def test_fichier_absent_aucune_exclusion(self, tmp_path: Any) -> None:
        assert charger_ids_cables_aeriens(str(tmp_path)) == set()

    def test_collecte_ids(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_AERIEN),
            [_feature_aerien("cA"), _feature_aerien("cB")],
        )
        assert charger_ids_cables_aeriens(str(tmp_path)) == {"cA", "cB"}

    def test_href_multi_valeurs(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_AERIEN), [_feature_aerien("cA,cB")])
        assert charger_ids_cables_aeriens(str(tmp_path)) == {"cA", "cB"}


# --------------------------------------------------------------------------- #
# Extraction des parties
# --------------------------------------------------------------------------- #


class TestExtraireParties:
    """Tests de _extraire_parties."""

    def test_linestring(self) -> None:
        assert extraire_parties_lineaires(_ligne(_CONFORME)) == [_CONFORME]

    def test_multilinestring(self) -> None:
        geom = {"type": "MultiLineString", "coordinates": [_CONFORME, _NON_CONFORME]}
        assert extraire_parties_lineaires(geom) == [_CONFORME, _NON_CONFORME]

    def test_geometrie_none(self) -> None:
        assert extraire_parties_lineaires(None) == []

    def test_type_non_lineaire(self) -> None:
        assert extraire_parties_lineaires({"type": "Point", "coordinates": [0.0, 0.0]}) == []

    def test_coordonnees_vides(self) -> None:
        assert extraire_parties_lineaires({"type": "LineString", "coordinates": []}) == []


# --------------------------------------------------------------------------- #
# Analyse de la geometrie
# --------------------------------------------------------------------------- #


class TestAnalyserGeometrie:
    """Tests de analyser_geometrie."""

    def test_conforme(self) -> None:
        distance_max, nb = analyser_geometrie(_ligne(_CONFORME))
        assert distance_max == 10.0
        assert nb == 0

    def test_non_conforme(self) -> None:
        distance_max, nb = analyser_geometrie(_ligne(_NON_CONFORME))
        assert distance_max == 20.0
        assert nb == 1

    def test_seuil_exact_conforme(self) -> None:
        # Segment de 15 m exactement -> conforme (strictement superieur requis)
        _, nb = analyser_geometrie(_ligne([[0.0, 0.0, 0.0], [15.0, 0.0, 0.0]]))
        assert nb == 0

    def test_distance_3d(self) -> None:
        # Segment horizontal de 12 m + denivele de 9 m -> 15 m (3D), conforme
        _, nb = analyser_geometrie(_ligne([[0.0, 0.0, 0.0], [12.0, 0.0, 9.0]]))
        assert nb == 0
        # Meme XY mais denivele de 10 m -> sqrt(144+100) ~ 15.62 m -> non conforme
        distance_max, nb2 = analyser_geometrie(_ligne([[0.0, 0.0, 0.0], [12.0, 0.0, 10.0]]))
        assert nb2 == 1
        assert distance_max > SEUIL_DISTANCE

    def test_multilinestring_compte_toutes_parties(self) -> None:
        geom = {"type": "MultiLineString", "coordinates": [_CONFORME, _NON_CONFORME]}
        distance_max, nb = analyser_geometrie(geom)
        assert distance_max == 20.0
        assert nb == 1

    def test_sommet_sans_z_traite_en_2d(self) -> None:
        # Sommets 2D -> dz=0, distance planimetrique
        _, nb = analyser_geometrie(_ligne([[0.0, 0.0], [20.0, 0.0]]))
        assert nb == 1


# --------------------------------------------------------------------------- #
# Detection des anomalies
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies et compter_cables_controles."""

    def test_cable_conforme(self) -> None:
        features = [_feature_cable("c1", _CONFORME)]
        assert detecter_anomalies(features, set()) == []

    def test_cable_non_conforme(self) -> None:
        features = [_feature_cable("c1", _NON_CONFORME)]
        anomalies = detecter_anomalies(features, set())
        assert len(anomalies) == 1
        assert anomalies[0]["id_cable"] == "c1"
        assert anomalies[0]["distance_max"] == 20.0
        assert anomalies[0]["nombre_segments_trop_longs"] == 1

    def test_statut_non_controle_ignore(self) -> None:
        features = [_feature_cable("c1", _NON_CONFORME, statut="Projected")]
        assert detecter_anomalies(features, set()) == []

    def test_cable_aerien_exclu(self) -> None:
        features = [_feature_cable("c1", _NON_CONFORME)]
        # c1 est aerien -> exclu meme s'il est non conforme
        assert detecter_anomalies(features, {"c1"}) == []

    def test_compter_cables_controles(self) -> None:
        features = [
            _feature_cable("c1", _CONFORME),
            _feature_cable("c2", _CONFORME, statut="Projected"),
            _feature_cable("c3", _CONFORME),
        ]
        # c1 et c3 sont UnderCommissionning ; c3 est aerien -> 1 seul controle
        assert compter_cables_controles(features, {"c3"}) == 1


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "id_cable": "c1",
            "distance_max": 20.0,
            "nombre_segments_trop_longs": 2,
            "geometrie": _ligne(_NON_CONFORME),
        }

    def test_proprietes(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_cable"] == "c1"
        assert props["distance_max_m"] == 20.0
        assert props["seuil_m"] == SEUIL_DISTANCE
        assert props["nombre_segments_trop_longs"] == 2

    def test_geometrie_conservee(self) -> None:
        geom = construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"]
        assert geom["type"] == "LineString"

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichier_cable_absent_non_bloquant(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_cable_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_nominal_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", _CONFORME)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_controles"] == 1
        assert resultat["seuil_m"] == SEUIL_DISTANCE

    def test_nominal_non_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", _NON_CONFORME)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_exclusion_aerienne_integree(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", _NON_CONFORME)])
        ecrire_collection(str(tmp_path / FICHIER_AERIEN), [_feature_aerien("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_controles"] == 0
        assert resultat["nombre_cables_aeriens_exclus"] == 1

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", _NON_CONFORME)])
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", _CONFORME)])
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "nombre_cables_controles",
            "nombre_cables_aeriens_exclus",
            "seuil_m",
            "fichier_cable_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Le controle se comporte identiquement en V1.0 et V1.1.

    La geometrie 3D des cables et le mecanisme d'exclusion aerienne sont
    structurellement identiques dans les deux versions.
    """

    def test_multilinestring_non_conforme(self, tmp_path: Any) -> None:
        feature = {
            "type": "Feature",
            "properties": {"id": "c1", "Statut": STATUT_CONTROLE},
            "geometry": {"type": "MultiLineString", "coordinates": [_CONFORME, _NON_CONFORME]},
        }
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [feature])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
