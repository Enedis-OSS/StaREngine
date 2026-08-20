"""
Tests du pipeline complet RecoStaR (pipeline_complet.py).

Les quatre etapes sont des sous-processus longs (conversion GML, controles,
calcul des longueurs) : elles ne sont pas executees ici. Les tests portent sur
la logique d'orchestration, qui est l'objet du module :

- construction des lignes de commande passees a chaque script ;
- lecture du resultat d'un sous-processus, y compris le cas des scripts qui
  sortent avec le code 0 tout en signalant un echec dans leur rapport JSON ;
- politique d'arret et assemblage du rapport de synthese ;
- traitement par lot : decoupage en sous-dossiers, poursuite malgre un echec ;
- coherence du registre ETAPES avec les scripts reellement presents.

Le niveau sous-jacent (subprocess.run, executer_etape) est substitue par
monkeypatch, ce qui garde les tests isoles et instantanes.
"""

import dataclasses
import json
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

import pytest

from pipeline_complet import (
    CONSTRUCTEURS_ARGUMENTS,
    DOSSIER_TRAVAIL_DEFAUT,
    ETAPES,
    FICHIER_RAPPORT,
    FICHIER_RAPPORT_LOT,
    RACINE,
    SUFFIXE_GML_SORTIE,
    TAILLE_MAX_TRACE,
    ContexteOrchestration,
    EtapePipeline,
    ResultatEtape,
    _analyser_sortie_json,
    _arguments_controle,
    _arguments_geojson_vers_gml,
    _arguments_gml_vers_geojson,
    _arguments_longueurs,
    _interrompre_apres,
    _motif_echec,
    _tronquer_trace,
    construire_contexte,
    executer_etape,
    executer_lot,
    executer_pipeline,
    lister_gml_du_lot,
    main,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gml_source(tmp_path: Path) -> Path:
    """Cree un fichier GML d'entree minimal (le contenu n'est jamais parse ici)."""
    chemin = tmp_path / "recolement.gml"
    chemin.write_text("<gml/>", encoding="utf-8")
    return chemin


@pytest.fixture
def contexte(tmp_path: Path, gml_source: Path) -> ContexteOrchestration:
    """Contexte d'orchestration resolu, sans option facultative."""
    racine = tmp_path / "travail"
    return ContexteOrchestration(
        gml_entree=gml_source,
        racine_sortie=racine,
        dossier_geojson=racine / "geojson",
        gml_sortie=racine / "sortie.gml",
    )


def _processus(
    code_retour: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> "subprocess.CompletedProcess[str]":
    """Fabrique un CompletedProcess pour substituer subprocess.run."""
    return subprocess.CompletedProcess(args=["python"], returncode=code_retour, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Construction du contexte
# ---------------------------------------------------------------------------


class TestConstruireContexte:
    """Validation des entrees et resolution de l'arborescence de travail."""

    def test_gml_introuvable_retourne_erreur(self, tmp_path: Path) -> None:
        contexte, erreur = construire_contexte(str(tmp_path / "absent.gml"))
        assert contexte is None
        assert erreur is not None
        assert "introuvable" in erreur

    def test_repertoire_passe_comme_gml_est_refuse(self, tmp_path: Path) -> None:
        """Un repertoire n'est pas un fichier : is_file() doit le rejeter."""
        contexte, erreur = construire_contexte(str(tmp_path))
        assert contexte is None
        assert erreur is not None

    def test_sortie_par_defaut_a_cote_du_gml(self, gml_source: Path) -> None:
        contexte, erreur = construire_contexte(str(gml_source))
        assert erreur is None
        assert contexte is not None
        assert contexte.racine_sortie == gml_source.parent / "pipeline_recostar"

    def test_sortie_explicite_est_resolue(self, gml_source: Path, tmp_path: Path) -> None:
        cible = tmp_path / "ailleurs"
        contexte, _ = construire_contexte(str(gml_source), sortie=str(cible))
        assert contexte is not None
        assert contexte.racine_sortie == cible.resolve()

    def test_dossier_geojson_est_cree(self, gml_source: Path, tmp_path: Path) -> None:
        """Les etapes 2 a 4 relisent ce dossier : il doit exister des la resolution."""
        contexte, _ = construire_contexte(str(gml_source), sortie=str(tmp_path / "t"))
        assert contexte is not None
        assert contexte.dossier_geojson.is_dir()

    def test_gml_sortie_par_defaut_derive_du_nom_source(self, gml_source: Path, tmp_path: Path) -> None:
        contexte, _ = construire_contexte(str(gml_source), sortie=str(tmp_path / "t"))
        assert contexte is not None
        assert contexte.gml_sortie.name == f"recolement{SUFFIXE_GML_SORTIE}"

    def test_gml_sortie_explicite_est_conserve(self, gml_source: Path, tmp_path: Path) -> None:
        cible = tmp_path / "resultat.gml"
        contexte, _ = construire_contexte(str(gml_source), sortie=str(tmp_path / "t"), gml_sortie=str(cible))
        assert contexte is not None
        assert contexte.gml_sortie == cible.resolve()

    def test_options_facultatives_sont_propagees(self, gml_source: Path, tmp_path: Path) -> None:
        contexte, _ = construire_contexte(
            str(gml_source),
            sortie=str(tmp_path / "t"),
            numero_affaire="RAC-ABC-24-000001",
            srs="EPSG:2154",
        )
        assert contexte is not None
        assert contexte.numero_affaire == "RAC-ABC-24-000001"
        assert contexte.srs == "EPSG:2154"


# ---------------------------------------------------------------------------
# Construction des lignes de commande
# ---------------------------------------------------------------------------


class TestPropagationCommentaire:
    """Propagation de --commentaire depuis le CLI jusqu'a la conversion sortante."""

    def test_defaut_est_desactive(self, gml_source: Path, tmp_path: Path) -> None:
        contexte, _ = construire_contexte(str(gml_source), sortie=str(tmp_path / "t"))
        assert contexte is not None
        assert contexte.commentaire_vide is False

    def test_valeur_transmise_au_contexte(self, gml_source: Path, tmp_path: Path) -> None:
        contexte, _ = construire_contexte(
            str(gml_source),
            sortie=str(tmp_path / "t"),
            commentaire_vide=True,
        )
        assert contexte is not None
        assert contexte.commentaire_vide is True


class TestArgumentsEtapes:
    """Arguments transmis a chacun des quatre scripts."""

    def test_conversion_entrante_positionnels(self, contexte: ContexteOrchestration) -> None:
        assert _arguments_gml_vers_geojson(contexte) == [
            str(contexte.gml_entree),
            str(contexte.dossier_geojson),
        ]

    def test_controle_transmet_le_gml_explicitement(self, contexte: ContexteOrchestration) -> None:
        """Sans --gml, pipeline_globale ecarterait la famille structuration.

        Le dossier analyse ne contient que des GeoJSON : la detection
        automatique du GML n'y trouverait rien.
        """
        arguments = _arguments_controle(contexte)
        assert "--gml" in arguments
        assert arguments[arguments.index("--gml") + 1] == str(contexte.gml_entree)

    def test_controle_analyse_le_dossier_geojson(self, contexte: ContexteOrchestration) -> None:
        arguments = _arguments_controle(contexte)
        assert arguments[arguments.index("--repertoire") + 1] == str(contexte.dossier_geojson)

    def test_controle_sans_numero_affaire_omet_l_option(self, contexte: ContexteOrchestration) -> None:
        assert "--numero_affaire" not in _arguments_controle(contexte)

    def test_controle_avec_numero_affaire_ajoute_l_option(self, contexte: ContexteOrchestration) -> None:
        avec_numero = dataclasses.replace(contexte, numero_affaire="RAC-ABC-24-000001")
        arguments = _arguments_controle(avec_numero)
        assert arguments[arguments.index("--numero_affaire") + 1] == "RAC-ABC-24-000001"

    def test_longueurs_sortie_dans_la_racine(self, contexte: ContexteOrchestration) -> None:
        """Le script cree lui-meme un sous-dossier rapport/ dans --chemin-sortie."""
        arguments = _arguments_longueurs(contexte)
        assert arguments[arguments.index("--chemin-sortie") + 1] == str(contexte.racine_sortie)

    def test_conversion_sortante_positionnels(self, contexte: ContexteOrchestration) -> None:
        assert _arguments_geojson_vers_gml(contexte)[:2] == [
            str(contexte.dossier_geojson),
            str(contexte.gml_sortie),
        ]

    def test_conversion_sortante_sans_srs_omet_l_option(self, contexte: ContexteOrchestration) -> None:
        """Sans --srs, le script detecte le CRS des GeoJSON et preserve l'original."""
        assert "--srs" not in _arguments_geojson_vers_gml(contexte)

    def test_conversion_sortante_sans_commentaire_omet_le_drapeau(self, contexte: ContexteOrchestration) -> None:
        assert "--commentaire" not in _arguments_geojson_vers_gml(contexte)

    def test_conversion_sortante_avec_commentaire_ajoute_le_drapeau(self, contexte: ContexteOrchestration) -> None:
        avec_commentaire = dataclasses.replace(contexte, commentaire_vide=True)
        assert "--commentaire" in _arguments_geojson_vers_gml(avec_commentaire)

    def test_commentaire_est_un_drapeau_sans_valeur(self, contexte: ContexteOrchestration) -> None:
        """Le drapeau est en fin de commande et n'est suivi d'aucune valeur."""
        arguments = _arguments_geojson_vers_gml(dataclasses.replace(contexte, commentaire_vide=True))
        assert arguments[-1] == "--commentaire"

    def test_commentaire_absent_des_autres_etapes(self, contexte: ContexteOrchestration) -> None:
        """Seule la conversion sortante connait --commentaire."""
        avec_commentaire = dataclasses.replace(contexte, commentaire_vide=True)
        for constructeur in (_arguments_gml_vers_geojson, _arguments_controle, _arguments_longueurs):
            assert "--commentaire" not in constructeur(avec_commentaire)

    def test_conversion_sortante_avec_srs_ajoute_l_option(self, contexte: ContexteOrchestration) -> None:
        avec_srs = dataclasses.replace(contexte, srs="EPSG:2154")
        arguments = _arguments_geojson_vers_gml(avec_srs)
        assert arguments[arguments.index("--srs") + 1] == "EPSG:2154"


# ---------------------------------------------------------------------------
# Registre des etapes
# ---------------------------------------------------------------------------


class TestRegistreEtapes:
    """Coherence du registre ETAPES, point d'extension unique du module."""

    def test_quatre_etapes_declarees(self) -> None:
        assert len(ETAPES) == 4

    def test_cles_uniques(self) -> None:
        assert len({e.cle for e in ETAPES}) == len(ETAPES)

    def test_chaque_mode_possede_un_constructeur(self) -> None:
        for etape in ETAPES:
            assert etape.mode in CONSTRUCTEURS_ARGUMENTS

    def test_chaque_script_existe_sur_disque(self) -> None:
        """Garde-fou : un script deplace ou renomme casse ce test, pas la production."""
        for etape in ETAPES:
            assert (RACINE / etape.script).is_file(), etape.script

    def test_ordre_des_etapes(self) -> None:
        """L'ordre porte la dependance de donnees : il ne doit pas changer par accident."""
        assert [e.cle for e in ETAPES] == [
            "conversion_entrante",
            "controle",
            "longueurs",
            "conversion_sortante",
        ]

    def test_seules_les_etapes_a_rapport_json_sont_analysees(self) -> None:
        """Seuls pipeline_globale et pipeline.py serialisent un rapport JSON."""
        assert {e.cle for e in ETAPES if e.sortie_json} == {"controle", "longueurs"}


# ---------------------------------------------------------------------------
# Analyse de la sortie standard
# ---------------------------------------------------------------------------


class TestAnalyserSortieJson:
    """Extraction du rapport JSON emis par une etape."""

    def test_json_pur(self) -> None:
        assert _analyser_sortie_json('{"succes": true}') == {"succes": True}

    def test_json_precede_de_texte_de_progression(self) -> None:
        assert _analyser_sortie_json('Lecture du fichier...\n{"succes": true}') == {"succes": True}

    def test_texte_sans_json_retourne_none(self) -> None:
        assert _analyser_sortie_json("Conversion terminee") is None

    def test_chaine_vide_retourne_none(self) -> None:
        assert _analyser_sortie_json("") is None

    def test_json_invalide_retourne_none(self) -> None:
        assert _analyser_sortie_json('{"succes": ') is None

    def test_liste_json_sans_accolade_retourne_none(self) -> None:
        """Aucune accolade dans le texte : rien a analyser."""
        assert _analyser_sortie_json("[1, 2, 3]") is None

    def test_objet_imbrique_dans_une_liste_retourne_none(self) -> None:
        """L'analyse part de la premiere accolade : le fragment '{...}]' est invalide."""
        assert _analyser_sortie_json('[{"succes": true}]') is None


# ---------------------------------------------------------------------------
# Motif d'echec et trace
# ---------------------------------------------------------------------------


class TestMotifEchec:
    """Derivation du motif d'echec depuis les flux du sous-processus."""

    def test_stderr_est_prioritaire(self) -> None:
        processus = _processus(1, stdout="sortie", stderr="Erreur: fichier absent")
        assert _motif_echec(processus) == "Erreur: fichier absent"

    def test_derniere_ligne_utile_retenue(self) -> None:
        processus = _processus(1, stderr="Traceback...\n  File ...\nValueError: x\n\n")
        assert _motif_echec(processus) == "ValueError: x"

    def test_repli_sur_stdout_si_stderr_vide(self) -> None:
        processus = _processus(1, stdout="Echec de la conversion", stderr="   \n")
        assert _motif_echec(processus) == "Echec de la conversion"

    def test_repli_sur_code_retour_si_flux_vides(self) -> None:
        assert _motif_echec(_processus(3)) == "Code de retour 3"


class TestTronquerTrace:
    """Bornage de la trace conservee dans le rapport."""

    def test_stderr_vide_retourne_none(self) -> None:
        assert _tronquer_trace(_processus(1, stderr="  \n ")) is None

    def test_trace_courte_conservee_entierement(self) -> None:
        assert _tronquer_trace(_processus(1, stderr="ValueError: x")) == "ValueError: x"

    def test_trace_longue_tronquee_a_la_fin(self) -> None:
        """La fin de la trace porte l'exception : c'est elle qu'on conserve."""
        trace = "a" * (TAILLE_MAX_TRACE + 500) + "FIN"
        resultat = _tronquer_trace(_processus(1, stderr=trace))
        assert resultat is not None
        assert len(resultat) == TAILLE_MAX_TRACE
        assert resultat.endswith("FIN")


# ---------------------------------------------------------------------------
# Execution d'une etape
# ---------------------------------------------------------------------------


class TestExecuterEtape:
    """Lecture du resultat d'un sous-processus."""

    def test_script_introuvable_signale_sans_lancer_de_processus(
        self,
        contexte: ContexteOrchestration,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def refuser(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("aucun sous-processus ne doit etre lance")

        monkeypatch.setattr(subprocess, "run", refuser)
        etape = EtapePipeline("x", "X", "chemin/inexistant.py", "gml_vers_geojson")
        resultat = executer_etape(etape, contexte)
        assert not resultat.execute
        assert resultat.motif is not None
        assert "introuvable" in resultat.motif

    def test_code_retour_non_nul_est_un_echec(
        self,
        contexte: ContexteOrchestration,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _processus(1, stderr="Erreur: GML invalide"))
        resultat = executer_etape(ETAPES[0], contexte)
        assert not resultat.execute
        assert resultat.code_retour == 1
        assert resultat.motif == "Erreur: GML invalide"

    def test_code_retour_nul_est_un_succes(
        self,
        contexte: ContexteOrchestration,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _processus(0, stdout="Conversion terminee"))
        resultat = executer_etape(ETAPES[0], contexte)
        assert resultat.execute
        assert resultat.code_retour == 0
        # L'etape 1 n'emet pas de JSON : aucun rapport n'est attendu.
        assert resultat.rapport is None

    def test_rapport_json_est_repris(
        self,
        contexte: ContexteOrchestration,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sortie = json.dumps({"succes": True, "nombre_anomalies": 7})
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _processus(0, stdout=sortie))
        resultat = executer_etape(ETAPES[1], contexte)
        assert resultat.execute
        assert resultat.rapport is not None
        assert resultat.rapport["nombre_anomalies"] == 7

    def test_code_retour_nul_mais_succes_faux_est_un_echec(
        self,
        contexte: ContexteOrchestration,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cas limite central : pipeline_globale et pipeline.py sortent avec 0 en echec.

        Se fier au seul code de retour declarerait l'etape reussie et laisserait
        les etapes suivantes travailler sur des donnees absentes.
        """
        sortie = json.dumps({"succes": False, "erreur": "Repertoire introuvable"})
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _processus(0, stdout=sortie))
        resultat = executer_etape(ETAPES[1], contexte)
        assert not resultat.execute
        assert resultat.motif == "Repertoire introuvable"
        assert resultat.rapport is not None

    def test_succes_absent_du_rapport_ne_declasse_pas_l_etape(
        self,
        contexte: ContexteOrchestration,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Un rapport sans champ "succes" reste un succes : le code de retour tranche."""
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _processus(0, stdout='{"nb_cables": 3}'))
        resultat = executer_etape(ETAPES[2], contexte)
        assert resultat.execute

    def test_interpreteur_courant_est_utilise(
        self,
        contexte: ContexteOrchestration,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """sys.executable garantit que le virtualenv Poetry actif est celui du sous-processus."""
        commandes: list[list[str]] = []

        def capturer(commande: list[str], **_kwargs: Any) -> "subprocess.CompletedProcess[str]":
            commandes.append(commande)
            return _processus(0)

        monkeypatch.setattr(subprocess, "run", capturer)
        executer_etape(ETAPES[0], contexte)
        assert commandes[0][0] == sys.executable
        assert commandes[0][1].endswith("recostar_to_geojson.py")


# ---------------------------------------------------------------------------
# Politique d'arret
# ---------------------------------------------------------------------------


class TestInterrompreApres:
    """Politique d'arret du pipeline."""

    def test_echec_interrompt(self) -> None:
        assert _interrompre_apres(ResultatEtape("x", "X", execute=False))

    def test_succes_n_interrompt_pas(self) -> None:
        assert not _interrompre_apres(ResultatEtape("x", "X", execute=True))


# ---------------------------------------------------------------------------
# Orchestration complete
# ---------------------------------------------------------------------------


def _substituer_executer_etape(
    monkeypatch: pytest.MonkeyPatch,
    cles_en_echec: set[str],
) -> list[str]:
    """Substitue executer_etape et retourne la liste des cles effectivement appelees."""
    import pipeline_complet

    appelees: list[str] = []

    def faux(etape: EtapePipeline, _contexte: ContexteOrchestration) -> ResultatEtape:
        appelees.append(etape.cle)
        return ResultatEtape(etape.cle, etape.libelle, execute=etape.cle not in cles_en_echec, duree_s=0.5)

    monkeypatch.setattr(pipeline_complet, "executer_etape", faux)
    return appelees


class TestExecuterPipeline:
    """Enchainement des etapes et assemblage du rapport global."""

    def test_gml_introuvable_court_circuite_tout(self, tmp_path: Path) -> None:
        rapport = executer_pipeline(str(tmp_path / "absent.gml"))
        assert not rapport["succes"]
        assert rapport["etapes"] == {}

    def test_toutes_les_etapes_reussissent(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        appelees = _substituer_executer_etape(monkeypatch, set())
        rapport = executer_pipeline(str(gml_source), sortie=str(tmp_path / "t"))
        assert rapport["succes"]
        assert len(appelees) == 4
        assert rapport["etapes_executees"] == 4
        assert rapport["etapes_ignorees"] == []

    def test_echec_premiere_etape_ignore_les_suivantes(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        appelees = _substituer_executer_etape(monkeypatch, {"conversion_entrante"})
        rapport = executer_pipeline(str(gml_source), sortie=str(tmp_path / "t"))
        assert not rapport["succes"]
        assert appelees == ["conversion_entrante"]
        assert rapport["etapes_ignorees"] == ["controle", "longueurs", "conversion_sortante"]

    def test_echec_etape_intermediaire_arrete_le_pipeline(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        appelees = _substituer_executer_etape(monkeypatch, {"longueurs"})
        rapport = executer_pipeline(str(gml_source), sortie=str(tmp_path / "t"))
        assert not rapport["succes"]
        assert appelees == ["conversion_entrante", "controle", "longueurs"]
        assert rapport["etapes_ignorees"] == ["conversion_sortante"]

    def test_duree_totale_agregee(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _substituer_executer_etape(monkeypatch, set())
        rapport = executer_pipeline(str(gml_source), sortie=str(tmp_path / "t"))
        assert rapport["duree_totale_s"] == pytest.approx(2.0)

    def test_rapport_ecrit_sur_disque(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _substituer_executer_etape(monkeypatch, set())
        racine = tmp_path / "t"
        rapport = executer_pipeline(str(gml_source), sortie=str(racine))
        chemin = racine / FICHIER_RAPPORT
        assert chemin.is_file()
        assert rapport["rapport_pipeline"] == str(chemin)

    def test_rapport_relu_est_coherent(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Le fichier persiste doit etre relisible et refleter le resultat en memoire."""
        _substituer_executer_etape(monkeypatch, {"controle"})
        racine = tmp_path / "t"
        rapport = executer_pipeline(str(gml_source), sortie=str(racine))
        relu = json.loads((racine / FICHIER_RAPPORT).read_text(encoding="utf-8"))
        assert relu["succes"] is False
        assert relu["etapes_executees"] == rapport["etapes_executees"]
        assert set(relu["etapes"]) == {"conversion_entrante", "controle"}

    def test_chemins_reportes_dans_le_rapport(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _substituer_executer_etape(monkeypatch, set())
        racine = tmp_path / "t"
        rapport = executer_pipeline(str(gml_source), sortie=str(racine))
        assert rapport["gml_entree"] == str(gml_source.resolve())
        assert rapport["dossier_geojson"] == str((racine / "geojson").resolve())


# ---------------------------------------------------------------------------
# Traitement par lot
# ---------------------------------------------------------------------------


@pytest.fixture
def dossier_lot(tmp_path: Path) -> Path:
    """Dossier de livraison contenant trois GML et un fichier a ignorer."""
    dossier = tmp_path / "livraison"
    dossier.mkdir()
    for nom in ("beta.gml", "alpha.gml", "gamma.GML"):
        (dossier / nom).write_text("<gml/>", encoding="utf-8")
    (dossier / "lisez_moi.txt").write_text("ignore", encoding="utf-8")
    (dossier / "sous_dossier").mkdir()
    return dossier


def _substituer_executer_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    noms_en_echec: set[str],
) -> list[tuple[str, str]]:
    """Substitue executer_pipeline et retourne les couples (gml, sortie) appeles."""
    import pipeline_complet

    appels: list[tuple[str, str]] = []

    def faux(
        gml_entree: str,
        sortie: str | None = None,
        _gml_sortie: str | None = None,
        _numero_affaire: str | None = None,
        _srs: str | None = None,
        commentaire_vide: bool = False,
    ) -> dict[str, Any]:
        appels.append((gml_entree, sortie or ""))
        return {
            "succes": Path(gml_entree).stem not in noms_en_echec,
            "sortie": sortie,
            "commentaire_vide": commentaire_vide,
        }

    monkeypatch.setattr(pipeline_complet, "executer_pipeline", faux)
    return appels


class TestListerGmlDuLot:
    """Selection des fichiers d'un dossier de lot."""

    def test_seuls_les_gml_sont_retenus(self, dossier_lot: Path) -> None:
        noms = [chemin.name for chemin in lister_gml_du_lot(dossier_lot)]
        assert "lisez_moi.txt" not in noms
        assert len(noms) == 3

    def test_extension_insensible_a_la_casse(self, dossier_lot: Path) -> None:
        assert "gamma.GML" in [chemin.name for chemin in lister_gml_du_lot(dossier_lot)]

    def test_ordre_alphabetique_reproductible(self, dossier_lot: Path) -> None:
        noms = [chemin.name for chemin in lister_gml_du_lot(dossier_lot)]
        assert noms == sorted(noms)

    def test_sous_dossiers_ignores(self, tmp_path: Path) -> None:
        """Un repertoire nomme *.gml ne doit pas etre pris pour un fichier."""
        dossier = tmp_path / "lot"
        (dossier / "piege.gml").mkdir(parents=True)
        assert lister_gml_du_lot(dossier) == []

    def test_dossier_vide_retourne_liste_vide(self, tmp_path: Path) -> None:
        dossier = tmp_path / "vide"
        dossier.mkdir()
        assert lister_gml_du_lot(dossier) == []


class TestExecuterLot:
    """Orchestration d'un lot de GML."""

    def test_dossier_introuvable(self, tmp_path: Path) -> None:
        rapport = executer_lot(str(tmp_path / "absent"))
        assert not rapport["succes"]
        assert rapport["traitements"] == {}

    def test_fichier_passe_comme_lot_est_refuse(self, gml_source: Path) -> None:
        rapport = executer_lot(str(gml_source))
        assert not rapport["succes"]

    def test_dossier_sans_gml(self, tmp_path: Path) -> None:
        dossier = tmp_path / "vide"
        dossier.mkdir()
        rapport = executer_lot(str(dossier))
        assert not rapport["succes"]
        assert "Aucun fichier GML" in rapport["erreur"]

    def test_chaque_gml_est_traite(
        self,
        dossier_lot: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        appels = _substituer_executer_pipeline(monkeypatch, set())
        rapport = executer_lot(str(dossier_lot), sortie=str(tmp_path / "res"))
        assert rapport["succes"]
        assert rapport["nombre_gml"] == 3
        assert len(appels) == 3

    def test_un_sous_dossier_par_gml(
        self,
        dossier_lot: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        appels = _substituer_executer_pipeline(monkeypatch, set())
        racine = tmp_path / "res"
        executer_lot(str(dossier_lot), sortie=str(racine))
        sorties = {Path(sortie).name for _, sortie in appels}
        assert sorties == {"alpha", "beta", "gamma"}
        assert all(Path(sortie).parent == racine for _, sortie in appels)

    def test_echec_n_interrompt_pas_le_lot(
        self,
        dossier_lot: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Les recolements sont independants : les suivants doivent etre traites."""
        appels = _substituer_executer_pipeline(monkeypatch, {"alpha"})
        rapport = executer_lot(str(dossier_lot), sortie=str(tmp_path / "res"))
        assert len(appels) == 3
        assert not rapport["succes"]
        assert rapport["nombre_echoues"] == 1
        assert rapport["nombre_reussis"] == 2
        assert rapport["gml_en_echec"] == ["alpha"]

    def test_rapports_individuels_conserves(
        self,
        dossier_lot: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _substituer_executer_pipeline(monkeypatch, {"beta"})
        rapport = executer_lot(str(dossier_lot), sortie=str(tmp_path / "res"))
        assert set(rapport["traitements"]) == {"alpha", "beta", "gamma"}
        assert rapport["traitements"]["beta"]["succes"] is False

    def test_options_propagees_a_chaque_gml(
        self,
        dossier_lot: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _substituer_executer_pipeline(monkeypatch, set())
        rapport = executer_lot(
            str(dossier_lot),
            sortie=str(tmp_path / "res"),
            numero_affaire="123",
            srs="EPSG:2154",
            commentaire_vide=True,
        )
        assert all(t["commentaire_vide"] is True for t in rapport["traitements"].values())

    def test_sortie_par_defaut_dans_le_dossier_de_lot(
        self,
        dossier_lot: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _substituer_executer_pipeline(monkeypatch, set())
        rapport = executer_lot(str(dossier_lot))
        assert rapport["sortie"] == str(dossier_lot / DOSSIER_TRAVAIL_DEFAUT)

    def test_radicaux_homonymes_ne_s_ecrasent_pas(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reseau.gml et Reseau.GML partagent leur radical : deux dossiers distincts."""
        dossier = tmp_path / "lot"
        dossier.mkdir()
        (dossier / "Reseau.gml").write_text("<gml/>", encoding="utf-8")
        (dossier / "Reseau.GML").write_text("<gml/>", encoding="utf-8")
        appels = _substituer_executer_pipeline(monkeypatch, set())
        rapport = executer_lot(str(dossier), sortie=str(tmp_path / "res"))
        assert rapport["nombre_gml"] == 2
        assert len({sortie for _, sortie in appels}) == 2
        assert set(rapport["traitements"]) == {"Reseau", "Reseau_2"}

    def test_rapport_de_lot_ecrit_sur_disque(
        self,
        dossier_lot: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _substituer_executer_pipeline(monkeypatch, set())
        racine = tmp_path / "res"
        rapport = executer_lot(str(dossier_lot), sortie=str(racine))
        chemin = racine / FICHIER_RAPPORT_LOT
        assert chemin.is_file()
        assert rapport["rapport_lot"] == str(chemin)
        relu = json.loads(chemin.read_text(encoding="utf-8"))
        assert relu["nombre_gml"] == 3
        assert relu["mode"] == "lot"


# ---------------------------------------------------------------------------
# Serialisation du resultat d'etape
# ---------------------------------------------------------------------------


class TestResultatEtapeVersDict:
    """Serialisation d'un resultat d'etape."""

    def test_champs_toujours_presents(self) -> None:
        donnees = ResultatEtape("x", "X", execute=True, code_retour=0, duree_s=1.5).vers_dict()
        assert donnees == {"libelle": "X", "execute": True, "code_retour": 0, "duree_s": 1.5}

    def test_champs_optionnels_omis_si_absents(self) -> None:
        donnees = ResultatEtape("x", "X").vers_dict()
        assert "motif" not in donnees
        assert "rapport" not in donnees
        assert "trace" not in donnees

    def test_champs_optionnels_presents_si_renseignes(self) -> None:
        donnees = ResultatEtape(
            "x",
            "X",
            motif="echec",
            rapport={"succes": False},
            trace="ValueError",
        ).vers_dict()
        assert donnees["motif"] == "echec"
        assert donnees["rapport"] == {"succes": False}
        assert donnees["trace"] == "ValueError"


# ---------------------------------------------------------------------------
# Point d'entree CLI
# ---------------------------------------------------------------------------


class TestMain:
    """Code de sortie du CLI : contrat sur lequel un appelant CI s'appuie."""

    def test_succes_sort_sans_erreur(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _substituer_executer_etape(monkeypatch, set())
        monkeypatch.setattr(
            sys,
            "argv",
            ["pipeline_complet.py", "--gml", str(gml_source), "--sortie", str(tmp_path / "t")],
        )
        main()
        assert json.loads(capsys.readouterr().out)["succes"] is True

    def test_echec_sort_avec_le_code_1(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _substituer_executer_etape(monkeypatch, {"controle"})
        monkeypatch.setattr(
            sys,
            "argv",
            ["pipeline_complet.py", "--gml", str(gml_source), "--sortie", str(tmp_path / "t")],
        )
        with pytest.raises(SystemExit) as sortie:
            main()
        assert sortie.value.code == 1
        assert json.loads(capsys.readouterr().out)["succes"] is False

    def test_source_manquante_est_refusee_par_argparse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--gml ou --lot est requis : argparse sort avec le code 2."""
        monkeypatch.setattr(sys, "argv", ["pipeline_complet.py"])
        with pytest.raises(SystemExit) as sortie:
            main()
        assert sortie.value.code == 2

    def test_gml_et_lot_sont_exclusifs(self, gml_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            ["pipeline_complet.py", "--gml", str(gml_source), "--lot", str(tmp_path)],
        )
        with pytest.raises(SystemExit) as sortie:
            main()
        assert sortie.value.code == 2

    def test_gml_sortie_incompatible_avec_lot(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Un lot produit un GML par recolement : un nom unique ne peut les designer tous."""
        monkeypatch.setattr(
            sys,
            "argv",
            ["pipeline_complet.py", "--lot", str(tmp_path), "--gml-sortie", str(tmp_path / "x.gml")],
        )
        with pytest.raises(SystemExit) as sortie:
            main()
        assert sortie.value.code == 2

    def test_commentaire_transmis_au_pipeline(
        self,
        gml_source: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        import pipeline_complet

        recus: dict[str, Any] = {}

        def faux(*arguments: Any) -> dict[str, Any]:
            recus["commentaire_vide"] = arguments[5]
            return {"succes": True}

        monkeypatch.setattr(pipeline_complet, "executer_pipeline", faux)
        monkeypatch.setattr(
            sys,
            "argv",
            ["pipeline_complet.py", "--gml", str(gml_source), "--commentaire"],
        )
        main()
        capsys.readouterr()
        assert recus["commentaire_vide"] is True

    def test_mode_lot_appelle_executer_lot(
        self,
        dossier_lot: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _substituer_executer_pipeline(monkeypatch, set())
        monkeypatch.setattr(
            sys,
            "argv",
            ["pipeline_complet.py", "--lot", str(dossier_lot), "--sortie", str(tmp_path / "res")],
        )
        main()
        rapport = json.loads(capsys.readouterr().out)
        assert rapport["mode"] == "lot"
        assert rapport["nombre_gml"] == 3

    def test_lot_en_echec_sort_avec_le_code_1(
        self,
        dossier_lot: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _substituer_executer_pipeline(monkeypatch, {"alpha"})
        monkeypatch.setattr(
            sys,
            "argv",
            ["pipeline_complet.py", "--lot", str(dossier_lot), "--sortie", str(tmp_path / "res")],
        )
        with pytest.raises(SystemExit) as sortie:
            main()
        assert sortie.value.code == 1
        assert json.loads(capsys.readouterr().out)["nombre_echoues"] == 1
