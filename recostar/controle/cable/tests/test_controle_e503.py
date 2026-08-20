"""
Tests du controle E503 : precision XY/Z des cheminements associes a un cable.

Couvre :
  - le chargement des cables a controler (filtre Statut)
  - l'indexation des cheminements par cable (3 couches, filtrage par set)
  - la detection des cheminements non conformes
  - la construction du GeoJSON d'ecarts
  - l'execution CLI complete
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import os
from typing import Any

from controle_e503 import (
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    STATUT_CONTROLE,
    TYPE_ANOMALIE,
    EntiteCheminement,
    _est_conforme,
    charger_ids_cables_a_controler,
    compter_liens,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
    indexer_cheminements_par_cable,
)
from utils_tests import ecrire_collection

# Fichiers cheminement (constantes locales pour la lisibilite des tests)
FICHIER_FOURREAU = "RPD_Fourreau_Reco.geojson"
FICHIER_PLEINE_TERRE = "RPD_PleineTerre_Reco.geojson"
FICHIER_PROTECTION = "RPD_ProtectionMecanique_Reco.geojson"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _feature_cable(identifiant: str, statut: str = STATUT_CONTROLE) -> dict[str, Any]:
    """Feature GeoJSON minimale representant un cable electrique."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "Statut": statut},
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
    }


def _feature_cheminement(
    identifiant: str,
    cables_href: Any,
    precision_xy: Any = "A",
    precision_z: Any = "A",
) -> dict[str, Any]:
    """Feature GeoJSON minimale representant un cheminement."""
    return {
        "type": "Feature",
        "properties": {
            "id": identifiant,
            "cables_href": cables_href,
            "PrecisionXY": precision_xy,
            "PrecisionZ": precision_z,
        },
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [2.0, 0.0]]},
    }


def _cheminement(
    precision_xy: Any = "A",
    precision_z: Any = "A",
    fichier: str = FICHIER_FOURREAU,
    identifiant: str = "ch1",
) -> EntiteCheminement:
    """Construit une EntiteCheminement de test."""
    return EntiteCheminement(
        id_entite=identifiant,
        fichier=fichier,
        precision_xy=precision_xy,
        precision_z=precision_z,
        geometrie={"type": "LineString", "coordinates": [[0.0, 0.0], [2.0, 0.0]]},
    )


# --------------------------------------------------------------------------- #
# Chargement des cables a controler
# --------------------------------------------------------------------------- #


class TestChargerIdsCables:
    """Tests de charger_ids_cables_a_controler."""

    def test_fichier_absent(self, tmp_path: Any) -> None:
        ids, absent = charger_ids_cables_a_controler(str(tmp_path))
        assert ids == set()
        assert absent is True

    def test_filtre_statut(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [
                _feature_cable("c1", STATUT_CONTROLE),
                _feature_cable("c2", "Projected"),
                _feature_cable("c3", STATUT_CONTROLE),
            ],
        )
        ids, absent = charger_ids_cables_a_controler(str(tmp_path))
        assert absent is False
        assert ids == {"c1", "c3"}


# --------------------------------------------------------------------------- #
# Indexation des cheminements
# --------------------------------------------------------------------------- #


class TestIndexerCheminements:
    """Tests de indexer_cheminements_par_cable."""

    def test_fichiers_absents(self, tmp_path: Any) -> None:
        index, absents, _ = indexer_cheminements_par_cable(str(tmp_path), {"c1"})
        assert index == {}
        assert set(absents) == {FICHIER_FOURREAU, FICHIER_PLEINE_TERRE, FICHIER_PROTECTION}

    def test_indexation_par_cable(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_FOURREAU),
            [_feature_cheminement("ch1", "c1")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_PLEINE_TERRE),
            [_feature_cheminement("ch2", "c1")],
        )
        index, _, _ = indexer_cheminements_par_cable(str(tmp_path), {"c1"})
        assert set(index.keys()) == {"c1"}
        assert len(index["c1"]) == 2

    def test_cheminement_cable_non_controle_ignore(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_FOURREAU),
            [_feature_cheminement("ch1", "c_autre")],
        )
        index, _, _ = indexer_cheminements_par_cable(str(tmp_path), {"c1"})
        assert index == {}

    def test_cheminement_multi_cables(self, tmp_path: Any) -> None:
        # Un cheminement referençant deux cables controles est indexe sous les deux
        ecrire_collection(
            str(tmp_path / FICHIER_FOURREAU),
            [_feature_cheminement("ch1", "c1,c2")],
        )
        index, _, _ = indexer_cheminements_par_cable(str(tmp_path), {"c1", "c2"})
        assert index["c1"][0].id_entite == "ch1"
        assert index["c2"][0].id_entite == "ch1"


# --------------------------------------------------------------------------- #
# Detection des anomalies
# --------------------------------------------------------------------------- #


