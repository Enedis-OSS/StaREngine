"""
Tests unitaires du controle de coherence terre.

Couvre les cas nominaux et les cas limites :
- construction du GeoJSON d'ecarts avec le champ priorite
- noeud terre sans cable terre
- cable terre sans noeud terre
- absence de donnees (0 cable, 0 noeud)
- exclusion des noeuds de nature TerreMasses
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_coherence_terre import (
    construire_geojson_ecarts,
    construire_rapport_json,
    controler_coherence_terre,
    executer_controle_cli,
    extraire_ids_cables_href,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #

PRIORITE_ATTENDUE: str = "bloquant"


def _construire_noeud_terre(
    identifiant: str,
    coordonnees: list[float],
    cables_href: list[str] | str | None = None,
    nature_terre_href: str | None = None,
) -> dict[str, Any]:
    """Construit une feature noeud terre minimale pour les tests."""
    props: dict[str, Any] = {"id": identifiant}
    if cables_href is not None:
        props["cables_href"] = cables_href
    if nature_terre_href is not None:
        props["NatureTerre_href"] = nature_terre_href
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": coordonnees},
    }


def _construire_cable_terre(
    identifiant: str, coordonnees: list[list[float]]
) -> dict[str, Any]:
    """Construit une feature cable terre minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


