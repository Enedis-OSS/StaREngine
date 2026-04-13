"""
Tests unitaires du controle des extremites des cables.

Couvre les cas nominaux et les cas limites :
- construction du GeoJSON d'ecarts avec le champ priorite
- extremite liee a une jonction
- extremite liee a un poste electrique (cables_href seul, sans proximite)
- cables_href au format chaine separee par virgules
- extremite non liee
- retrocompatibilite sans postes electriques
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_extremites import (
    construire_geojson_ecarts,
    construire_rapport_json,
    controler_extremites,
    executer_controle_cli,
    extraire_ids_cables_href,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #

PRIORITE_ATTENDUE: str = "bloquant"


def _construire_cable(
    identifiant: str, coordonnees: list[list[float]]
) -> dict[str, Any]:
    """Construit une feature cable electrique minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


def _construire_jonction(
    identifiant: str,
    coordonnees: list[float],
    cables_href: list[str] | str | None = None,
) -> dict[str, Any]:
    """Construit une feature jonction minimale pour les tests."""
    props: dict[str, Any] = {"id": identifiant}
    if cables_href is not None:
        props["cables_href"] = cables_href
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": coordonnees},
    }


def _construire_poste_electrique(
    identifiant: str,
    coordonnees: list[float],
    cables_href: str | None = None,
) -> dict[str, Any]:
    """Construit une feature poste electrique minimale pour les tests."""
    props: dict[str, Any] = {"id": identifiant}
    if cables_href is not None:
        props["cables_href"] = cables_href
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": coordonnees},
    }


# --------------------------------------------------------------------------- #
# Tests du parsing de cables_href
# --------------------------------------------------------------------------- #


class TestExtraireIdsCablesHref:
    """Verifie l'extraction des identifiants depuis cables_href."""

    def test_chaine_separee_par_virgules(self) -> None:
        """Une chaine CSV est correctement decoupee en identifiants."""
        feature: dict[str, Any] = {"properties": {"cables_href": "idA,idB,idC"}}
        assert extraire_ids_cables_href(feature) == {"idA", "idB", "idC"}

    def test_chaine_simple(self) -> None:
        """Une chaine sans virgule retourne un seul identifiant."""
        feature: dict[str, Any] = {"properties": {"cables_href": "idA"}}
        assert extraire_ids_cables_href(feature) == {"idA"}

    def test_chaine_avec_espaces(self) -> None:
        """Les espaces autour des identifiants sont supprimes."""
        feature: dict[str, Any] = {"properties": {"cables_href": "idA , idB , idC"}}
        assert extraire_ids_cables_href(feature) == {"idA", "idB", "idC"}

    def test_liste_d_identifiants(self) -> None:
        """Une liste de chaines est supportee."""
        feature: dict[str, Any] = {"properties": {"cables_href": ["idA", "idB"]}}
        assert extraire_ids_cables_href(feature) == {"idA", "idB"}

    def test_cables_href_absent(self) -> None:
        """Retourne un ensemble vide si cables_href est absent."""
        feature: dict[str, Any] = {"properties": {}}
        assert extraire_ids_cables_href(feature) == set()

    def test_cables_href_none(self) -> None:
        """Retourne un ensemble vide si cables_href vaut None."""
        feature: dict[str, Any] = {"properties": {"cables_href": None}}
        assert extraire_ids_cables_href(feature) == set()


