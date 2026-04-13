"""
Tests unitaires du controle de domaine de tension.

Couvre les cas nominaux et les cas limites :
- construction du GeoJSON d'ecarts avec le champ priorite
- detection d'incoherences de tension cable/jonction
- absence d'incoherence quand les tensions correspondent
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_domaine_tension import (
    construire_geojson_ecarts,
    construire_rapport_json,
    controler_domaine_tension,
    executer_controle_cli,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #

PRIORITE_ATTENDUE: str = "bloquant"


def _construire_cable(
    identifiant: str,
    coordonnees: list[list[float]],
    domaine_tension: str | None = None,
) -> dict[str, Any]:
    """Construit une feature cable electrique minimale pour les tests."""
    props: dict[str, Any] = {"id": identifiant}
    if domaine_tension is not None:
        props["DomaineTension"] = domaine_tension
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


def _construire_jonction(
    identifiant: str,
    coordonnees: list[float],
    cables_href: list[str] | None = None,
    domaine_tension: str | None = None,
) -> dict[str, Any]:
    """Construit une feature jonction minimale pour les tests."""
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
# Tests du champ priorite dans le GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestPrioriteGeojsonEcarts:
    """Verifie la presence du champ priorite dans chaque feature d'ecart."""

    def test_priorite_incoherence_tension(self) -> None:
        """Chaque incoherence de tension doit avoir priorite bloquant."""
        resultats = [
            {
                "id_cable": "C1",
                "problemes": [
                    {
                        "id_jonction": "J1",
                        "tension_cable": "BT",
                        "tension_jonction": "HTA",
                    }
                ],
            }
        ]
        geojson = construire_geojson_ecarts(resultats)
        features = geojson["features"]

        assert len(features) == 1
        assert features[0]["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_priorite_plusieurs_problemes(self) -> None:
        """Plusieurs incoherences pour un cable : chaque feature a la priorite."""
        resultats = [
            {
                "id_cable": "C1",
                "problemes": [
                    {
                        "id_jonction": "J1",
                        "tension_cable": "BT",
                        "tension_jonction": "HTA",
                    },
                    {
                        "id_jonction": "J2",
                        "tension_cable": "BT",
                        "tension_jonction": "HTB",
                    },
                ],
            }
        ]
        geojson = construire_geojson_ecarts(resultats)

        assert len(geojson["features"]) == 2
        for feature in geojson["features"]:
            assert feature["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_aucune_feature_si_aucun_resultat(self) -> None:
        """Aucune feature si aucune incoherence."""
        geojson = construire_geojson_ecarts([])
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


class TestControlerDomaineTension:
    """Verifie la detection des incoherences de tension."""

    def test_pas_d_incoherence_si_tensions_identiques(self) -> None:
        """Aucune incoherence si cable et jonction ont la meme tension."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]], domaine_tension="BT")
        jonction = _construire_jonction(
            "J1", [0.0, 0.0], cables_href=["C1"], domaine_tension="BT"
        )

        resultats = controler_domaine_tension([cable], [jonction])
        assert len(resultats) == 0

    def test_incoherence_si_tensions_differentes(self) -> None:
        """Incoherence detectee si cable et jonction ont des tensions differentes."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]], domaine_tension="BT")
        jonction = _construire_jonction(
            "J1", [0.0, 0.0], cables_href=["C1"], domaine_tension="HTA"
        )

        resultats = controler_domaine_tension([cable], [jonction])
        assert len(resultats) == 1
        assert resultats[0]["id_cable"] == "C1"

    def test_cable_sans_tension_ignore(self) -> None:
        """Un cable sans DomaineTension ne genere pas d'incoherence."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
        jonction = _construire_jonction(
            "J1", [0.0, 0.0], cables_href=["C1"], domaine_tension="BT"
        )

        resultats = controler_domaine_tension([cable], [jonction])
        assert len(resultats) == 0


# --------------------------------------------------------------------------- #
# Tests du rapport JSON
# --------------------------------------------------------------------------- #


class TestConstruireRapportJson:
    """Verifie la structure du rapport JSON."""

    def test_rapport_avec_incoherences(self) -> None:
        """Le rapport contient le nombre d'incoherences."""
        rapport = construire_rapport_json([{"id_cable": "C1"}], 5)
        assert rapport["nombre_incoherences"] == 1
        assert rapport["nombre_cables"] == 5

    def test_rapport_sans_incoherence(self) -> None:
        """Le rapport indique zero incoherence."""
        rapport = construire_rapport_json([], 3)
        assert rapport["nombre_incoherences"] == 0


# --------------------------------------------------------------------------- #
# Test CLI bout en bout
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Verifie l'execution CLI avec ecriture des fichiers de sortie."""

    def test_cli_genere_fichiers_avec_priorite(self, tmp_path: Any) -> None:
        """Le GeoJSON de sortie contient le champ priorite sur chaque feature."""
        cable = _construire_cable("C1", [[0.0, 0.0], [10.0, 0.0]], domaine_tension="BT")
        jonction = _construire_jonction(
            "J1", [0.0, 0.0], cables_href=["C1"], domaine_tension="HTA"
        )

        cables = {"type": "FeatureCollection", "features": [cable]}
        jonctions = {"type": "FeatureCollection", "features": [jonction]}

        chemin_cables = os.path.join(str(tmp_path), "RPD_CableElectrique_Reco.geojson")
        chemin_jonctions = os.path.join(str(tmp_path), "RPD_Jonction_Reco.geojson")
        for chemin, donnees in [(chemin_cables, cables), (chemin_jonctions, jonctions)]:
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump(donnees, f)

        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        chemin_ecarts = resultat["ecarts"]
        with open(chemin_ecarts, "r", encoding="utf-8") as f:
            geojson = json.load(f)

        for feature in geojson["features"]:
            assert feature["properties"]["priorite"] == PRIORITE_ATTENDUE
