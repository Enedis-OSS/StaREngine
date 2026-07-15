"""Tests du script pipeline_controle_cable.py."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import DEFAULT, patch

from pipeline_controle_cable import NOMS_CONTROLES, executer_pipeline

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _resultat_succes(nb_anomalies: int = 0) -> dict[str, Any]:
    """Construit un resultat de controle reussi."""
    return {"succes": True, "nombre_anomalies": nb_anomalies, "sortie": "test.geojson"}


def _resultat_echec(erreur: str = "Erreur") -> dict[str, Any]:
    """Construit un resultat de controle en echec."""
    return {"succes": False, "erreur": erreur}


# Fonctions executer_controle_* importees dans le namespace du pipeline
_FONCTIONS = (
    "executer_controle_domaine_tension",  # E500
    "executer_controle_fonction_cable",  # E501
    "executer_controle_designation",  # E502
    "executer_controle_precision_cheminement",  # E503
    "executer_controle_densite_sommets",  # E504
    "executer_controle_longueur_domaine",  # E505
    "executer_controle_raccordement",  # E506
    "executer_controle_position_jonction",  # E507
)

_CONTROLES = (
    "controle_e500",
    "controle_e501",
    "controle_e502",
    "controle_e503",
    "controle_e504",
    "controle_e505",
    "controle_e506",
    "controle_e507",
)


def _patch_tous():
    """Patche toutes les fonctions de controle du pipeline (mocks par mot-cle)."""
    return patch.multiple("pipeline_controle_cable", **dict.fromkeys(_FONCTIONS, DEFAULT))


# --------------------------------------------------------------------------- #
# Tests du pipeline
# --------------------------------------------------------------------------- #


class TestPipeline:
    """Tests de l'orchestration du pipeline cable."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_pipeline("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_tous_controles_executes(self, tmp_path: Any) -> None:
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes(1)
            resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        for mock in mocks.values():
            assert mock.called
        for controle in _CONTROLES:
            assert resultat["controles"][controle]["succes"] is True

    def test_nombre_anomalies_total(self, tmp_path: Any) -> None:
        with _patch_tous() as mocks:
            for i, mock in enumerate(mocks.values(), start=1):
                mock.return_value = _resultat_succes(i)
            resultat = executer_pipeline(str(tmp_path))
        # 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8
        assert resultat["nombre_anomalies_total"] == 36

    def test_un_controle_echoue_pipeline_reste_succes(self, tmp_path: Any) -> None:
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes(2)
            mocks["executer_controle_domaine_tension"].return_value = _resultat_echec("Fichier absent")
            resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        # 7 controles reussis x 2 anomalies (E500 en echec exclu de la somme)
        assert resultat["nombre_anomalies_total"] == 14
        assert resultat["controles"]["controle_e500"]["succes"] is False

    def test_sortie_personnalisee(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        sortie = os.path.join(rep, "resultats")
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            resultat = executer_pipeline(rep, sortie)
            for mock in mocks.values():
                mock.assert_called_once_with(rep, sortie)
        assert resultat["succes"] is True
        assert os.path.isdir(sortie)

    def test_sortie_par_defaut(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            executer_pipeline(rep)
            for mock in mocks.values():
                mock.assert_called_once_with(rep, rep)

    def test_structure_resultats(self, tmp_path: Any) -> None:
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            resultat = executer_pipeline(str(tmp_path))
        assert "controles" in resultat
        assert "nombre_anomalies_total" in resultat
        for controle in _CONTROLES:
            assert controle in resultat["controles"]

    def test_nombre_controles_definis(self) -> None:
        """Huit controles sont enregistres (E500 a E507)."""
        assert len(NOMS_CONTROLES) == 8
