"""Tests du pipeline de contrôle de structuration XSD (pipeline_controle_xsd.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pipeline_controle_xsd as pipeline

# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #


def _resume_succes(type_controle: str, nb_erreurs: int = 0) -> dict[str, Any]:
    """Construit un résumé de contrôle réussi."""
    par_severite = {"ERREUR": nb_erreurs} if nb_erreurs else {}
    return {
        "succes": True,
        "type_controle": type_controle,
        "conformite": "CONFORME" if nb_erreurs == 0 else "NON_CONFORME",
        "nb_erreurs": nb_erreurs,
        "nb_par_severite": par_severite,
        "rapport": "rapport.json",
    }


# --------------------------------------------------------------------------- #
# Tests sur fichier inexistant
# --------------------------------------------------------------------------- #


class TestFichierIntrouvable:
    """Le pipeline échoue proprement si le fichier GML n'existe pas."""

    def test_fichier_inexistant(self, tmp_path: Path) -> None:
        resultat = pipeline.executer_pipeline(tmp_path / "absent.gml")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]


# --------------------------------------------------------------------------- #
# Tests d'orchestration (contrôles mockés)
# --------------------------------------------------------------------------- #


def _patcher_tous(nb_par_controle: dict[str, int]):
    """Construit les patchs des 5 wrappers de contrôle avec un nombre d'erreurs donné."""
    type_controles = {
        "E110": "E110_ORDRE",
        "E111": "E111_METIER",
        "E112": "E112_XSD_NATIF",
        "E113": "E113_ENTETE",
        "E114": "E114_VALEURS",
    }
    return {code: _resume_succes(type_controles[code], nb_par_controle.get(code, 0)) for code in type_controles}


class TestOrchestration:
    """Tests de l'agrégation des résumés de contrôle."""

    def _executer(self, tmp_path: Path, resumes: dict[str, dict[str, Any]]):
        gml = tmp_path / "test.gml"
        gml.write_text("<root/>", encoding="utf-8")
        with (
            patch.object(pipeline, "_executer_e110", return_value=resumes["E110"]),
            patch.object(pipeline, "_executer_e111", return_value=resumes["E111"]),
            patch.object(pipeline, "_executer_e112", return_value=resumes["E112"]),
            patch.object(pipeline, "_executer_e113", return_value=resumes["E113"]),
            patch.object(pipeline, "_executer_e114", return_value=resumes["E114"]),
        ):
            return pipeline.executer_pipeline(gml)

    def test_tous_conformes(self, tmp_path: Path) -> None:
        resultat = self._executer(tmp_path, _patcher_tous({}))
        assert resultat["succes"] is True
        assert resultat["nb_erreurs_total"] == 0
        assert resultat["conformite_globale"] == "CONFORME"
        assert set(resultat["controles"]) == {"E110", "E111", "E112", "E113", "E114"}

    def test_total_erreurs_agrege(self, tmp_path: Path) -> None:
        resultat = self._executer(tmp_path, _patcher_tous({"E110": 2, "E114": 3}))
        assert resultat["nb_erreurs_total"] == 5
        assert resultat["conformite_globale"] == "NON_CONFORME"

    def test_controle_en_echec_nonbloquant(self, tmp_path: Path) -> None:
        """Un contrôle qui lève une exception est isolé et signalé."""
        gml = tmp_path / "test.gml"
        gml.write_text("<root/>", encoding="utf-8")
        with (
            patch.object(pipeline, "_executer_e110", return_value=_resume_succes("E110_ORDRE")),
            patch.object(pipeline, "_executer_e111", return_value=_resume_succes("E111_METIER")),
            patch.object(pipeline, "_executer_e112", side_effect=RuntimeError("XSD indisponible")),
            patch.object(pipeline, "_executer_e113", return_value=_resume_succes("E113_ENTETE")),
            patch.object(pipeline, "_executer_e114", return_value=_resume_succes("E114_VALEURS")),
        ):
            resultat = pipeline.executer_pipeline(gml)

        assert resultat["succes"] is True
        assert resultat["controles"]["E112"]["succes"] is False
        assert "XSD indisponible" in resultat["controles"]["E112"]["erreur"]
        assert resultat["controles_en_echec"] == ["E112"]
        # Un échec invalide la conformité globale même sans erreur détectée.
        assert resultat["conformite_globale"] == "NON_CONFORME"

    def test_rapport_global_ecrit(self, tmp_path: Path) -> None:
        resultat = self._executer(tmp_path, _patcher_tous({}))
        chemin = Path(resultat["rapport_global"])
        assert chemin.is_file()
        with open(chemin, encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["controles"].keys() == resultat["controles"].keys()


# --------------------------------------------------------------------------- #
# Test d'intégration bout en bout (contrôles réels)
# --------------------------------------------------------------------------- #


class TestIntegration:
    """Exécution réelle du pipeline sur un GML conforme."""

    def test_pipeline_bout_en_bout(self, gml_entete_conforme: Path) -> None:
        sortie = gml_entete_conforme.parent
        resultat = pipeline.executer_pipeline(gml_entete_conforme, sortie=sortie)

        assert resultat["succes"] is True
        assert set(resultat["controles"]) == {"E110", "E111", "E112", "E113", "E114"}
        assert isinstance(resultat["nb_erreurs_total"], int)
        assert "conformite_globale" in resultat

        # Les contrôles sans dépendance externe doivent toujours produire un rapport.
        for code in ("E110", "E111", "E113", "E114"):
            controle = resultat["controles"][code]
            assert controle["succes"] is True
            assert Path(controle["rapport"]).is_file()

        assert Path(resultat["rapport_global"]).is_file()
