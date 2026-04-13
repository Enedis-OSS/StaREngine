"""
Tests unitaires du script de generation du rapport PDF des controles des noeuds.

Couvre les cas nominaux et les cas limites :
- collecte des resultats depuis les fichiers d'ecarts
- generation du PDF avec contenu
- generation du PDF sans fichier d'ecarts
- execution CLI avec repertoire de sortie
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from rapport_pdf_noeud import (
    CONTROLES,
    collecter_resultats_controles,
    executer_rapport_cli,
    generer_rapport_pdf,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _creer_geojson_ecarts(
    features: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construit un GeoJSON FeatureCollection minimal."""
    return {"type": "FeatureCollection", "features": features}


def _feature_geometrie(identifiant: str) -> dict[str, Any]:
    """Feature d'ecart geometrique minimale."""
    return {
        "type": "Feature",
        "properties": {
            "id_cable": identifiant,
            "erreur": "geometrie absente",
            "type_anomalie": "geometrie_invalide",
            "priorite": "bloquant",
        },
        "geometry": None,
    }


def _feature_extremite(identifiant: str) -> dict[str, Any]:
    """Feature d'ecart extremite minimale."""
    return {
        "type": "Feature",
        "properties": {
            "id_cable": identifiant,
            "extremite": "extremite_depart",
            "type_anomalie": "extremite_non_liee",
            "priorite": "bloquant",
        },
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
    }


# --------------------------------------------------------------------------- #
# Tests de collecte des resultats
# --------------------------------------------------------------------------- #


class TestCollecterResultatsControles:
    """Verifie la collecte des resultats depuis les fichiers d'ecarts."""

    def test_aucun_fichier_present(self, tmp_path: Any) -> None:
        """Tous les controles sont marques comme non disponibles."""
        resultats = collecter_resultats_controles(str(tmp_path))

        assert len(resultats) == len(CONTROLES)
        for resultat in resultats:
            assert resultat["disponible"] is False
            assert resultat["nombre_anomalies"] == 0

    def test_fichier_avec_anomalies(self, tmp_path: Any) -> None:
        """Les anomalies sont correctement comptees."""
        geojson = _creer_geojson_ecarts([_feature_geometrie("C1")])
        chemin = os.path.join(str(tmp_path), "ecarts_geometrie.geojson")
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(geojson, f)

        resultats = collecter_resultats_controles(str(tmp_path))

        resultat_geo = next(
            r for r in resultats if r["fichier"] == "ecarts_geometrie.geojson"
        )
        assert resultat_geo["disponible"] is True
        assert resultat_geo["nombre_anomalies"] == 1

    def test_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        """Un fichier vide est disponible mais avec 0 anomalies."""
        geojson = _creer_geojson_ecarts([])
        chemin = os.path.join(str(tmp_path), "ecarts_extremites.geojson")
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(geojson, f)

        resultats = collecter_resultats_controles(str(tmp_path))

        resultat_ext = next(
            r for r in resultats if r["fichier"] == "ecarts_extremites.geojson"
        )
        assert resultat_ext["disponible"] is True
        assert resultat_ext["nombre_anomalies"] == 0


# --------------------------------------------------------------------------- #
# Tests de generation du PDF
# --------------------------------------------------------------------------- #


class TestGenererRapportPdf:
    """Verifie la generation du rapport PDF."""

    def test_generation_pdf_avec_ecarts(self, tmp_path: Any) -> None:
        """Le PDF est genere avec des anomalies presentes."""
        geojson = _creer_geojson_ecarts(
            [_feature_geometrie("C1"), _feature_extremite("C2")]
        )
        chemin_geo = os.path.join(str(tmp_path), "ecarts_geometrie.geojson")
        chemin_ext = os.path.join(str(tmp_path), "ecarts_extremites.geojson")
        for chemin in (chemin_geo, chemin_ext):
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump(geojson, f)

        chemin_pdf = os.path.join(str(tmp_path), "rapport.pdf")
        resultat = generer_rapport_pdf(str(tmp_path), chemin_pdf)

        assert resultat["succes"] is True
        assert os.path.isfile(chemin_pdf)
        assert resultat["nombre_total_anomalies"] == 4
        assert resultat["controles_disponibles"] == 2

    def test_generation_pdf_sans_ecarts(self, tmp_path: Any) -> None:
        """Le PDF est genere meme sans fichier d'ecarts."""
        chemin_pdf = os.path.join(str(tmp_path), "rapport.pdf")
        resultat = generer_rapport_pdf(str(tmp_path), chemin_pdf)

        assert resultat["succes"] is True
        assert os.path.isfile(chemin_pdf)
        assert resultat["nombre_total_anomalies"] == 0
        assert resultat["controles_disponibles"] == 0


# --------------------------------------------------------------------------- #
# Tests CLI
# --------------------------------------------------------------------------- #


class TestExecuterRapportCli:
    """Verifie l'execution CLI du rapport PDF."""

    def test_cli_repertoire_inexistant(self) -> None:
        """Un repertoire inexistant retourne une erreur."""
        resultat = executer_rapport_cli("/chemin/inexistant")
        assert resultat["succes"] is False

    def test_cli_sortie_separee(self, tmp_path: Any) -> None:
        """Le PDF est genere dans le repertoire de sortie specifie."""
        repertoire_entree = os.path.join(str(tmp_path), "entree")
        repertoire_sortie = os.path.join(str(tmp_path), "sortie")
        os.makedirs(repertoire_entree)

        geojson = _creer_geojson_ecarts([_feature_geometrie("C1")])
        chemin = os.path.join(repertoire_entree, "ecarts_geometrie.geojson")
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(geojson, f)

        resultat = executer_rapport_cli(repertoire_entree, repertoire_sortie)

        assert resultat["succes"] is True
        assert os.path.isfile(
            os.path.join(repertoire_sortie, "rapport_controles_noeud.pdf")
        )

    def test_cli_sortie_par_defaut(self, tmp_path: Any) -> None:
        """Sans sortie specifiee, le PDF est cree dans le repertoire d'entree."""
        resultat = executer_rapport_cli(str(tmp_path))

        assert resultat["succes"] is True
        assert os.path.isfile(
            os.path.join(str(tmp_path), "rapport_controles_noeud.pdf")
        )