# --------------------------------------------------------------------------- #
# Tests du champ priorite dans le GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestPrioriteGeojsonEcarts:
    """Verifie la presence du champ priorite dans chaque feature d'ecart."""

    def test_priorite_noeud_sans_cable(self) -> None:
        """Un noeud terre sans cable terre doit avoir priorite bloquant."""
        anomalies = [
            {
                "id_noeud": "N1",
                "type": "noeud_terre_sans_cable_terre",
                "message": "Le noeud terre N1 n'est lie a aucun cable terre",
                "coordonnees": [1.0, 2.0, 3.0],
                "cables_href": [],
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        features = geojson["features"]

        assert len(features) == 1
        assert features[0]["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_priorite_cable_sans_noeud(self) -> None:
        """Un cable terre sans noeud doit avoir priorite bloquant sur chaque extremite."""
        anomalies = [
            {
                "id_cable": "C1",
                "type": "cable_terre_sans_noeud_terre",
                "message": "Le cable terre C1 n'est lie a aucun noeud terre",
                "extremites": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        features = geojson["features"]

        assert len(features) == 2
        for feature in features:
            assert feature["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_priorite_absente_si_aucune_anomalie(self) -> None:
        """Aucune feature si aucune anomalie : le geojson reste vide."""
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


class TestControlerCoherenceTerre:
    """Verifie la detection des anomalies de coherence terre."""

    def test_aucune_anomalie_si_vide(self) -> None:
        """Aucune anomalie quand il n'y a ni cable ni noeud."""
        anomalies, nombre_exclus = controler_coherence_terre([], [])
        assert anomalies == []
        assert nombre_exclus == 0

    def test_noeud_lie_a_cable_pas_d_anomalie(self) -> None:
        """Un noeud proche d'un cable qu'il reference ne genere pas d'anomalie."""
        cable = _construire_cable_terre("C1", [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
        noeud = _construire_noeud_terre("N1", [0.0, 0.0, 0.0], cables_href=["C1"])

        anomalies, nombre_exclus = controler_coherence_terre([cable], [noeud])
        assert len(anomalies) == 0
        assert nombre_exclus == 0

    def test_noeud_sans_cable_reference(self) -> None:
        """Un noeud sans cables_href genere une anomalie."""
        cable = _construire_cable_terre("C1", [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
        noeud = _construire_noeud_terre("N1", [0.0, 0.0, 0.0])

        anomalies, _ = controler_coherence_terre([cable], [noeud])
        noeud_anomalies = [
            a for a in anomalies if a["type"] == "noeud_terre_sans_cable_terre"
        ]
        assert len(noeud_anomalies) >= 1

    def test_cable_sans_noeud_proche(self) -> None:
        """Un cable sans noeud a proximite genere une anomalie."""
        cable = _construire_cable_terre("C1", [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
        noeud = _construire_noeud_terre("N1", [999.0, 999.0, 0.0], cables_href=["C1"])

        anomalies, _ = controler_coherence_terre([cable], [noeud])
        cable_anomalies = [
            a for a in anomalies if a["type"] == "cable_terre_sans_noeud_terre"
        ]
        assert len(cable_anomalies) >= 1


# --------------------------------------------------------------------------- #
# Tests de l'exclusion des noeuds TerreMasses
# --------------------------------------------------------------------------- #


class TestExclusionTerreMasses:
    """Verifie que les noeuds de nature TerreMasses sont exclus du controle."""

    def test_noeud_terre_masses_exclu_du_controle(self) -> None:
        """Un noeud TerreMasses sans cable ne genere pas d'anomalie."""
        noeud_tm = _construire_noeud_terre(
            "N1", [0.0, 0.0, 0.0], nature_terre_href="TerreMasses"
        )

        anomalies, nombre_exclus = controler_coherence_terre([], [noeud_tm])
        assert anomalies == []
        assert nombre_exclus == 1

    def test_noeud_normal_non_exclu(self) -> None:
        """Un noeud sans NatureTerre_href TerreMasses est controle normalement."""
        cable = _construire_cable_terre("C1", [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
        noeud = _construire_noeud_terre(
            "N1", [0.0, 0.0, 0.0], nature_terre_href="AutreNature"
        )

        anomalies, nombre_exclus = controler_coherence_terre([cable], [noeud])
        noeud_anomalies = [
            a for a in anomalies if a["type"] == "noeud_terre_sans_cable_terre"
        ]
        assert len(noeud_anomalies) >= 1
        assert nombre_exclus == 0

    def test_melange_terre_masses_et_normal(self) -> None:
        """Seul le noeud TerreMasses est exclu, l'autre est controle."""
        cable = _construire_cable_terre("C1", [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
        noeud_normal = _construire_noeud_terre(
            "N1", [0.0, 0.0, 0.0], cables_href=["C1"]
        )
        noeud_tm = _construire_noeud_terre(
            "N2", [50.0, 50.0, 0.0], nature_terre_href="TerreMasses"
        )

        anomalies, nombre_exclus = controler_coherence_terre(
            [cable], [noeud_normal, noeud_tm]
        )
        assert nombre_exclus == 1
        # Le noeud normal est conforme, pas d'anomalie cote noeud
        noeud_anomalies = [
            a for a in anomalies if a["type"] == "noeud_terre_sans_cable_terre"
        ]
        assert len(noeud_anomalies) == 0

    def test_cable_lie_a_terre_masses_reste_valide(self) -> None:
        """Un cable lie a un noeud TerreMasses est toujours considere valide."""
        cable = _construire_cable_terre("C1", [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
        noeud_tm = _construire_noeud_terre(
            "N1",
            [0.0, 0.0, 0.0],
            cables_href=["C1"],
            nature_terre_href="TerreMasses",
        )

        anomalies, nombre_exclus = controler_coherence_terre([cable], [noeud_tm])
        cable_anomalies = [
            a for a in anomalies if a["type"] == "cable_terre_sans_noeud_terre"
        ]
        assert len(cable_anomalies) == 0
        assert nombre_exclus == 1

    def test_terre_masses_sans_nature_href_non_exclu(self) -> None:
        """Un noeud sans NatureTerre_href n'est pas exclu."""
        noeud = _construire_noeud_terre("N1", [0.0, 0.0, 0.0])

        _, nombre_exclus = controler_coherence_terre([], [noeud])
        assert nombre_exclus == 0


# --------------------------------------------------------------------------- #
# Tests du rapport JSON
# --------------------------------------------------------------------------- #


class TestConstruireRapportJson:
    """Verifie la structure du rapport JSON."""

    def test_rapport_bloquant_avec_anomalies(self) -> None:
        """Le rapport est bloquant des qu'il y a au moins une anomalie."""
        rapport = construire_rapport_json([{"type": "test"}], 1, 1)
        assert rapport["bloquant"] is True
        assert rapport["nombre_anomalies"] == 1

    def test_rapport_non_bloquant_sans_anomalie(self) -> None:
        """Le rapport n'est pas bloquant sans anomalie."""
        rapport = construire_rapport_json([], 1, 1)
        assert rapport["bloquant"] is False

    def test_rapport_contient_nombre_exclus(self) -> None:
        """Le rapport contient le nombre de noeuds TerreMasses exclus."""
        rapport = construire_rapport_json([], 1, 3, nombre_noeuds_exclus=2)
        assert rapport["nombre_noeuds_exclus_terre_masses"] == 2

    def test_rapport_nombre_exclus_par_defaut(self) -> None:
        """Le nombre de noeuds exclus vaut 0 par defaut."""
        rapport = construire_rapport_json([], 1, 1)
        assert rapport["nombre_noeuds_exclus_terre_masses"] == 0


# --------------------------------------------------------------------------- #
# Test CLI bout en bout
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Verifie l'execution CLI avec ecriture des fichiers de sortie."""

    def test_cli_genere_fichiers_avec_priorite(self, tmp_path: Any) -> None:
        """Le GeoJSON de sortie contient le champ priorite sur chaque feature."""
        # Noeud terre isole (sans cable)
        noeuds = {
            "type": "FeatureCollection",
            "features": [_construire_noeud_terre("N1", [1.0, 2.0, 3.0])],
        }
        cables: dict[str, Any] = {"type": "FeatureCollection", "features": []}

        chemin_noeuds = os.path.join(str(tmp_path), "RPD_Terre_Reco.geojson")
        chemin_cables = os.path.join(str(tmp_path), "RPD_CableTerre_Reco.geojson")
        for chemin, donnees in [(chemin_noeuds, noeuds), (chemin_cables, cables)]:
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump(donnees, f)

        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        chemin_ecarts = resultat["ecarts"]
        with open(chemin_ecarts, "r", encoding="utf-8") as f:
            geojson = json.load(f)

        for feature in geojson["features"]:
            assert feature["properties"]["priorite"] == PRIORITE_ATTENDUE

    def test_cli_terre_masses_exclu_du_rapport(self, tmp_path: Any) -> None:
        """Le rapport CLI trace les noeuds TerreMasses exclus."""
        noeud_tm = _construire_noeud_terre(
            "N1", [0.0, 0.0, 0.0], nature_terre_href="TerreMasses"
        )
        noeuds = {"type": "FeatureCollection", "features": [noeud_tm]}
        cables: dict[str, Any] = {"type": "FeatureCollection", "features": []}

        chemin_noeuds = os.path.join(str(tmp_path), "RPD_Terre_Reco.geojson")
        chemin_cables = os.path.join(str(tmp_path), "RPD_CableTerre_Reco.geojson")
        for chemin, donnees in [(chemin_noeuds, noeuds), (chemin_cables, cables)]:
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump(donnees, f)

        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        with open(resultat["rapport"], "r", encoding="utf-8") as f:
            rapport = json.load(f)

        assert rapport["nombre_noeuds_exclus_terre_masses"] == 1
        assert rapport["nombre_anomalies"] == 0
        assert rapport["bloquant"] is False
