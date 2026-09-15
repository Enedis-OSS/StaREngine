"""Tests du pipeline de contrôle de structuration XSD (pipeline_controle_xsd.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from recostar.controle.xsd_structuration import pipeline_controle_xsd as pipeline
from recostar.controle.xsd_structuration import versions
from recostar.controle.xsd_structuration.priorites_structuration import PRIORITE_FORTE, PRIORITE_MOYENNE

# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #


def _resume_succes(
    type_controle: str,
    nb_erreurs: int = 0,
    priorite: str = PRIORITE_FORTE,
) -> dict[str, Any]:
    """Construit un résumé de contrôle réussi, au format produit par `_resumer`.

    `priorite` affecte toutes les erreurs du résumé : bloquantes par défaut,
    ce qui reflète la règle générale de la structuration.
    """
    par_severite = {"ERREUR": nb_erreurs} if nb_erreurs else {}
    par_priorite = {priorite: nb_erreurs} if nb_erreurs else {}
    nb_bloquantes = nb_erreurs if priorite == PRIORITE_FORTE else 0
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
    """Construit les patchs des 8 wrappers de contrôle avec un nombre d'erreurs donné.

    E0116 et E0117 ne sont pas patchés : ils s'exécutent réellement et ne
    relèvent rien sur le GML factice, ce qui suffit au test d'agrégation.
    """
    type_controles = {
        "E0110": "E0110_ORDRE",
        "E0111": "E0111_METIER",
        "E0112": "E0112_XSD_NATIF",
        "E0113": "E0113_ENTETE",
        "E0114": "E0114_VALEURS",
        "E0115": "E0115_GEOMETRIE",
        "E0118": "E0118_DOCUMENT",
        "E0119": "E0119_SRS_DIMENSION",
        "E0120": "E0120_STATUT_EN_SERVICE",
    }
    return {code: _resume_succes(type_controles[code], nb_par_controle.get(code, 0)) for code in type_controles}


class TestOrchestration:
    """Tests de l'agrégation des résumés de contrôle."""

    def _executer(self, tmp_path: Path, resumes: dict[str, dict[str, Any]]):
        gml = tmp_path / "test.gml"
        gml.write_text("<root/>", encoding="utf-8")
        with (
            patch.object(pipeline, "_executer_ordre", return_value=resumes["E0110"]),
            patch.object(pipeline, "_executer_metier", return_value=resumes["E0111"]),
            patch.object(pipeline, "_executer_xsd_natif", return_value=resumes["E0112"]),
            patch.object(pipeline, "_executer_entete", return_value=resumes["E0113"]),
            patch.object(pipeline, "_executer_valeurs", return_value=resumes["E0114"]),
            patch.object(pipeline, "_executer_geometrie", return_value=resumes["E0115"]),
            # Le GML factice « <root/> » ne porte aucun objet : sans ce patch,
            # E0118 leverait a juste titre son anomalie de document vide.
            patch.object(pipeline, "_executer_document", return_value=resumes["E0118"]),
            patch.object(pipeline, "_executer_srs_dimension", return_value=resumes["E0119"]),
            # Le GML factice ne porte aucun statut : sans ce patch, E0120
            # leverait a juste titre son constat de livraison sans ouvrage.
            patch.object(pipeline, "_executer_statut_en_service", return_value=resumes["E0120"]),
        ):
            return pipeline.executer_pipeline(gml)

    def test_tous_conformes(self, tmp_path: Path) -> None:
        resultat = self._executer(tmp_path, _patcher_tous({}))
        assert resultat["succes"] is True
        assert resultat["nb_erreurs_total"] == 0
        assert resultat["conformite_globale"] == "CONFORME"
        assert set(resultat["controles"]) == {
            "E0110",
            "E0111",
            "E0112",
            "E0113",
            "E0114",
            "E0115",
            "E0116",
            "E0117",
            "E0118",
            "E0119",
            "E0120",
        }

    def test_total_erreurs_agrege(self, tmp_path: Path) -> None:
        resultat = self._executer(tmp_path, _patcher_tous({"E0110": 2, "E0114": 3}))
        assert resultat["nb_erreurs_total"] == 5
        assert resultat["nb_erreurs_bloquantes"] == 5
        assert resultat["conformite_globale"] == "NON_CONFORME"

    def test_erreurs_non_bloquantes_comptees_sans_declasser(self, tmp_path: Path) -> None:
        """Une anomalie majeure est comptée et listée mais ne déclasse pas."""
        resumes = _patcher_tous({})
        resumes["E0113"] = _resume_succes("E0113_ENTETE", 1, PRIORITE_MOYENNE)
        resultat = self._executer(tmp_path, resumes)
        assert resultat["nb_erreurs_total"] == 1
        assert resultat["nb_erreurs_bloquantes"] == 0
        assert resultat["conformite_globale"] == "CONFORME"

    def test_une_bloquante_declasse_malgre_les_autres(self, tmp_path: Path) -> None:
        """Une seule bloquante suffit, quel que soit le reste."""
        resumes = _patcher_tous({"E0110": 1})
        resumes["E0113"] = _resume_succes("E0113_ENTETE", 4, PRIORITE_MOYENNE)
        resultat = self._executer(tmp_path, resumes)
        assert resultat["nb_erreurs_total"] == 5
        assert resultat["nb_erreurs_bloquantes"] == 1
        assert resultat["conformite_globale"] == "NON_CONFORME"

    def test_controle_en_echec_nonbloquant(self, tmp_path: Path) -> None:
        """Un contrôle qui lève une exception est isolé et signalé."""
        gml = tmp_path / "test.gml"
        gml.write_text("<root/>", encoding="utf-8")
        with (
            patch.object(pipeline, "_executer_ordre", return_value=_resume_succes("E0110_ORDRE")),
            patch.object(pipeline, "_executer_metier", return_value=_resume_succes("E0111_METIER")),
            patch.object(pipeline, "_executer_xsd_natif", side_effect=RuntimeError("XSD indisponible")),
            patch.object(pipeline, "_executer_entete", return_value=_resume_succes("E0113_ENTETE")),
            patch.object(pipeline, "_executer_valeurs", return_value=_resume_succes("E0114_VALEURS")),
            patch.object(pipeline, "_executer_geometrie", return_value=_resume_succes("E0115_GEOMETRIE")),
        ):
            resultat = pipeline.executer_pipeline(gml)

        assert resultat["succes"] is True
        assert resultat["controles"]["E0112"]["succes"] is False
        assert "XSD indisponible" in resultat["controles"]["E0112"]["erreur"]
        assert resultat["controles_en_echec"] == ["E0112"]
        # Un échec invalide la conformité globale même sans erreur détectée.
        assert resultat["conformite_globale"] == "NON_CONFORME"

    def test_rapport_de_famille_ecrit(self, tmp_path: Path) -> None:
        """La famille ne laisse qu'un fichier, qui porte la synthèse par contrôle."""
        resultat = self._executer(tmp_path, _patcher_tous({}))
        chemin = Path(resultat["rapport_famille"])
        assert chemin.is_file()
        with open(chemin, encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["controles"].keys() == resultat["controles"].keys()
        assert contenu["famille"] == "structuration"


# --------------------------------------------------------------------------- #
# Test d'intégration bout en bout (contrôles réels)
# --------------------------------------------------------------------------- #


class TestIntegration:
    """Exécution réelle du pipeline sur un GML conforme."""

    def test_pipeline_bout_en_bout(self, gml_entete_conforme: Path) -> None:
        sortie = gml_entete_conforme.parent
        resultat = pipeline.executer_pipeline(gml_entete_conforme, sortie=sortie)

        assert resultat["succes"] is True
        assert set(resultat["controles"]) == {
            "E0110",
            "E0111",
            "E0112",
            "E0113",
            "E0114",
            "E0115",
            "E0116",
            "E0117",
            "E0118",
            "E0119",
            "E0120",
        }
        assert isinstance(resultat["nb_erreurs_total"], int)
        assert "conformite_globale" in resultat

        # Les contrôles sans dépendance externe doivent toujours aboutir.
        for code in ("E0110", "E0111", "E0113", "E0114", "E0115"):
            assert resultat["controles"][code]["succes"] is True

        # Leurs rapports individuels sont refondus dans le fichier de famille,
        # seul survivant : c'est lui qui doit exister.
        rapport_famille = Path(resultat["rapport_famille"])
        assert rapport_famille.is_file()
        for code in ("E0110", "E0111", "E0113", "E0114", "E0115"):
            assert not Path(resultat["controles"][code]["rapport"]).is_file()

        restants = sorted(p.name for p in sortie.glob("*_controle_*.json"))
        assert restants == [rapport_famille.name]


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
        assert list(resultat["controles"]) == [
            "E0110",
            "E0111",
            "E0112",
            "E0113",
            "E0114",
            "E0115",
            "E0116",
            "E0117",
            "E0118",
            "E0119",
            "E0120",
        ]
        assert resultat["version_controlee"] == "1.1"

    def test_codes_v1_0(self, tmp_path: Path) -> None:
        resultat = self._executer(tmp_path, "1.0")
        assert list(resultat["controles"]) == [
            "E0010",
            "E0011",
            "E0012",
            "E0013",
            "E0014",
            "E0015",
            "E0016",
            "E0017",
            "E0018",
            "E0019",
            "E0020",
        ]
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
            "E0010",
            "E0011",
            "E0012",
            "E0013",
            "E0014",
            "E0015",
            "E0016",
            "E0017",
            "E0018",
            "E0019",
            "E0020",
            "E0110",
            "E0111",
            "E0112",
            "E0113",
            "E0114",
            "E0115",
            "E0116",
            "E0117",
            "E0118",
            "E0119",
            "E0120",
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
        assert list(resultat["controles"]) == [
            "E0010",
            "E0011",
            "E0012",
            "E0013",
            "E0014",
            "E0015",
            "E0016",
            "E0017",
            "E0018",
            "E0019",
            "E0020",
        ]

    def test_gml_v1_1_controle_en_e11x(self, tmp_path: Path) -> None:
        resultat = pipeline.executer_pipeline(self._gml(tmp_path, "1.1"), sortie=tmp_path)
        assert resultat["version_controlee"] == "1.1"
        assert list(resultat["controles"]) == [
            "E0110",
            "E0111",
            "E0112",
            "E0113",
            "E0114",
            "E0115",
            "E0116",
            "E0117",
            "E0118",
            "E0119",
            "E0120",
        ]

    def _gml_depot(self, tmp_path: Path, branche: str) -> Path:
        """Crée un GML dont le schemaLocation pointe une branche réelle du dépôt.

        Complète `_gml`, qui forge une URL factice : la reconnaissance par nom
        de branche porte sur le chemin `/raw/<branche>/` du dépôt amont, que
        seule l'URL canonique reproduit.
        """
        url = (
            "http://StaR-Elec.com https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/"
            f"{branche}/RecoStaR/SchemaStarElecRecoStar.xsd"
        )
        chemin = tmp_path / f"{branche.replace('.', '').replace('-', '')}.gml"
        chemin.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            f'xsi:schemaLocation="{url}"/>',
            encoding="utf-8",
        )
        return chemin

    def test_gml_branche_main_controle_comme_le_tag_v1_0(self, tmp_path: Path) -> None:
        """Un fichier pris sur `main` est contrôlé en V1.0, comme le tag v1.0.

        Les producteurs historiques pointent la branche `main` du dépôt amont,
        dont le contenu suit le schéma V1.0. Les deux formes doivent donner la
        même version contrôlée et la même série de codes : c'est l'équivalence
        que ce test verrouille, `main` ne portant aucun tag de version.
        """
        depuis_main = pipeline.executer_pipeline(self._gml_depot(tmp_path, "main"), sortie=tmp_path)
        depuis_tag = pipeline.executer_pipeline(self._gml_depot(tmp_path, "RecoStar-v1.0"), sortie=tmp_path)
        assert depuis_main["version_controlee"] == depuis_tag["version_controlee"] == "1.0"
        assert list(depuis_main["controles"]) == list(depuis_tag["controles"])
        assert list(depuis_main["controles"]) == [
            "E0010",
            "E0011",
            "E0012",
            "E0013",
            "E0014",
            "E0015",
            "E0016",
            "E0017",
            "E0018",
            "E0019",
            "E0020",
        ]

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