# --------------------------------------------------------------------------- #
# Tests du champ priorite dans le GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestPrioriteGeojsonEcarts:
    """Verifie la presence du champ priorite dans chaque feature d'ecart."""

    def test_priorite_extremite_non_liee(self) -> None:
        """Une extremite non liee doit avoir priorite bloquant."""
        resultats = [
            {
                "id_cable": "C1",
                "extremite_depart": {
                    "coordonnees": [1.0, 2.0],
                    "entites_liees": [],
                    "lien_valide": False,
                },
                "extremite_arrivee": {
                    "coordonnees": [3.0, 4.0],
                    "entites_liees": [{"id": "J1"}],
                    "lien_valide": True,
                },
            }
        ]
        geojson = construire_geojson_ecarts(resultats)
        features = geojson["features"]

        assert len(features) == 1
        assert features[0]["properties"]["priorite"] == PRIORITE_ATTENDUE
        assert features[0]["properties"]["extremite"] == "extremite_depart"

    def test_priorite_deux_extremites_non_liees(self) -> None:
        """Les deux extremites non liees doivent chacune avoir priorite bloquant."""
        resultats = [
            {
                "id_cable": "C1",
                "extremite_depart": {
                    "coordonnees": [1.0, 2.0],
                    "entites_liees": [],
                    "lien_valide": False,
                },
                "extremite_arrivee": {
                    "coordonnees": [3.0, 4.0],
                    "entites_liees": [],
                    "lien_valide": False,
                },
            }
        ]
        geojson = construire_geojson_ecarts(resultats)

        assert len(geojson["features"]) == 2
        for feature in geojson["features"]:
            assert feature["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_aucune_feature_si_tout_valide(self) -> None:
        """Aucune feature si toutes les extremites sont valides."""
        resultats = [
            {
                "id_cable": "C1",
                "extremite_depart": {
                    "coordonnees": [0.0, 0.0],
                    "entites_liees": [{"id": "J1"}],
                    "lien_valide": True,
                },
                "extremite_arrivee": {
                    "coordonnees": [1.0, 0.0],
                    "entites_liees": [{"id": "J2"}],
                    "lien_valide": True,
                },
            }
        ]
        geojson = construire_geojson_ecarts(resultats)
        assert geojson["features"] == []

    def test_crs_propage_si_present(self) -> None:
        """Le CRS est propage dans le FeatureCollection de sortie."""
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        """Aucun champ crs si non fourni."""
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson


# --------------------------------------------------------------------------- #
# Tests de la logique metier
# --------------------------------------------------------------------------- #


class TestControlerExtremites:
    """Verifie la validation des extremites de cables."""

    def test_extremite_liee_a_jonction(self) -> None:
        """Un cable dont les deux extremites sont liees a des jonctions est conforme."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        jonction_depart = _construire_jonction("J1", [0.0, 0.0], cables_href=["C1"])
        jonction_arrivee = _construire_jonction("J2", [10.0, 0.0], cables_href=["C1"])
        collections_noeuds = {
            "RPD_Jonction_Reco.geojson": [jonction_depart, jonction_arrivee]
        }

        resultats = controler_extremites([cable], collections_noeuds, [])

        assert len(resultats) == 1
        assert resultats[0]["extremite_depart"]["lien_valide"] is True
        assert resultats[0]["extremite_arrivee"]["lien_valide"] is True

    def test_extremite_isolee(self) -> None:
        """Un cable sans entite proche a une extremite non valide."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])

        resultats = controler_extremites([cable], {}, [])

        assert len(resultats) == 1
        assert resultats[0]["extremite_depart"]["lien_valide"] is False
        assert resultats[0]["extremite_arrivee"]["lien_valide"] is False

    def test_retrocompatibilite_sans_postes(self) -> None:
        """Le controle fonctionne sans postes electriques (parametre optionnel)."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        jonction = _construire_jonction("J1", [0.0, 0.0], cables_href=["C1"])
        collections_noeuds = {"RPD_Jonction_Reco.geojson": [jonction]}

        resultats = controler_extremites([cable], collections_noeuds, [])

        assert len(resultats) == 1
        assert resultats[0]["extremite_depart"]["lien_valide"] is True


# --------------------------------------------------------------------------- #
# Tests de l'integration des postes electriques
# --------------------------------------------------------------------------- #


class TestPostesElectriques:
    """Verifie l'integration des postes electriques dans le controle."""

    def test_extremite_liee_a_poste_par_cables_href(self) -> None:
        """Un poste referencant le cable valide l'extremite sans contrainte de distance."""
        cable = _construire_cable("C1", [[0.0, 0.0], [100.0, 0.0]])
        # Poste eloigne (> seuil de 0.5m) mais referencant le cable
        poste = _construire_poste_electrique("P1", [50.0, 50.0], cables_href="C1")

        resultats = controler_extremites([cable], {}, [], features_postes=[poste])

        assert len(resultats) == 1
        # Les deux extremites sont validees par le poste via cables_href
        assert resultats[0]["extremite_depart"]["lien_valide"] is True
        assert resultats[0]["extremite_arrivee"]["lien_valide"] is True

    def test_poste_sans_reference_cable_ne_valide_pas(self) -> None:
        """Un poste qui ne reference pas le cable ne valide pas l'extremite."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        poste = _construire_poste_electrique("P1", [0.0, 0.0], cables_href="AUTRE")

        resultats = controler_extremites([cable], {}, [], features_postes=[poste])

        assert resultats[0]["extremite_depart"]["lien_valide"] is False

    def test_poste_avec_cables_href_csv(self) -> None:
        """Un poste avec cables_href en CSV valide les cables references."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        poste = _construire_poste_electrique("P1", [5.0, 5.0], cables_href="C1,C2,C3")

        resultats = controler_extremites([cable], {}, [], features_postes=[poste])

        assert resultats[0]["extremite_depart"]["lien_valide"] is True

    def test_entite_liee_type_poste_electrique(self) -> None:
        """L'entite liee de type poste porte le bon type et la distance informative."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        poste = _construire_poste_electrique("P1", [3.0, 4.0], cables_href="C1")

        resultats = controler_extremites([cable], {}, [], features_postes=[poste])

        entites_depart = resultats[0]["extremite_depart"]["entites_liees"]
        assert len(entites_depart) == 1
        assert entites_depart[0]["type"] == "PosteElectrique"
        assert entites_depart[0]["id"] == "P1"
        assert abs(entites_depart[0]["distance"] - 5.0) < 1e-9

    def test_jonction_csv_et_poste_combines(self) -> None:
        """Jonction (cables_href CSV) et poste valident des extremites differentes."""
        cable = _construire_cable("C1", [[0.0, 0.0], [100.0, 0.0]])
        jonction = _construire_jonction("J1", [0.0, 0.0], cables_href="C1,C2")
        poste = _construire_poste_electrique("P1", [200.0, 200.0], cables_href="C1")
        collections_noeuds = {"RPD_Jonction_Reco.geojson": [jonction]}

        resultats = controler_extremites(
            [cable], collections_noeuds, [], features_postes=[poste]
        )

        # Depart: lie par jonction (proche + href) ET poste (href seul)
        assert resultats[0]["extremite_depart"]["lien_valide"] is True
        # Arrivee: lie par poste uniquement (href seul, sans contrainte de distance)
        assert resultats[0]["extremite_arrivee"]["lien_valide"] is True


# --------------------------------------------------------------------------- #
# Tests du rapport JSON
# --------------------------------------------------------------------------- #


class TestConstruireRapportJson:
    """Verifie la structure du rapport JSON."""

    def test_rapport_cables_non_conformes(self) -> None:
        """Le rapport compte correctement les cables non conformes."""
        resultats = [
            {
                "id_cable": "C1",
                "extremite_depart": {"lien_valide": False},
                "extremite_arrivee": {"lien_valide": True},
            },
            {
                "id_cable": "C2",
                "extremite_depart": {"lien_valide": True},
                "extremite_arrivee": {"lien_valide": True},
            },
        ]
        rapport = construire_rapport_json(resultats)
        assert rapport["cables_non_conformes"] == 1
        assert rapport["cables_conformes"] == 1


# --------------------------------------------------------------------------- #
# Test CLI bout en bout
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Verifie l'execution CLI avec ecriture des fichiers de sortie."""

    def test_cli_genere_fichiers_avec_priorite(self, tmp_path: Any) -> None:
        """Le GeoJSON de sortie contient le champ priorite sur chaque feature."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        cables = {"type": "FeatureCollection", "features": [cable]}

        chemin_cables = os.path.join(str(tmp_path), "RPD_CableElectrique_Reco.geojson")
        with open(chemin_cables, "w", encoding="utf-8") as f:
            json.dump(cables, f)

        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        chemin_ecarts = resultat["ecarts"]
        with open(chemin_ecarts, "r", encoding="utf-8") as f:
            geojson = json.load(f)

        for feature in geojson["features"]:
            assert feature["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_cli_avec_poste_electrique(self, tmp_path: Any) -> None:
        """Le CLI charge et utilise les postes electriques."""
        cable = _construire_cable("C1", [[0.0, 0.0], [100.0, 0.0]])
        poste = _construire_poste_electrique("P1", [50.0, 50.0], cables_href="C1")

        for nom, donnees in [
            (
                "RPD_CableElectrique_Reco.geojson",
                {"type": "FeatureCollection", "features": [cable]},
            ),
            (
                "RPD_PosteElectrique_Reco.geojson",
                {"type": "FeatureCollection", "features": [poste]},
            ),
        ]:
            chemin = os.path.join(str(tmp_path), nom)
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump(donnees, f)

        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        chemin_rapport = resultat["rapport"]
        with open(chemin_rapport, "r", encoding="utf-8") as f:
            rapport = json.load(f)

        # Le cable est conforme grace au poste
        assert rapport["cables_conformes"] == 1
        assert rapport["cables_non_conformes"] == 0
