"""
Tests unitaires du controle de geometrie des cables.

Couvre les cas nominaux et les cas limites :
- construction du GeoJSON d'ecarts avec le champ priorite
- cable avec geometrie valide
- cable sans geometrie ou geometrie invalide
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_geometrie import (
    construire_geojson_ecarts,
    construire_rapport_json,
    controler_geometrie,
    executer_controle_cli,
    valider_geometrie_cable,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #

PRIORITE_ATTENDUE: str = "bloquant"


def _construire_cable(
    identifiant: str,
    coordonnees: list[list[float]] | None = None,
    type_geometrie: str = "LineString",
) -> dict[str, Any]:
    """Construit une feature cable avec geometrie parametrable pour les tests."""
    props: dict[str, Any] = {"id": identifiant}
    if coordonnees is None:
        return {"type": "Feature", "properties": props, "geometry": None}
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": type_geometrie, "coordinates": coordonnees},
    }


# --------------------------------------------------------------------------- #
# Tests du champ priorite dans le GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestPrioriteGeojsonEcarts:
    """Verifie la presence du champ priorite dans chaque feature d'ecart."""

    def test_priorite_geometrie_absente(self) -> None:
        """Un cable sans geometrie doit avoir priorite bloquant dans le geojson."""
        cable = _construire_cable("C1")
        resultats = [{"id_cable": "C1", "valide": False, "erreur": "Geometrie absente"}]

        geojson = construire_geojson_ecarts(resultats, [cable])
        features = geojson["features"]

        assert len(features) == 1
        assert features[0]["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_priorite_type_geometrie_invalide(self) -> None:
        """Un cable avec type geometrie incorrect a priorite bloquant."""
        cable = _construire_cable("C2", [[0.0, 0.0]], type_geometrie="Point")
        resultats = [
            {
                "id_cable": "C2",
                "valide": False,
                "erreur": "Geometrie invalide (type Point, attendu LineString)",
            }
        ]

        geojson = construire_geojson_ecarts(resultats, [cable])
        features = geojson["features"]

        assert len(features) == 1
        assert features[0]["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_aucune_feature_si_tout_valide(self) -> None:
        """Aucune feature si tous les cables ont une geometrie valide."""
        resultats = [{"id_cable": "C1", "valide": True}]
        geojson = construire_geojson_ecarts(resultats, [])
        assert geojson["features"] == []

    def test_crs_propage_si_present(self) -> None:
        """Le CRS est propage dans le FeatureCollection de sortie."""
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], [], crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        """Aucun champ crs si non fourni."""
        geojson = construire_geojson_ecarts([], [])
        assert "crs" not in geojson


# --------------------------------------------------------------------------- #
# Tests de la validation de geometrie
# --------------------------------------------------------------------------- #


class TestValiderGeometrieCable:
    """Verifie la validation d'un cable individuel."""

    def test_cable_valide(self) -> None:
        """Un cable LineString avec 2+ points est valide."""
        cable = _construire_cable("C1", [[0.0, 0.0], [1.0, 1.0]])
        resultat = valider_geometrie_cable(cable)
        assert resultat["valide"] is True

    def test_cable_sans_geometrie(self) -> None:
        """Un cable sans geometrie est invalide."""
        cable = _construire_cable("C1")
        resultat = valider_geometrie_cable(cable)
        assert resultat["valide"] is False

    def test_cable_un_seul_point(self) -> None:
        """Un cable avec un seul point est invalide."""
        cable = _construire_cable("C1", [[0.0, 0.0]])
        resultat = valider_geometrie_cable(cable)
        assert resultat["valide"] is False

    def test_cable_mauvais_type(self) -> None:
        """Un cable avec un type Point est invalide."""
        cable = _construire_cable("C1", [[0.0, 0.0]], type_geometrie="Point")
        resultat = valider_geometrie_cable(cable)
        assert resultat["valide"] is False

    def test_cable_sans_id(self) -> None:
        """Un cable sans identifiant est invalide."""
        cable = {"type": "Feature", "properties": {}, "geometry": None}
        resultat = valider_geometrie_cable(cable)
        assert resultat["valide"] is False
        assert resultat["id_cable"] == "inconnu"


# --------------------------------------------------------------------------- #
# Tests du rapport JSON
# --------------------------------------------------------------------------- #


class TestConstruireRapportJson:
    """Verifie la structure du rapport JSON."""

    def test_rapport_avec_erreurs(self) -> None:
        """Le rapport compte les cables conformes et non conformes."""
        resultats = [
            {"id_cable": "C1", "valide": True},
            {"id_cable": "C2", "valide": False, "erreur": "Geometrie absente"},
        ]
        rapport = construire_rapport_json(resultats)
        assert rapport["cables_conformes"] == 1
        assert rapport["cables_non_conformes"] == 1
        assert rapport["nombre_cables"] == 2


# --------------------------------------------------------------------------- #
# Test CLI bout en bout
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Verifie l'execution CLI avec ecriture des fichiers de sortie."""

    def test_cli_genere_fichiers_avec_priorite(self, tmp_path: Any) -> None:
        """Le GeoJSON de sortie contient le champ priorite sur chaque feature."""
        cable_invalide = _construire_cable("C1")
        cables = {"type": "FeatureCollection", "features": [cable_invalide]}

        chemin_cables = os.path.join(str(tmp_path), "RPD_CableElectrique_Reco.geojson")
        with open(chemin_cables, "w", encoding="utf-8") as f:
            json.dump(cables, f)

        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        chemin_ecarts = resultat["ecarts"]
        with open(chemin_ecarts, "r", encoding="utf-8") as f:
            geojson = json.load(f)

        assert len(geojson["features"]) >= 1
        for feature in geojson["features"]:
            assert feature["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_cli_fichier_manquant(self, tmp_path: Any) -> None:
        """L'absence du fichier source retourne une erreur."""
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