class _ErreurFactice:
    """Erreur minimale exposant le contrat attendu par le pipeline."""

    def __init__(self, regle: str) -> None:
        self.severite = "ERREUR"
        self._regle = regle

    def vers_dict(self) -> dict:
        """Serialise l'erreur, `type_erreur` portant le code de la regle."""
        return {"type_erreur": self._regle}


class TestCodesErreurEmis:
    """Codes du verificateur exposes par le resume d'un controle."""

    def test_sans_anomalie_codes_couverts(self):
        """Sans anomalie, le controle annonce les codes qu'il couvre."""
        assert pipeline._codes_erreur("E0112_XSD_NATIF", []) == ("E-1104",)

    def test_codes_des_anomalies_relevees(self):
        """Avec anomalies, seuls les codes reellement emis sont exposes."""
        codes = pipeline._codes_erreur("E0110_ORDRE", [_ErreurFactice("ELEMENT_REQUIS_MANQUANT")])
        assert codes == ("E-1101",)

    def test_doublons_fusionnes(self):
        """Deux anomalies de meme regle ne produisent qu'un code."""
        erreurs = [_ErreurFactice("ELEMENT_REQUIS_MANQUANT")] * 3
        assert pipeline._codes_erreur("E0110_ORDRE", erreurs) == ("E-1101",)

    def test_repli_sur_le_code_du_controle(self):
        """Une regle sans equivalent au verificateur retombe sur le code du controle.

        Le repli reproduit celui de la sortie : la colonne du rapport et le
        detail des anomalies portent alors la meme valeur.
        """
        codes = pipeline._codes_erreur("E0110_ORDRE", [_ErreurFactice("ORDRE_INCORRECT")])
        assert codes == ("E0110",)

    def test_type_controle_inconnu(self):
        """Un type de controle hors nomenclature ne rend aucun code."""
        assert pipeline._codes_erreur("INCONNU", []) == ()

    def test_version_v1_0(self):
        """La nomenclature V1.0 (E001x) se resout comme la V1.1."""
        assert pipeline._codes_erreur("E0012_XSD_NATIF", []) == ("E-1104",)