class TestEstConforme:
    """Tests de _est_conforme."""

    def test_deux_a_conforme(self) -> None:
        assert _est_conforme(_cheminement("A", "A")) is True

    def test_xy_non_a(self) -> None:
        assert _est_conforme(_cheminement("B", "A")) is False

    def test_z_non_a(self) -> None:
        assert _est_conforme(_cheminement("A", "C")) is False

    def test_none_non_conforme(self) -> None:
        assert _est_conforme(_cheminement(None, "A")) is False


class TestDetecterAnomalies:
    """Tests de detecter_anomalies et compter_liens."""

    def test_tous_conformes(self) -> None:
        index = {"c1": [_cheminement("A", "A"), _cheminement("A", "A")]}
        assert detecter_anomalies(index) == []

    def test_un_non_conforme(self) -> None:
        index = {"c1": [_cheminement("A", "A"), _cheminement("B", "A", identifiant="ch2")]}
        anomalies = detecter_anomalies(index)
        assert len(anomalies) == 1
        assert anomalies[0]["id_cable"] == "c1"
        assert anomalies[0]["id_cheminement"] == "ch2"
        assert anomalies[0]["precision_xy"] == "B"

    def test_plusieurs_cables(self) -> None:
        index = {
            "c1": [_cheminement("A", "A")],
            "c2": [_cheminement("A", "Z"), _cheminement("W", "A")],
        }
        assert len(detecter_anomalies(index)) == 2

    def test_compter_liens(self) -> None:
        index = {"c1": [_cheminement(), _cheminement()], "c2": [_cheminement()]}
        assert compter_liens(index) == 3


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "id_cable": "c1",
            "fichier_cheminement": FICHIER_FOURREAU,
            "id_cheminement": "ch1",
            "precision_xy": "B",
            "precision_z": "A",
            "geometrie": {"type": "LineString", "coordinates": [[0.0, 0.0], [2.0, 0.0]]},
        }

    def test_proprietes(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_cable"] == "c1"
        assert props["fichier_cheminement"] == FICHIER_FOURREAU
        assert props["id_cheminement"] == "ch1"
        assert props["precision_xy"] == "B"
        assert props["precision_z"] == "A"

    def test_geometrie_cheminement(self) -> None:
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

    def _ecrire_jeu(
        self,
        tmp_path: Any,
        cables: list[dict[str, Any]],
        fourreaux: list[dict[str, Any]] | None = None,
    ) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), cables)
        if fourreaux is not None:
            ecrire_collection(str(tmp_path / FICHIER_FOURREAU), fourreaux)

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_nominal_conforme(self, tmp_path: Any) -> None:
        self._ecrire_jeu(
            tmp_path,
            [_feature_cable("c1")],
            [_feature_cheminement("ch1", "c1", "A", "A")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_controles"] == 1
        assert resultat["nombre_liens_controles"] == 1

    def test_nominal_non_conforme(self, tmp_path: Any) -> None:
        self._ecrire_jeu(
            tmp_path,
            [_feature_cable("c1")],
            [_feature_cheminement("ch1", "c1", "B", "A")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_cable_non_under_commissionning_ignore(self, tmp_path: Any) -> None:
        # Cheminement non conforme mais cable Projected -> pas de controle
        self._ecrire_jeu(
            tmp_path,
            [_feature_cable("c1", "Projected")],
            [_feature_cheminement("ch1", "c1", "B", "B")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_controles"] == 0

    def test_cable_sans_cheminement_conforme(self, tmp_path: Any) -> None:
        # Aucun cheminement associe -> conforme (vacuite)
        self._ecrire_jeu(tmp_path, [_feature_cable("c1")], [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_liens_controles"] == 0

    def test_fichier_cable_absent_non_bloquant(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_cable_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        self._ecrire_jeu(
            tmp_path,
            [_feature_cable("c1")],
            [_feature_cheminement("ch1", "c1", "B", "A")],
        )
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        self._ecrire_jeu(
            tmp_path,
            [_feature_cable("c1")],
            [_feature_cheminement("ch1", "c1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "nombre_cables_controles",
            "nombre_liens_controles",
            "fichier_cable_absent",
            "fichiers_cheminement_absents",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Le controle se comporte identiquement en V1.0 et V1.1.

    Les couches, cables_href et champs de precision sont structurellement
    identiques dans les deux versions.
    """

    def test_plusieurs_couches_cheminement(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        ecrire_collection(str(tmp_path / FICHIER_FOURREAU), [_feature_cheminement("f1", "c1", "A", "A")])
        ecrire_collection(str(tmp_path / FICHIER_PLEINE_TERRE), [_feature_cheminement("p1", "c1", "A", "B")])
        ecrire_collection(str(tmp_path / FICHIER_PROTECTION), [_feature_cheminement("m1", "c1", "C", "A")])
        resultat = executer_controle_cli(str(tmp_path))
        # p1 (Z=B) et m1 (XY=C) non conformes ; f1 conforme
        assert resultat["nombre_anomalies"] == 2
        assert resultat["nombre_liens_controles"] == 3
