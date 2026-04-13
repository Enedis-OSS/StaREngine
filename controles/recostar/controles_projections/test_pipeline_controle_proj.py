"""
Tests unitaires du pipeline de controle des projections (pipeline_controle_proj).

Couvre les cas nominaux et les cas limites :
- execution du pipeline complet sur repertoire vide
- execution sur donnees conformes (aucune anomalie)
- execution sur donnees avec anomalies
- gestion du repertoire introuvable
- sortie par defaut et personnalisee
- generation du rapport PDF via le pipeline
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from pipeline_controle_proj import NOMS_CONTROLES, executer_pipeline
from rapport_pdf_proj import FICHIER_RAPPORT

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _creer_geojson_conforme(
    repertoire: str,
    nom: str,
    code_epsg: int = 2154,
    coords: list[float] | None = None,
) -> str:
    """Cree un fichier GeoJSON conforme dans le repertoire."""
    if coords is None:
        coords = [850000.0, 6800000.0, 100.0]
    contenu: dict[str, Any] = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": f"urn:ogc:def:crs:EPSG::{code_epsg}",
            },
        },
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "e1"},
                "geometry": {"type": "Point", "coordinates": coords},
            },
        ],
    }
    chemin = os.path.join(repertoire, nom)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(contenu, f, ensure_ascii=False)
    return chemin


def _creer_geojson_non_conforme(
    repertoire: str,
    nom: str,
    code_epsg: int = 9999,
) -> str:
    """Cree un fichier GeoJSON avec un CRS non conforme."""
    contenu: dict[str, Any] = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": f"urn:ogc:def:crs:EPSG::{code_epsg}",
            },
        },
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "ko1"},
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0, 0.0]},
            },
        ],
    }
    chemin = os.path.join(repertoire, nom)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(contenu, f, ensure_ascii=False)
    return chemin


# --------------------------------------------------------------------------- #
# Tests executer_pipeline
# --------------------------------------------------------------------------- #


class TestExecuterPipeline:
    """Tests de l'execution du pipeline complet."""

    def test_repertoire_introuvable(self) -> None:
        resultat = executer_pipeline("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 0
        assert "controles" in resultat
        assert "rapport" in resultat

    def test_donnees_conformes(self, tmp_path: Any) -> None:
        dossier_sortie = os.path.join(str(tmp_path), "sortie")
        _creer_geojson_conforme(str(tmp_path), "RPD_Test.geojson")
        resultat = executer_pipeline(str(tmp_path), dossier_sortie)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 0

    def test_donnees_non_conformes(self, tmp_path: Any) -> None:
        _creer_geojson_non_conforme(str(tmp_path), "RPD_Bad.geojson")
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] > 0

    def test_structure_resultat(self, tmp_path: Any) -> None:
        _creer_geojson_conforme(str(tmp_path), "RPD_Test.geojson")
        resultat = executer_pipeline(str(tmp_path))
        assert "succes" in resultat
        assert "controles" in resultat
        assert "rapport" in resultat
        assert "nombre_anomalies_total" in resultat

    def test_tous_controles_presents(self, tmp_path: Any) -> None:
        _creer_geojson_conforme(str(tmp_path), "RPD_Test.geojson")
        resultat = executer_pipeline(str(tmp_path))
        controles = resultat["controles"]
        for nom in NOMS_CONTROLES:
            assert nom in controles
            assert controles[nom]["succes"] is True

    def test_rapport_pdf_genere(self, tmp_path: Any) -> None:
        _creer_geojson_conforme(str(tmp_path), "RPD_Test.geojson")
        executer_pipeline(str(tmp_path))
        chemin_pdf = os.path.join(str(tmp_path), FICHIER_RAPPORT)
        assert os.path.isfile(chemin_pdf)

    def test_sortie_personnalisee(self, tmp_path: Any) -> None:
        _creer_geojson_conforme(str(tmp_path), "RPD_Test.geojson")
        dossier_sortie = os.path.join(str(tmp_path), "output")
        resultat = executer_pipeline(str(tmp_path), dossier_sortie)
        assert resultat["succes"] is True
        chemin_pdf = os.path.join(dossier_sortie, FICHIER_RAPPORT)
        assert os.path.isfile(chemin_pdf)

    def test_sortie_par_defaut(self, tmp_path: Any) -> None:
        _creer_geojson_conforme(str(tmp_path), "RPD_Test.geojson")
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        chemin_pdf = os.path.join(str(tmp_path), FICHIER_RAPPORT)
        assert os.path.isfile(chemin_pdf)

    def test_fichiers_ecarts_generes(self, tmp_path: Any) -> None:
        _creer_geojson_non_conforme(str(tmp_path), "RPD_Bad.geojson")
        executer_pipeline(str(tmp_path))
        assert os.path.isfile(os.path.join(str(tmp_path), "ecarts_proj.geojson"))

    def test_pdf_lisible(self, tmp_path: Any) -> None:
        """Le fichier PDF genere doit commencer par l'en-tete PDF."""
        _creer_geojson_conforme(str(tmp_path), "RPD_Test.geojson")
        executer_pipeline(str(tmp_path))
        chemin_pdf = os.path.join(str(tmp_path), FICHIER_RAPPORT)
        with open(chemin_pdf, "rb") as f:
            en_tete = f.read(5)
        assert en_tete == b"%PDF-"

    def test_plusieurs_fichiers_mixtes(self, tmp_path: Any) -> None:
        _creer_geojson_conforme(str(tmp_path), "RPD_Ok.geojson")
        _creer_geojson_non_conforme(str(tmp_path), "RPD_Bad.geojson")
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] > 0

    def test_chaque_controle_a_succes(self, tmp_path: Any) -> None:
        """Chaque controle individuel doit renvoyer succes avec des donnees."""
        _creer_geojson_conforme(str(tmp_path), "RPD_Test.geojson")
        dossier_sortie = os.path.join(str(tmp_path), "sortie")
        resultat = executer_pipeline(str(tmp_path), dossier_sortie)
        for nom, r in resultat["controles"].items():
            assert r["succes"] is True, f"Echec pour {nom}"

    def test_rapport_contient_chemin_pdf(self, tmp_path: Any) -> None:
        resultat = executer_pipeline(str(tmp_path))
        assert "chemin_pdf" in resultat["rapport"]
        assert resultat["rapport"]["chemin_pdf"].endswith(FICHIER_RAPPORT)


# --------------------------------------------------------------------------- #
# Tests configuration
# --------------------------------------------------------------------------- #


class TestConfigurationPipeline:
    """Tests de la configuration du pipeline."""

    def test_nombre_controles(self) -> None:
        assert len(NOMS_CONTROLES) == 3

    def test_noms_controles(self) -> None:
        assert "controle_proj" in NOMS_CONTROLES
        assert "controle_proj_ensemble" in NOMS_CONTROLES
        assert "controle_proj_coordonnees" in NOMS_CONTROLES
