"""Tests du script pipeline_controle_alti.py."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from pipeline_controle_alti import (
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
    "pipeline_controle_alti.executer_controle_3d",
    "pipeline_controle_alti.executer_controle_z_null",
    "pipeline_controle_alti.executer_controle_sommets",
    "pipeline_controle_alti.executer_controle_ign",
    "pipeline_controle_alti.executer_controle_doublons_spatiaux",
    "pipeline_controle_alti.executer_controle_point_leve_geom_supp",
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
    @patch(_PATCHES[5])
    def test_tous_controles_executes(
        self,
        mock_point_leve: Any,
        mock_doublons: Any,
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
        mock_doublons.return_value = _resultat_succes(1)
        mock_point_leve.return_value = _resultat_succes(0)

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert mock_3d.called
        assert mock_z_null.called
        assert mock_sommets.called
        assert mock_ign.called
        assert mock_doublons.called
        assert mock_point_leve.called

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    @patch(_PATCHES[5])
    def test_nombre_anomalies_total(
        self,
        mock_point_leve: Any,
        mock_doublons: Any,
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
        mock_doublons.return_value = _resultat_succes(4)
        mock_point_leve.return_value = _resultat_succes(6)

        resultat = executer_pipeline(rep)

        assert resultat["nombre_anomalies_total"] == 30

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    @patch(_PATCHES[5])
    def test_un_controle_echoue(
        self,
        mock_point_leve: Any,
        mock_doublons: Any,
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
        mock_doublons.return_value = _resultat_succes(0)
        mock_point_leve.return_value = _resultat_succes(0)

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 3
        assert resultat["controles"]["controle_e201"]["succes"] is False

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    @patch(_PATCHES[5])
    def test_sortie_personnalisee(
        self,
        mock_point_leve: Any,
        mock_doublons: Any,
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
        mock_doublons.return_value = _resultat_succes()
        mock_point_leve.return_value = _resultat_succes()

        resultat = executer_pipeline(rep, sortie)

        assert resultat["succes"] is True
        assert os.path.isdir(sortie)
        mock_3d.assert_called_once_with(rep, sortie)

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    @patch(_PATCHES[5])
    def test_sortie_par_defaut(
        self,
        mock_point_leve: Any,
        mock_doublons: Any,
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
        mock_doublons.return_value = _resultat_succes()
        mock_point_leve.return_value = _resultat_succes()

        executer_pipeline(rep)

        mock_3d.assert_called_once_with(rep, rep)

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    @patch(_PATCHES[5])
    def test_structure_resultats(
        self,
        mock_point_leve: Any,
        mock_doublons: Any,
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
        mock_doublons.return_value = _resultat_succes()
        mock_point_leve.return_value = _resultat_succes()

        resultat = executer_pipeline(rep)

        assert "controles" in resultat
        assert "nombre_anomalies_total" in resultat
        assert "controle_e200" in resultat["controles"]
        assert "controle_e201" in resultat["controles"]
        assert "controle_e202" in resultat["controles"]
        assert "controle_e203" in resultat["controles"]
        assert "controle_e204" in resultat["controles"]
        assert "controle_e205" in resultat["controles"]

    def test_nombre_controles_definis(self) -> None:
        """Verifie que 6 controles sont enregistres."""
        assert len(NOMS_CONTROLES) == 6

    @patch(_PATCHES[0])
    @patch(_PATCHES[1])
    @patch(_PATCHES[2])
    @patch(_PATCHES[3])
    @patch(_PATCHES[4])
    @patch(_PATCHES[5])
    def test_tous_controles_echouent(
        self,
        mock_point_leve: Any,
        mock_doublons: Any,
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
        mock_doublons.return_value = _resultat_echec()
        mock_point_leve.return_value = _resultat_echec()

        resultat = executer_pipeline(rep)

        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 0
