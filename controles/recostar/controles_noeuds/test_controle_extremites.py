"""
Tests unitaires du controle des extremites des cables.

Couvre les cas nominaux et les cas limites :
- construction du GeoJSON d'ecarts avec le champ priorite
- extremite liee a une jonction via cables_href
- extremite liee a un poste electrique via cables_href
- extremite liee a un coupe-circuit a fusibles via cables_href
- extremite liee a un point de comptage via cables_href
- cables_href au format chaine separee par virgules
- extremite non liee (aucun noeud ne reference le cable)
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


def _construire_noeud(
    identifiant: str,
    coordonnees: list[float],
    cables_href: list[str] | str | None = None,
    domaine_tension: str | None = None,
) -> dict[str, Any]:
    """Construit une feature noeud minimale pour les tests."""
    props: dict[str, Any] = {"id": identifiant}
    if cables_href is not None:
        props["cables_href"] = cables_href
    if domaine_tension is not None:
        props["DomaineTension"] = domaine_tension
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
    """Verifie la validation des extremites de cables par cables_href."""

    def test_extremite_liee_a_jonction(self) -> None:
        """Un cable reference dans cables_href de jonctions est conforme."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        jonction_depart = _construire_noeud("J1", [0.0, 0.0], cables_href=["C1"])
        jonction_arrivee = _construire_noeud("J2", [10.0, 0.0], cables_href=["C1"])
        collections_noeuds = {
            "RPD_Jonction_Reco.geojson": [jonction_depart, jonction_arrivee]
        }

        resultats = controler_extremites([cable], collections_noeuds)

        assert len(resultats) == 1
        assert resultats[0]["extremite_depart"]["lien_valide"] is True
        assert resultats[0]["extremite_arrivee"]["lien_valide"] is True

    def test_extremite_isolee(self) -> None:
        """Un cable non reference par aucun noeud est non valide."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])

        resultats = controler_extremites([cable], {})

        assert len(resultats) == 1
        assert resultats[0]["extremite_depart"]["lien_valide"] is False
        assert resultats[0]["extremite_arrivee"]["lien_valide"] is False

    def test_lien_par_cables_href_sans_proximite(self) -> None:
        """Un noeud eloigne referencant le cable valide l'extremite."""
        cable = _construire_cable("C1", [[0.0, 0.0], [100.0, 0.0]])
        # Noeud tres eloigne geometriquement mais referencant le cable
        noeud = _construire_noeud("N1", [999.0, 999.0], cables_href="C1")
        collections = {"RPD_Jonction_Reco.geojson": [noeud]}

        resultats = controler_extremites([cable], collections)

        assert resultats[0]["extremite_depart"]["lien_valide"] is True
        assert resultats[0]["extremite_arrivee"]["lien_valide"] is True

    def test_coupe_circuit_a_fusibles_valide(self) -> None:
        """Un cable reference par un coupe-circuit a fusibles est conforme."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        ccf = _construire_noeud("CCF1", [50.0, 50.0], cables_href="C1")
        collections = {"RPD_CoupeCircuitAFusibles_Reco.geojson": [ccf]}

        resultats = controler_extremites([cable], collections)

        assert resultats[0]["extremite_depart"]["lien_valide"] is True

    def test_point_de_comptage_valide(self) -> None:
        """Un cable reference par un point de comptage est conforme."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        pdc = _construire_noeud("PDC1", [50.0, 50.0], cables_href="C1")
        collections = {"RPD_PointDeComptage_Reco.geojson": [pdc]}

        resultats = controler_extremites([cable], collections)

        assert resultats[0]["extremite_depart"]["lien_valide"] is True

    def test_poste_electrique_valide(self) -> None:
        """Un poste referencant le cable valide l'extremite."""
        cable = _construire_cable("C1", [[0.0, 0.0], [100.0, 0.0]])
        poste = _construire_noeud("P1", [50.0, 50.0], cables_href="C1")
        collections = {"RPD_PosteElectrique_Reco.geojson": [poste]}

        resultats = controler_extremites([cable], collections)

        assert resultats[0]["extremite_depart"]["lien_valide"] is True
        assert resultats[0]["extremite_arrivee"]["lien_valide"] is True

    def test_poste_sans_reference_cable_ne_valide_pas(self) -> None:
        """Un poste qui ne reference pas le cable ne valide pas l'extremite."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        poste = _construire_noeud("P1", [0.0, 0.0], cables_href="AUTRE")
        collections = {"RPD_PosteElectrique_Reco.geojson": [poste]}

        resultats = controler_extremites([cable], collections)

        assert resultats[0]["extremite_depart"]["lien_valide"] is False

    def test_cables_href_csv(self) -> None:
        """Un noeud avec cables_href en CSV valide les cables references."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        noeud = _construire_noeud("N1", [5.0, 5.0], cables_href="C1,C2,C3")
        collections = {"RPD_Jonction_Reco.geojson": [noeud]}

        resultats = controler_extremites([cable], collections)

        assert resultats[0]["extremite_depart"]["lien_valide"] is True

    def test_entite_liee_type_correct(self) -> None:
        """L'entite liee porte le bon type et identifiant."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        noeud = _construire_noeud("J1", [3.0, 4.0], cables_href="C1")
        collections = {"RPD_Jonction_Reco.geojson": [noeud]}

        resultats = controler_extremites([cable], collections)

        entites = resultats[0]["extremite_depart"]["entites_liees"]
        assert len(entites) == 1
        assert entites[0]["type"] == "Jonction"
        assert entites[0]["id"] == "J1"
        assert "distance" not in entites[0]

    def test_domaine_tension_propage(self) -> None:
        """Le domaine de tension est propage dans l'entite liee."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        noeud = _construire_noeud(
            "J1", [0.0, 0.0], cables_href="C1", domaine_tension="BT"
        )
        collections = {"RPD_Jonction_Reco.geojson": [noeud]}

        resultats = controler_extremites([cable], collections)

        entites = resultats[0]["extremite_depart"]["entites_liees"]
        assert entites[0]["domaine_tension"] == "BT"

    def test_jonction_et_poste_combines(self) -> None:
        """Jonction et poste referencant le meme cable apparaissent tous les deux."""
        cable = _construire_cable("C1", [[0.0, 0.0], [100.0, 0.0]])
        jonction = _construire_noeud("J1", [0.0, 0.0], cables_href="C1")
        poste = _construire_noeud("P1", [200.0, 200.0], cables_href="C1")
        collections = {
            "RPD_Jonction_Reco.geojson": [jonction],
            "RPD_PosteElectrique_Reco.geojson": [poste],
        }

        resultats = controler_extremites([cable], collections)

        assert resultats[0]["extremite_depart"]["lien_valide"] is True
        assert resultats[0]["extremite_arrivee"]["lien_valide"] is True
        # Les deux entites sont presentes
        entites = resultats[0]["extremite_depart"]["entites_liees"]
        types = {e["type"] for e in entites}
        assert "Jonction" in types
        assert "PosteElectrique" in types

    def test_types_noeuds_multiples(self) -> None:
        """Differents types de noeuds peuvent valider un meme cable."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        ccf = _construire_noeud("CCF1", [0.0, 0.0], cables_href="C1")
        pdc = _construire_noeud("PDC1", [10.0, 0.0], cables_href="C1")
        collections = {
            "RPD_CoupeCircuitAFusibles_Reco.geojson": [ccf],
            "RPD_PointDeComptage_Reco.geojson": [pdc],
        }

        resultats = controler_extremites([cable], collections)

        assert resultats[0]["extremite_depart"]["lien_valide"] is True
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
        poste = _construire_noeud("P1", [50.0, 50.0], cables_href="C1")

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

    def test_cli_avec_coupe_circuit_a_fusibles(self, tmp_path: Any) -> None:
        """Le CLI charge et utilise les coupe-circuits a fusibles."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        ccf = _construire_noeud("CCF1", [50.0, 50.0], cables_href="C1")

        for nom, donnees in [
            (
                "RPD_CableElectrique_Reco.geojson",
                {"type": "FeatureCollection", "features": [cable]},
            ),
            (
                "RPD_CoupeCircuitAFusibles_Reco.geojson",
                {"type": "FeatureCollection", "features": [ccf]},
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

        assert rapport["cables_conformes"] == 1
        assert rapport["cables_non_conformes"] == 0
