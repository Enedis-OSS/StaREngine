"""Tests du script pipeline_controle_cheminement.py."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from pipeline_controle_cheminement import (
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


# Decorateurs de mock appliques dans l'ordre inverse des parametres
_PATCHES = (
    "pipeline_controle_cheminement.executer_controle_superpositions",
    "pipeline_controle_cheminement.executer_controle_integrite_cables",
    "pipeline_controle_cheminement.executer_controle_cable_terre",
    "pipeline_controle_cheminement.executer_controle_implantation_cables",
    "pipeline_controle_cheminement.executer_controle_charge_generatrice",
)


# --------------------------------------------------------------------------- #
# Tests du pipeline
# --------------------------------------------------------------------------- #


class TestPipeline:
    """Tests de l'orchestration du pipeline."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_pipeline("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    def test_tous_controles_executes(
        self,
        mock_charge: Any,
        mock_implantation: Any,
        mock_cable_terre: Any,
        mock_integrite: Any,
        mock_superpositions: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        mock_superpositions.return_value = _resultat_succes(2)
        mock_integrite.return_value = _resultat_succes(3)
        mock_cable_terre.return_value = _resultat_succes(1)
        mock_implantation.return_value = _resultat_succes(0)
        mock_charge.return_value = _resultat_succes(1)

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert mock_superpositions.called
        assert mock_integrite.called
        assert mock_cable_terre.called
        assert mock_implantation.called
        assert mock_charge.called

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    def test_nombre_anomalies_total(
        self,
        mock_charge: Any,
        mock_implantation: Any,
        mock_cable_terre: Any,
        mock_integrite: Any,
        mock_superpositions: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        mock_superpositions.return_value = _resultat_succes(5)
        mock_integrite.return_value = _resultat_succes(10)
        mock_cable_terre.return_value = _resultat_succes(3)
        mock_implantation.return_value = _resultat_succes(2)
        mock_charge.return_value = _resultat_succes(4)

        resultat = executer_pipeline(rep)

        assert resultat["nombre_anomalies_total"] == 24

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    def test_un_controle_echoue(
        self,
        mock_charge: Any,
        mock_implantation: Any,
        mock_cable_terre: Any,
        mock_integrite: Any,
        mock_superpositions: Any,
        tmp_path: Any,
    ) -> None:
        """Un echec de controle ne bloque pas les suivants."""
        rep = str(tmp_path)
        mock_superpositions.return_value = _resultat_succes(2)
        mock_integrite.return_value = _resultat_echec("Fichier absent")
        mock_cable_terre.return_value = _resultat_succes(1)
        mock_implantation.return_value = _resultat_succes(0)
        mock_charge.return_value = _resultat_succes(0)

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 3
        assert resultat["controles"]["controle_e401"]["succes"] is False

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    def test_sortie_personnalisee(
        self,
        mock_charge: Any,
        mock_implantation: Any,
        mock_cable_terre: Any,
        mock_integrite: Any,
        mock_superpositions: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        sortie = os.path.join(rep, "resultats")
        mock_superpositions.return_value = _resultat_succes()
        mock_integrite.return_value = _resultat_succes()
        mock_cable_terre.return_value = _resultat_succes()
        mock_implantation.return_value = _resultat_succes()
        mock_charge.return_value = _resultat_succes()

        resultat = executer_pipeline(rep, sortie)

        assert resultat["succes"] is True
        assert os.path.isdir(sortie)
        mock_superpositions.assert_called_once_with(rep, sortie)

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    def test_sortie_par_defaut(
        self,
        mock_charge: Any,
        mock_implantation: Any,
        mock_cable_terre: Any,
        mock_integrite: Any,
        mock_superpositions: Any,
        tmp_path: Any,
    ) -> None:
        """Sans --sortie, le repertoire d'entree est utilise."""
        rep = str(tmp_path)
        mock_superpositions.return_value = _resultat_succes()
        mock_integrite.return_value = _resultat_succes()
        mock_cable_terre.return_value = _resultat_succes()
        mock_implantation.return_value = _resultat_succes()
        mock_charge.return_value = _resultat_succes()

        executer_pipeline(rep)

        mock_superpositions.assert_called_once_with(rep, rep)

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    def test_structure_resultats(
        self,
        mock_charge: Any,
        mock_implantation: Any,
        mock_cable_terre: Any,
        mock_integrite: Any,
        mock_superpositions: Any,
        tmp_path: Any,
    ) -> None:
        rep = str(tmp_path)
        mock_superpositions.return_value = _resultat_succes()
        mock_integrite.return_value = _resultat_succes()
        mock_cable_terre.return_value = _resultat_succes()
        mock_implantation.return_value = _resultat_succes()
        mock_charge.return_value = _resultat_succes()

        resultat = executer_pipeline(rep)

        assert "controles" in resultat
        assert "nombre_anomalies_total" in resultat
        assert "controle_e400" in resultat["controles"]
        assert "controle_e401" in resultat["controles"]
        assert "controle_e402" in resultat["controles"]
        assert "controle_e403" in resultat["controles"]
        assert "controle_e404" in resultat["controles"]

    def test_nombre_controles_definis(self) -> None:
        """Verifie que 5 controles sont enregistres."""
        assert len(NOMS_CONTROLES) == 5

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    def test_tous_controles_echouent(
        self,
        mock_charge: Any,
        mock_implantation: Any,
        mock_cable_terre: Any,
        mock_integrite: Any,
        mock_superpositions: Any,
        tmp_path: Any,
    ) -> None:
        """Le pipeline reste en succes meme si tous les controles echouent."""
        rep = str(tmp_path)
        mock_superpositions.return_value = _resultat_echec()
        mock_integrite.return_value = _resultat_echec()
        mock_cable_terre.return_value = _resultat_echec()
        mock_implantation.return_value = _resultat_echec()
        mock_charge.return_value = _resultat_echec()

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 0
