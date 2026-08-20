"""Tests du pipeline de contrôle de structuration XSD (pipeline_controle_xsd.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pipeline_controle_xsd as pipeline
import versions
from priorites_structuration import PRIORITE_BLOQUANT, PRIORITE_MAJEUR

# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #


def _resume_succes(
    type_controle: str,
    nb_erreurs: int = 0,
    priorite: str = PRIORITE_BLOQUANT,
) -> dict[str, Any]:
    """Construit un résumé de contrôle réussi, au format produit par `_resumer`.

    `priorite` affecte toutes les erreurs du résumé : bloquantes par défaut,
    ce qui reflète la règle générale de la structuration.
    """
    par_severite = {"ERREUR": nb_erreurs} if nb_erreurs else {}
    par_priorite = {priorite: nb_erreurs} if nb_erreurs else {}
    nb_bloquantes = nb_erreurs if priorite == PRIORITE_BLOQUANT else 0
    return {
        "succes": True,
        "type_controle": type_controle,
        "conformite": "CONFORME" if nb_bloquantes == 0 else "NON_CONFORME",
        "nb_erreurs": nb_erreurs,
        "nb_erreurs_bloquantes": nb_bloquantes,
        "nb_par_severite": par_severite,
        "anomalies_par_priorite": par_priorite,
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
            patch.object(pipeline, "_executer_ordre", return_value=resumes["E110"]),
            patch.object(pipeline, "_executer_metier", return_value=resumes["E111"]),
            patch.object(pipeline, "_executer_xsd_natif", return_value=resumes["E112"]),
            patch.object(pipeline, "_executer_entete", return_value=resumes["E113"]),
            patch.object(pipeline, "_executer_valeurs", return_value=resumes["E114"]),
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
        assert resultat["nb_erreurs_bloquantes"] == 5
        assert resultat["conformite_globale"] == "NON_CONFORME"

    def test_erreurs_non_bloquantes_comptees_sans_declasser(self, tmp_path: Path) -> None:
        """Une anomalie majeure est comptée et listée mais ne déclasse pas."""
        resumes = _patcher_tous({})
        resumes["E113"] = _resume_succes("E113_ENTETE", 1, PRIORITE_MAJEUR)
        resultat = self._executer(tmp_path, resumes)
        assert resultat["nb_erreurs_total"] == 1
        assert resultat["nb_erreurs_bloquantes"] == 0
        assert resultat["conformite_globale"] == "CONFORME"

    def test_une_bloquante_declasse_malgre_les_autres(self, tmp_path: Path) -> None:
        """Une seule bloquante suffit, quel que soit le reste."""
        resumes = _patcher_tous({"E110": 1})
        resumes["E113"] = _resume_succes("E113_ENTETE", 4, PRIORITE_MAJEUR)
        resultat = self._executer(tmp_path, resumes)
        assert resultat["nb_erreurs_total"] == 5
        assert resultat["nb_erreurs_bloquantes"] == 1
        assert resultat["conformite_globale"] == "NON_CONFORME"

    def test_controle_en_echec_nonbloquant(self, tmp_path: Path) -> None:
        """Un contrôle qui lève une exception est isolé et signalé."""
        gml = tmp_path / "test.gml"
        gml.write_text("<root/>", encoding="utf-8")
        with (
            patch.object(pipeline, "_executer_ordre", return_value=_resume_succes("E110_ORDRE")),
            patch.object(pipeline, "_executer_metier", return_value=_resume_succes("E111_METIER")),
            patch.object(pipeline, "_executer_xsd_natif", side_effect=RuntimeError("XSD indisponible")),
            patch.object(pipeline, "_executer_entete", return_value=_resume_succes("E113_ENTETE")),
            patch.object(pipeline, "_executer_valeurs", return_value=_resume_succes("E114_VALEURS")),
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


# --------------------------------------------------------------------------- #
# Sélection des codes de contrôle selon la version
# --------------------------------------------------------------------------- #


class TestCodesSelonVersion:
    """Les clés du rapport global suivent la version contrôlée."""

    def _executer(self, tmp_path: Path, version: str):
        gml = tmp_path / "test.gml"
        gml.write_text("<root/>", encoding="utf-8")
        return pipeline.executer_pipeline(gml, sortie=tmp_path, profil=versions.resoudre_profil(version))

    def test_codes_v1_1(self, tmp_path: Path) -> None:
        resultat = self._executer(tmp_path, "1.1")
        assert list(resultat["controles"]) == ["E110", "E111", "E112", "E113", "E114"]
        assert resultat["version_controlee"] == "1.1"

    def test_codes_v1_0(self, tmp_path: Path) -> None:
        resultat = self._executer(tmp_path, "1.0")
        assert list(resultat["controles"]) == ["E010", "E011", "E012", "E013", "E014"]
        assert resultat["version_controlee"] == "1.0"

    def test_types_controle_alignes_sur_les_codes(self, tmp_path: Path) -> None:
        """Chaque résumé porte un type_controle préfixé par sa propre clé."""
        for version in ("1.0", "1.1"):
            resultat = self._executer(tmp_path, version)
            for code, resume in resultat["controles"].items():
                assert resume["type_controle"].startswith(f"{code}_")

    def test_noms_controles_couvre_toutes_les_versions(self) -> None:
        """Le registre des codes expose les deux séries, pour les libellés PDF."""
        assert set(pipeline.NOMS_CONTROLES) == {
            "E010",
            "E011",
            "E012",
            "E013",
            "E014",
            "E110",
            "E111",
            "E112",
            "E113",
            "E114",
        }


class TestDetectionAutomatiqueVersion:
    """Sans profil explicite, la version est déduite du fichier contrôlé."""

    def _gml(self, tmp_path: Path, version: str) -> Path:
        chemin = tmp_path / f"v{version.replace('.', '')}.gml"
        chemin.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            f'xsi:schemaLocation="urn:test RecoStar-v{version}/Schema.xsd"/>',
            encoding="utf-8",
        )
        return chemin

    def test_gml_v1_0_controle_en_e01x(self, tmp_path: Path) -> None:
        resultat = pipeline.executer_pipeline(self._gml(tmp_path, "1.0"), sortie=tmp_path)
        assert resultat["version_controlee"] == "1.0"
        assert list(resultat["controles"]) == ["E010", "E011", "E012", "E013", "E014"]

    def test_gml_v1_1_controle_en_e11x(self, tmp_path: Path) -> None:
        resultat = pipeline.executer_pipeline(self._gml(tmp_path, "1.1"), sortie=tmp_path)
        assert resultat["version_controlee"] == "1.1"
        assert list(resultat["controles"]) == ["E110", "E111", "E112", "E113", "E114"]

    def test_profil_explicite_prioritaire_sur_la_detection(self, tmp_path: Path) -> None:
        """Un profil imposé n'est jamais écrasé par la détection."""
        resultat = pipeline.executer_pipeline(
            self._gml(tmp_path, "1.1"), sortie=tmp_path, profil=versions.resoudre_profil("1.0")
        )
        assert resultat["version_controlee"] == "1.0"

    def test_repli_sur_version_defaut_si_entete_illisible(self, tmp_path: Path) -> None:
        """Un GML sans schemaLocation reste contrôlé, dans la version par défaut."""
        chemin = tmp_path / "sans_entete.gml"
        chemin.write_text("<root/>", encoding="utf-8")
        resultat = pipeline.executer_pipeline(chemin, sortie=tmp_path)
        assert resultat["version_controlee"] == versions.VERSION_DEFAUT
