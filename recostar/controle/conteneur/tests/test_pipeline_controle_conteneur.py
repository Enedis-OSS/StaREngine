"""Tests du script pipeline_controle_conteneur.py."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import DEFAULT, patch

from pipeline_controle_conteneur import NOMS_CONTROLES, executer_pipeline

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
    "executer_controle_materiel_jonction",  # E600
    "executer_controle_rattachement_materiel",  # E601
    "executer_controle_unicite_identifiants",  # E602
    "executer_controle_caracteristiques_poteau",  # E603
    "executer_controle_noeuds_coffret",  # E604
    "executer_controle_localisation_noeuds",  # E605
    "executer_controle_localisation_remontees",  # E606
    "executer_controle_localisation_ouvrages",  # E607
    "executer_controle_nombre_cables_jonction",  # E608
    "executer_controle_rattachement_cable",  # E609
    "executer_controle_nomenclature_coffret",  # E610
)

_CONTROLES = (
    "controle_e600",
    "controle_e601",
    "controle_e602",
    "controle_e603",
    "controle_e604",
    "controle_e605",
    "controle_e606",
    "controle_e607",
    "controle_e608",
    "controle_e609",
    "controle_e610",
)


def _patch_tous():
    """Patche toutes les fonctions de controle du pipeline (mocks par mot-cle)."""
    return patch.multiple("pipeline_controle_conteneur", **dict.fromkeys(_FONCTIONS, DEFAULT))


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
        assert resultat["controles"]["controle_e600"]["succes"] is False
        assert resultat["nombre_anomalies_total"] == 0

    def test_controles_appeles_avec_repertoire_et_sortie(self, tmp_path: Any) -> None:
        sortie = tmp_path / "controle" / "conteneur"
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            executer_pipeline(str(tmp_path), str(sortie))
        for mock in mocks.values():
            mock.assert_called_once_with(str(tmp_path.resolve()), str(sortie.resolve()))

    def test_repertoire_sortie_cree(self, tmp_path: Any) -> None:
        sortie = tmp_path / "controle" / "conteneur"
        with _patch_tous() as mocks:
            for mock in mocks.values():
                mock.return_value = _resultat_succes()
            executer_pipeline(str(tmp_path), str(sortie))
        assert os.path.isdir(str(sortie))

    def test_noms_controles_coherents(self) -> None:
        assert NOMS_CONTROLES == _CONTROLES
