"""Tests du script pipeline_controle_alti.py."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import patch

import pytest

from pipeline_controle_alti import (
    NOMS_CONTROLES,
    executer_pipeline,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _creer_geojson_minimal(
    repertoire: str,
    nom: str,
    features: list[dict[str, Any]] | None = None,
) -> str:
    """Cree un fichier GeoJSON minimal dans le repertoire."""
    if features is None:
        features = []
    chemin = os.path.join(repertoire, nom)
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump({"type": "FeatureCollection", "features": features}, fichier)
    return chemin


def _resultat_succes(nb_anomalies: int = 0) -> dict[str, Any]:
    """Construit un resultat de controle reussi."""
    return {"succes": True, "nombre_anomalies": nb_anomalies, "sortie": "test.geojson"}


def _resultat_echec(erreur: str = "Erreur") -> dict[str, Any]:
    """Construit un resultat de controle en echec."""
    return {"succes": False, "erreur": erreur}


# --------------------------------------------------------------------------- #
# Tests du pipeline
# --------------------------------------------------------------------------- #


class TestPipeline:
    """Tests de l'orchestration du pipeline."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_pipeline("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    @patch("pipeline_controle_alti.executer_controle_3d")
    @patch("pipeline_controle_alti.executer_controle_z_null")
    @patch("pipeline_controle_alti.executer_controle_sommets")
    @patch("pipeline_controle_alti.executer_controle_ign")
    @patch("pipeline_controle_alti.executer_rapport_cli")
    def test_tous_controles_executes(
        self,
        mock_rapport: Any,
        mock_ign: Any,
        mock_sommets: Any,
        mock_z_null: Any,
        mock_3d: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        mock_3d.return_value = _resultat_succes(2)
        mock_z_null.return_value = _resultat_succes(3)
        mock_sommets.return_value = _resultat_succes(1)
        mock_ign.return_value = _resultat_succes(0)
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert mock_3d.called
        assert mock_z_null.called
        assert mock_sommets.called
        assert mock_ign.called
        assert mock_rapport.called

    @patch("pipeline_controle_alti.executer_controle_3d")
    @patch("pipeline_controle_alti.executer_controle_z_null")
    @patch("pipeline_controle_alti.executer_controle_sommets")
    @patch("pipeline_controle_alti.executer_controle_ign")
    @patch("pipeline_controle_alti.executer_rapport_cli")
    def test_nombre_anomalies_total(
        self,
        mock_rapport: Any,
        mock_ign: Any,
        mock_sommets: Any,
        mock_z_null: Any,
        mock_3d: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        mock_3d.return_value = _resultat_succes(5)
        mock_z_null.return_value = _resultat_succes(10)
        mock_sommets.return_value = _resultat_succes(3)
        mock_ign.return_value = _resultat_succes(2)
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert resultat["nombre_anomalies_total"] == 20

    @patch("pipeline_controle_alti.executer_controle_3d")
    @patch("pipeline_controle_alti.executer_controle_z_null")
    @patch("pipeline_controle_alti.executer_controle_sommets")
    @patch("pipeline_controle_alti.executer_controle_ign")
    @patch("pipeline_controle_alti.executer_rapport_cli")
    def test_un_controle_echoue(
        self,
        mock_rapport: Any,
        mock_ign: Any,
        mock_sommets: Any,
        mock_z_null: Any,
        mock_3d: Any,
        tmp_path: Any,
    ) -> None:
        """Un echec de controle ne bloque pas les suivants."""
        rep = str(tmp_path)
        mock_3d.return_value = _resultat_succes(2)
        mock_z_null.return_value = _resultat_echec("Fichier absent")
        mock_sommets.return_value = _resultat_succes(1)
        mock_ign.return_value = _resultat_succes(0)
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 3
        assert resultat["controles"]["controle_z_null"]["succes"] is False

    @patch("pipeline_controle_alti.executer_controle_3d")
    @patch("pipeline_controle_alti.executer_controle_z_null")
    @patch("pipeline_controle_alti.executer_controle_sommets")
    @patch("pipeline_controle_alti.executer_controle_ign")
    @patch("pipeline_controle_alti.executer_rapport_cli")
    def test_sortie_personnalisee(
        self,
        mock_rapport: Any,
        mock_ign: Any,
        mock_sommets: Any,
        mock_z_null: Any,
        mock_3d: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        sortie = os.path.join(rep, "resultats")
        mock_3d.return_value = _resultat_succes()
        mock_z_null.return_value = _resultat_succes()
        mock_sommets.return_value = _resultat_succes()
        mock_ign.return_value = _resultat_succes()
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep, sortie)

        assert resultat["succes"] is True
        assert os.path.isdir(sortie)
        # Verifie que le dossier de sortie est transmis aux controles
        mock_3d.assert_called_once_with(rep, sortie)
        mock_rapport.assert_called_once_with(sortie, sortie)

    @patch("pipeline_controle_alti.executer_controle_3d")
    @patch("pipeline_controle_alti.executer_controle_z_null")
    @patch("pipeline_controle_alti.executer_controle_sommets")
    @patch("pipeline_controle_alti.executer_controle_ign")
    @patch("pipeline_controle_alti.executer_rapport_cli")
    def test_sortie_par_defaut(
        self,
        mock_rapport: Any,
        mock_ign: Any,
        mock_sommets: Any,
        mock_z_null: Any,
        mock_3d: Any,
        tmp_path: Any,
    ) -> None:
        """Sans --sortie, le repertoire d'entree est utilise."""
        rep = str(tmp_path)
        mock_3d.return_value = _resultat_succes()
        mock_z_null.return_value = _resultat_succes()
        mock_sommets.return_value = _resultat_succes()
        mock_ign.return_value = _resultat_succes()
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        executer_pipeline(rep)

        mock_3d.assert_called_once_with(rep, rep)
        mock_rapport.assert_called_once_with(rep, rep)

    @patch("pipeline_controle_alti.executer_controle_3d")
    @patch("pipeline_controle_alti.executer_controle_z_null")
    @patch("pipeline_controle_alti.executer_controle_sommets")
    @patch("pipeline_controle_alti.executer_controle_ign")
    @patch("pipeline_controle_alti.executer_rapport_cli")
    def test_structure_resultats(
        self,
        mock_rapport: Any,
        mock_ign: Any,
        mock_sommets: Any,
        mock_z_null: Any,
        mock_3d: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        mock_3d.return_value = _resultat_succes()
        mock_z_null.return_value = _resultat_succes()
        mock_sommets.return_value = _resultat_succes()
        mock_ign.return_value = _resultat_succes()
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert "controles" in resultat
        assert "rapport" in resultat
        assert "nombre_anomalies_total" in resultat
        assert "controle_3d" in resultat["controles"]
        assert "controle_z_null" in resultat["controles"]
        assert "controle_alti_sommets" in resultat["controles"]
        assert "controle_alti_ign" in resultat["controles"]

    def test_nombre_controles_definis(self) -> None:
        """Verifie que 4 controles sont enregistres."""
        assert len(NOMS_CONTROLES) == 4

    @patch("pipeline_controle_alti.executer_controle_3d")
    @patch("pipeline_controle_alti.executer_controle_z_null")
    @patch("pipeline_controle_alti.executer_controle_sommets")
    @patch("pipeline_controle_alti.executer_controle_ign")
    @patch("pipeline_controle_alti.executer_rapport_cli")
    def test_tous_controles_echouent(
        self,
        mock_rapport: Any,
        mock_ign: Any,
        mock_sommets: Any,
        mock_z_null: Any,
        mock_3d: Any,
        tmp_path: Any,
    ) -> None:
        """Le pipeline reste en succes meme si tous les controles echouent."""
        rep = str(tmp_path)
        mock_3d.return_value = _resultat_echec()
        mock_z_null.return_value = _resultat_echec()
        mock_sommets.return_value = _resultat_echec()
        mock_ign.return_value = _resultat_echec()
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 0
