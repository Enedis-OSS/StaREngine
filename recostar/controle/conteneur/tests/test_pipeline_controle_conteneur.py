"""Tests du script pipeline_controle_conteneur.py."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import DEFAULT, patch

from recostar.controle.conteneur.pipeline_controle_conteneur import NOMS_CONTROLES, executer_pipeline

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
    "executer_controle_geometrie_supplementaire",
    "executer_controle_derivation",
    "executer_controle_jonction_simple",
    "executer_controle_extremite_reseau",
    "executer_controle_jonction_telecom",
    "executer_controle_raccordement",
    "executer_2201",
    "executer_6105",
    "executer_6106",
    "executer_6112",
    "executer_6107",
    "executer_6113",
    "executer_6114",
    "executer_6115",
    "executer_6213",
    "executer_controle_noeuds_coffret",
    "executer_controle_localisation_ouvrages",
    "executer_controle_localisation_remontees",
    "executer_6208",
    "executer_6209",
    "executer_controle_rattachement_materiel",
    "executer_7103",
    "executer_7100",
    "executer_7101",
    "executer_7104",
    "executer_7305",
    "executer_9600",
    "executer_controle_unicite_identifiants",
    "executer_9602",
    "executer_9603",
    "executer_9604",
    "executer_9605",
    "executer_9606",
    "executer_9607",
    "executer_9608",
)

# Controles recevant en plus le chemin du GML source.
_CONTROLES_AVEC_GML: frozenset[str] = frozenset({"executer_7100", "executer_7101"})

_CONTROLES = (
    "E-7104",
    "E-7100",
    "E-7101",
    "E-7305",
    "E-9600",
    "E-7102",
    "E-7103",
    "E-9601",
    "E-2201",
    "E-9602",
    "E-9603",
    "E-6108",
    "E-3110",
    "E-6105",
    "E-6106",
    "E-6112",
    "E-6209",
    "E-6204",
    "E-6109",
    "E-6201",
    "E-6202",
    "E-6203",
    "E-6116",
    "E-9609",
    "E-9604",
    "E-9605",
    "E-9606",
    "E-9607",
    "E-9608",
    "E-6113",
    "E-6114",
    "E-6115",
    "E-6213",
    "E-6107",
    "E-6208",
)


def _patch_tous():
    """Patche toutes les fonctions de controle du pipeline (mocks par mot-cle)."""
    return patch.multiple(
        "recostar.controle.conteneur.pipeline_controle_conteneur", **dict.fromkeys(_FONCTIONS, DEFAULT)
    )


# --------------------------------------------------------------------------- #
# Tests du pipeline
# --------------------------------------------------------------------------- #


class TestPipeline:
    """Tests de l'orchestration du pipeline conteneur."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_pipeline("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_tous_controles_executes(self, tmp_path: Any) -> None:
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert set(resultat["controles"]) == set(_CONTROLES)

    def test_agregation_des_anomalies(self, tmp_path: Any) -> None:
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes(3)
            resultat = executer_pipeline(str(tmp_path))
        assert resultat["nombre_anomalies_total"] == 3 * len(_CONTROLES)

    def test_echec_controle_non_bloquant(self, tmp_path: Any) -> None:
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_echec("Catalogue introuvable")
            resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["controles"]["E-7104"]["succes"] is False
        assert resultat["nombre_anomalies_total"] == 0

    def test_controles_appeles_avec_repertoire_et_sortie(self, tmp_path: Any) -> None:
        """Tous recoivent repertoire et sortie ; E-7100 et E-7101 y ajoutent le GML.

        Ces deux-la comptent les relations `Ouvrage_Materiel`, que la conversion
        ne conserve pas : le chemin du GML leur est transmis en plus.
        """
        sortie = tmp_path / "controle" / "conteneur"
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            executer_pipeline(str(tmp_path), str(sortie))
        for nom, mock in mocks.items():
            mock.assert_called_once()
            arguments = mock.call_args.args
            assert arguments[:2] == (str(tmp_path.resolve()), str(sortie.resolve()))
            attendu = 3 if nom in _CONTROLES_AVEC_GML else 2
            assert len(arguments) == attendu, f"{nom} : {len(arguments)} arguments"

    def test_repertoire_sortie_cree(self, tmp_path: Any) -> None:
        sortie = tmp_path / "controle" / "conteneur"
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            executer_pipeline(str(tmp_path), str(sortie))
        assert os.path.isdir(str(sortie))

    def test_noms_controles_coherents(self) -> None:
        assert NOMS_CONTROLES == _CONTROLES
