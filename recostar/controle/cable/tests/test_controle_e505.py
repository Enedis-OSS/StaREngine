"""
Tests du controle E505 : coherence longueur / DomaineTension des cables.

Couvre :
  - le calcul de longueur 3D (LineString / MultiLineString)
  - la resolution du seuil applicable (statut, exclusion aerienne, domaine)
  - la detection des anomalies (BT > 250 m, HTA > 500 m)
  - la construction du GeoJSON d'ecarts
  - l'execution CLI complete
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import os
from typing import Any

import pytest
from controle_e504 import FICHIER_AERIEN, STATUT_CONTROLE
from controle_e505 import (
    CHAMP_DOMAINE,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    TYPE_ANOMALIE,
    _seuil_applicable,
    calculer_longueur,
    compter_cables_controles,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
)
from utils_tests import ecrire_collection

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ligne_longueur(longueur: float) -> dict[str, Any]:
    """LineString horizontale de la longueur demandee (2 sommets, Z constant)."""
    return {"type": "LineString", "coordinates": [[0.0, 0.0, 0.0], [longueur, 0.0, 0.0]]}


def _feature_cable(
    identifiant: str,
    domaine: Any,
    longueur: float,
    statut: str = STATUT_CONTROLE,
) -> dict[str, Any]:
    """Feature GeoJSON representant un cable electrique de longueur donnee."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "Statut": statut, "DomaineTension": domaine},
        "geometry": _ligne_longueur(longueur),
    }


def _feature_aerien(cables_href: Any) -> dict[str, Any]:
    """Feature GeoJSON minimale d'un cheminement aerien."""
    return {
        "type": "Feature",
        "properties": {"cables_href": cables_href},
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
    }


# --------------------------------------------------------------------------- #
# Calcul de longueur
# --------------------------------------------------------------------------- #


class TestCalculerLongueur:
    """Tests de calculer_longueur."""

    def test_linestring_horizontale(self) -> None:
        assert calculer_longueur(_ligne_longueur(100.0)) == 100.0

    def test_3d(self) -> None:
        """Le denivele compte dans la longueur.

        Altitudes non nulles : un Z a 0.0 designe une altitude absente et serait
        corrige par propagation, ce qui annulerait le denivele teste ici.
        """
        # 3-4-5 : dx=3, dz=4 -> 5
        geom = {"type": "LineString", "coordinates": [[0.0, 0.0, 100.0], [3.0, 0.0, 104.0]]}
        assert calculer_longueur(geom) == 5.0

    def test_z_nul_ne_gonfle_pas_la_longueur(self) -> None:
        """Un sommet a Z=0 ne doit pas ajouter l'altitude du terrain a la longueur.

        Cas rencontre en production : un cable de 5,93 m etait mesure a 315,88 m
        et declare en longueur excessive (seuil BT 250 m) parce qu'une de ses
        extremites n'avait pas d'altitude renseignee.
        """
        geom = {
            "type": "LineString",
            "coordinates": [
                [850023.56, 6799907.27, 310.41],
                [850023.627197055, 6799906.4913877, 0.0],
            ],
        }
        assert calculer_longueur(geom) == pytest.approx(0.78, abs=0.01)

    def test_multilinestring_somme_parties(self) -> None:
        geom = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]],
                [[0.0, 0.0, 0.0], [50.0, 0.0, 0.0]],
            ],
        }
        assert calculer_longueur(geom) == 150.0

    def test_geometrie_none(self) -> None:
        assert calculer_longueur(None) == 0.0

    def test_sommets_2d(self) -> None:
        geom = {"type": "LineString", "coordinates": [[0.0, 0.0], [40.0, 30.0]]}
        assert calculer_longueur(geom) == 50.0


# --------------------------------------------------------------------------- #
# Seuil applicable
# --------------------------------------------------------------------------- #


