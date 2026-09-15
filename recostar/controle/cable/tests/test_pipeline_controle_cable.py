"""Tests du script pipeline_controle_cable.py."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import DEFAULT, patch

from recostar.controle.cable.pipeline_controle_cable import NOMS_CONTROLES, executer_pipeline

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
    "executer_controle_longueur_bt",
    "executer_controle_longueur_hta",
    "executer_controle_designation",
    "executer_3104",
    "executer_3302",
    "executer_controle_cable_htb_emprise",
    "executer_controle_densite_sommets",
    "executer_5101",
    "executer_5200",
    "executer_controle_precision_cheminement",
    "executer_6110",
    "executer_6111",
    "executer_controle_domaine_tension",
    "executer_9501",
    "executer_controle_position_jonction",
)

# E-3304 recoit un numero d'affaire en plus du repertoire et de la sortie :
# ses arguments d'appel different de ceux des autres controles.
_FONCTION_AVEC_NUMERO_AFFAIRE = "executer_controle_cable_htb_emprise"

_NUMERO_AFFAIRE = "RAC-CVL-25-007998"

_CONTROLES = (
    "E-9500",
    "E-3104",
    "E-3302",
    "E-2101",
    "E-6103",
    "E-5100",
    "E-4200",
    "E-4201",
    "E-6110",
    "E-6111",
    "E-9501",
    "E-9502",
    "E-3304",
    "E-5101",
    "E-5200",
)


def _patch_tous():
    """Patche toutes les fonctions de controle du pipeline (mocks par mot-cle)."""
    return patch.multiple("recostar.controle.cable.pipeline_controle_cable", **dict.fromkeys(_FONCTIONS, DEFAULT))


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
        # Somme des entiers de 1 a 15, un par controle du pipeline.
        assert resultat["nombre_anomalies_total"] == 120

    def test_un_controle_echoue_pipeline_reste_succes(self, tmp_path: Any) -> None:
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes(2)
            mocks["executer_controle_domaine_tension"].return_value = _resultat_echec("Fichier absent")
            resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        # 14 controles reussis x 2 anomalies (E-9500 en echec exclu de la somme)
        assert resultat["nombre_anomalies_total"] == 28
        assert resultat["controles"]["E-9500"]["succes"] is False

    def test_sortie_personnalisee(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        sortie = os.path.join(rep, "resultats")
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            resultat = executer_pipeline(rep, sortie, _NUMERO_AFFAIRE)
            for nom, mock in mocks.items():
                if nom == _FONCTION_AVEC_NUMERO_AFFAIRE:
                    mock.assert_called_once_with(rep, _NUMERO_AFFAIRE, sortie)
                else:
                    mock.assert_called_once_with(rep, sortie)
        assert resultat["succes"] is True
        assert os.path.isdir(sortie)

    def test_sortie_par_defaut(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            executer_pipeline(rep)
            for nom, mock in mocks.items():
                if nom == _FONCTION_AVEC_NUMERO_AFFAIRE:
                    # Sans numero d'affaire, E-3304 est appele avec None et
                    # retourne une erreur sans impacter les autres controles.
                    mock.assert_called_once_with(rep, None, rep)
                else:
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
        """Quinze controles sont enregistres dans la famille cable."""
        assert len(NOMS_CONTROLES) == 16

    def test_numero_affaire_transmis_a_e0508(self, tmp_path: Any) -> None:
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            executer_pipeline(str(tmp_path), None, _NUMERO_AFFAIRE)
        mocks[_FONCTION_AVEC_NUMERO_AFFAIRE].assert_called_once_with(str(tmp_path), _NUMERO_AFFAIRE, str(tmp_path))
