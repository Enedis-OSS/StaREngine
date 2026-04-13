"""Tests du script pipeline_controle_plor.py."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from pipeline_controle_plor import (
    NOMS_CONTROLES,
    executer_pipeline,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


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

    @patch("pipeline_controle_plor.executer_controle_cable")
    @patch("pipeline_controle_plor.executer_controle_doublons")
    @patch("pipeline_controle_plor.executer_controle_cheminement")
    @patch("pipeline_controle_plor.executer_rapport_cli")
    def test_tous_controles_executes(
        self,
        mock_rapport: Any,
        mock_cheminement: Any,
        mock_doublons: Any,
        mock_cable: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        mock_cable.return_value = _resultat_succes(2)
        mock_doublons.return_value = _resultat_succes(3)
        mock_cheminement.return_value = _resultat_succes(1)
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert mock_cable.called
        assert mock_doublons.called
        assert mock_cheminement.called
        assert mock_rapport.called

    @patch("pipeline_controle_plor.executer_controle_cable")
    @patch("pipeline_controle_plor.executer_controle_doublons")
    @patch("pipeline_controle_plor.executer_controle_cheminement")
    @patch("pipeline_controle_plor.executer_rapport_cli")
    def test_nombre_anomalies_total(
        self,
        mock_rapport: Any,
        mock_cheminement: Any,
        mock_doublons: Any,
        mock_cable: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        mock_cable.return_value = _resultat_succes(5)
        mock_doublons.return_value = _resultat_succes(10)
        mock_cheminement.return_value = _resultat_succes(3)
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert resultat["nombre_anomalies_total"] == 18

    @patch("pipeline_controle_plor.executer_controle_cable")
    @patch("pipeline_controle_plor.executer_controle_doublons")
    @patch("pipeline_controle_plor.executer_controle_cheminement")
    @patch("pipeline_controle_plor.executer_rapport_cli")
    def test_un_controle_echoue(
        self,
        mock_rapport: Any,
        mock_cheminement: Any,
        mock_doublons: Any,
        mock_cable: Any,
        tmp_path: Any,
    ) -> None:
        """Un echec de controle ne bloque pas les suivants."""
        rep = str(tmp_path)
        mock_cable.return_value = _resultat_succes(2)
        mock_doublons.return_value = _resultat_echec("Fichier absent")
        mock_cheminement.return_value = _resultat_succes(1)
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 3
        assert resultat["controles"]["controle_plor_doublons"]["succes"] is False

    @patch("pipeline_controle_plor.executer_controle_cable")
    @patch("pipeline_controle_plor.executer_controle_doublons")
    @patch("pipeline_controle_plor.executer_controle_cheminement")
    @patch("pipeline_controle_plor.executer_rapport_cli")
    def test_sortie_personnalisee(
        self,
        mock_rapport: Any,
        mock_cheminement: Any,
        mock_doublons: Any,
        mock_cable: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        sortie = os.path.join(rep, "resultats")
        mock_cable.return_value = _resultat_succes()
        mock_doublons.return_value = _resultat_succes()
        mock_cheminement.return_value = _resultat_succes()
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep, sortie)

        assert resultat["succes"] is True
        assert os.path.isdir(sortie)
        mock_cable.assert_called_once_with(rep, sortie)
        mock_rapport.assert_called_once_with(sortie, sortie)

    @patch("pipeline_controle_plor.executer_controle_cable")
    @patch("pipeline_controle_plor.executer_controle_doublons")
    @patch("pipeline_controle_plor.executer_controle_cheminement")
    @patch("pipeline_controle_plor.executer_rapport_cli")
    def test_sortie_par_defaut(
        self,
        mock_rapport: Any,
        mock_cheminement: Any,
        mock_doublons: Any,
        mock_cable: Any,
        tmp_path: Any,
    ) -> None:
        """Sans --sortie, le repertoire d'entree est utilise."""
        rep = str(tmp_path)
        mock_cable.return_value = _resultat_succes()
        mock_doublons.return_value = _resultat_succes()
        mock_cheminement.return_value = _resultat_succes()
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        executer_pipeline(rep)

        mock_cable.assert_called_once_with(rep, rep)
        mock_rapport.assert_called_once_with(rep, rep)

    @patch("pipeline_controle_plor.executer_controle_cable")
    @patch("pipeline_controle_plor.executer_controle_doublons")
    @patch("pipeline_controle_plor.executer_controle_cheminement")
    @patch("pipeline_controle_plor.executer_rapport_cli")
    def test_structure_resultats(
        self,
        mock_rapport: Any,
        mock_cheminement: Any,
        mock_doublons: Any,
        mock_cable: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        mock_cable.return_value = _resultat_succes()
        mock_doublons.return_value = _resultat_succes()
        mock_cheminement.return_value = _resultat_succes()
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert "controles" in resultat
        assert "rapport" in resultat
        assert "nombre_anomalies_total" in resultat
        assert "controle_plor_cable" in resultat["controles"]
        assert "controle_plor_doublons" in resultat["controles"]
        assert "controle_cheminement_superpose" in resultat["controles"]

    def test_nombre_controles_definis(self) -> None:
        """Verifie que 3 controles sont enregistres."""
        assert len(NOMS_CONTROLES) == 3

    @patch("pipeline_controle_plor.executer_controle_cable")
    @patch("pipeline_controle_plor.executer_controle_doublons")
    @patch("pipeline_controle_plor.executer_controle_cheminement")
    @patch("pipeline_controle_plor.executer_rapport_cli")
    def test_tous_controles_echouent(
        self,
        mock_rapport: Any,
        mock_cheminement: Any,
        mock_doublons: Any,
        mock_cable: Any,
        tmp_path: Any,
    ) -> None:
        """Le pipeline reste en succes meme si tous les controles echouent."""
        rep = str(tmp_path)
        mock_cable.return_value = _resultat_echec()
        mock_doublons.return_value = _resultat_echec()
        mock_cheminement.return_value = _resultat_echec()
        mock_rapport.return_value = {"succes": True, "chemin_pdf": "test.pdf"}

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 0