class TestSeuilApplicable:
    """Tests de _seuil_applicable."""

    def _props(self, domaine: Any = "BT", statut: str = STATUT_CONTROLE) -> dict[str, Any]:
        return {"Statut": statut, CHAMP_DOMAINE: domaine}

    def test_bt(self) -> None:
        assert _seuil_applicable(self._props("BT"), "c1", set()) == 250.0

    def test_hta(self) -> None:
        assert _seuil_applicable(self._props("HTA"), "c1", set()) == 500.0

    def test_htb_non_controle(self) -> None:
        assert _seuil_applicable(self._props("HTB"), "c1", set()) is None

    def test_statut_non_controle(self) -> None:
        assert _seuil_applicable(self._props("BT", statut="Projected"), "c1", set()) is None

    def test_cable_aerien(self) -> None:
        assert _seuil_applicable(self._props("BT"), "c1", {"c1"}) is None


# --------------------------------------------------------------------------- #
# Detection des anomalies
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies et compter_cables_controles."""

    def test_bt_conforme(self) -> None:
        # 250 m exactement -> conforme (strictement superieur requis)
        assert detecter_anomalies([_feature_cable("c1", "BT", 250.0)], set()) == []

    def test_bt_non_conforme(self) -> None:
        anomalies = detecter_anomalies([_feature_cable("c1", "BT", 250.1)], set())
        assert len(anomalies) == 1
        assert anomalies[0]["id_cable"] == "c1"
        assert anomalies[0]["domaine_tension"] == "BT"
        assert anomalies[0]["seuil"] == 250.0
        assert anomalies[0]["longueur"] == 250.1

    def test_hta_conforme(self) -> None:
        assert detecter_anomalies([_feature_cable("c1", "HTA", 500.0)], set()) == []

    def test_hta_non_conforme(self) -> None:
        assert len(detecter_anomalies([_feature_cable("c1", "HTA", 600.0)], set())) == 1

    def test_htb_ignore(self) -> None:
        # HTB tres long mais hors perimetre du controle
        assert detecter_anomalies([_feature_cable("c1", "HTB", 9999.0)], set()) == []

    def test_statut_ignore(self) -> None:
        assert detecter_anomalies([_feature_cable("c1", "BT", 999.0, statut="Functional")], set()) == []

    def test_aerien_exclu(self) -> None:
        assert detecter_anomalies([_feature_cable("c1", "BT", 999.0)], {"c1"}) == []

    def test_compter_cables_controles(self) -> None:
        features = [
            _feature_cable("c1", "BT", 10.0),
            _feature_cable("c2", "HTB", 10.0),  # domaine non controle
            _feature_cable("c3", "HTA", 10.0),
            _feature_cable("c4", "BT", 10.0, statut="Projected"),  # statut ignore
        ]
        assert compter_cables_controles(features, set()) == 2


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "id_cable": "c1",
            "domaine_tension": "BT",
            "longueur": 300.5,
            "seuil": 250.0,
            "geometrie": _ligne_longueur(300.5),
        }

    def test_proprietes(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_cable"] == "c1"
        assert props["domaine_tension"] == "BT"
        assert props["longueur_m"] == 300.5
        assert props["seuil_m"] == 250.0

    def test_priorite_information(self) -> None:
        assert PRIORITE_ANOMALIE == "information"

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
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "BT", 100.0), _feature_cable("c2", "HTA", 400.0)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_controles"] == 2
        assert resultat["priorite"] == "information"

    def test_nominal_non_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "BT", 300.0), _feature_cable("c2", "HTA", 400.0)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_exclusion_aerienne_integree(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", "BT", 999.0)])
        ecrire_collection(str(tmp_path / FICHIER_AERIEN), [_feature_aerien("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_controles"] == 0
        assert resultat["nombre_cables_aeriens_exclus"] == 1

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", "BT", 300.0)])
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", "BT", 100.0)])
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "nombre_cables_controles",
            "nombre_cables_aeriens_exclus",
            "fichier_cable_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Le controle se comporte identiquement en V1.0 et V1.1."""

    def test_multilinestring_bt_non_conforme(self, tmp_path: Any) -> None:
        feature = {
            "type": "Feature",
            "properties": {"id": "c1", "Statut": STATUT_CONTROLE, "DomaineTension": "BT"},
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [
                    [[0.0, 0.0, 0.0], [150.0, 0.0, 0.0]],
                    [[150.0, 0.0, 0.0], [280.0, 0.0, 0.0]],
                ],
            },
        }
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [feature])
        resultat = executer_controle_cli(str(tmp_path))
        # Longueur totale 280 m > 250 m (BT)
        assert resultat["nombre_anomalies"] == 1
