"""
Tests du registre des familles et de la pipeline globale.

Couvre :
  - l'integrite du registre (dossiers, pipelines et libelles declares)
  - la derivation du code et du libelle d'un controle
  - la resolution du fichier GML (explicite, automatique, ambigu, absent)
  - l'execution globale : arborescence, rapports, familles non executees
  - la generation du rapport PDF
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from familles_controle import (
    FAMILLES,
    LIBELLES_CONTROLES,
    MODE_GML,
    MODE_REPERTOIRE,
    RACINE_CONTROLE,
    charger_module_pipeline,
    code_controle,
    famille_par_cle,
    libelle_controle,
)
from pipeline_globale import (
    DOSSIER_CONTROLE,
    FICHIER_RAPPORT_JSON,
    FICHIER_RAPPORT_PDF,
    executer_pipeline,
    resoudre_chemin_gml,
)
from rapport_pdf import generer_rapport_pdf
from synthese_controles import (
    PRIORITE_BLOQUANT,
    STATUT_NON_EXECUTE,
    ResultatControle,
    ResultatFamille,
    agreger,
)

# --------------------------------------------------------------------------- #
# Registre des familles
# --------------------------------------------------------------------------- #


class TestRegistreFamilles:
    """Tests d'integrite du registre declaratif."""

    def test_familles_declarees(self) -> None:
        cles = {f.cle for f in FAMILLES}
        assert cles == {"structuration", "projection", "altimetrie", "cheminement", "cable"}

    def test_cles_uniques(self) -> None:
        cles = [f.cle for f in FAMILLES]
        assert len(cles) == len(set(cles))

    def test_dossiers_sources_existent(self) -> None:
        for famille in FAMILLES:
            assert (RACINE_CONTROLE / famille.dossier).is_dir(), famille.cle

    def test_modules_pipeline_existent(self) -> None:
        for famille in FAMILLES:
            chemin = RACINE_CONTROLE / famille.dossier / f"{famille.module_pipeline}.py"
            assert chemin.is_file(), famille.cle

    def test_modes_valides(self) -> None:
        for famille in FAMILLES:
            assert famille.mode in {MODE_REPERTOIRE, MODE_GML}, famille.cle

    def test_pipelines_exposent_executer_pipeline(self) -> None:
        """Contrat commun a toutes les familles, quel que soit leur mode."""
        for famille in FAMILLES:
            module = charger_module_pipeline(famille.cle)
            assert callable(module.executer_pipeline), famille.cle

    def test_tous_les_controles_ont_un_libelle(self) -> None:
        """Aucun controle du projet ne doit apparaitre sans libelle dans le PDF."""
        manquants: list[str] = []
        for famille in FAMILLES:
            module = charger_module_pipeline(famille.cle)
            for cle in module.NOMS_CONTROLES:
                if cle not in LIBELLES_CONTROLES:
                    manquants.append(f"{famille.cle}:{cle}")
        assert manquants == [], f"Libelles manquants : {manquants}"

    def test_aucun_libelle_orphelin(self) -> None:
        """Le registre ne declare pas de libelle pour un controle inexistant."""
        declares = set()
        for famille in FAMILLES:
            declares.update(charger_module_pipeline(famille.cle).NOMS_CONTROLES)
        assert set(LIBELLES_CONTROLES) - declares == set()

    def test_famille_par_cle(self) -> None:
        assert famille_par_cle("cable").libelle == "Câble"

    def test_famille_inconnue(self) -> None:
        with pytest.raises(KeyError):
            famille_par_cle("inexistante")

    def test_module_mis_en_cache(self) -> None:
        assert charger_module_pipeline("cable") is charger_module_pipeline("cable")


class TestCodeEtLibelle:
    """Tests de code_controle et libelle_controle."""

    def test_code_convention_geojson(self) -> None:
        assert code_controle("controle_e200") == "E200"

    def test_code_convention_xsd(self) -> None:
        assert code_controle("E110") == "E110"

    def test_libelle_declare(self) -> None:
        assert libelle_controle("controle_e506") == "Raccordement des câbles aux nœuds du réseau"

    def test_libelle_absent_retombe_sur_le_code(self) -> None:
        assert libelle_controle("controle_e999") == "E999"


# --------------------------------------------------------------------------- #
# Resolution du fichier GML
# --------------------------------------------------------------------------- #


class TestResoudreCheminGml:
    """Tests de resoudre_chemin_gml."""

    def test_chemin_explicite(self, tmp_path: Path) -> None:
        gml = tmp_path / "donnees.gml"
        gml.write_text("<gml/>", encoding="utf-8")
        chemin, motif = resoudre_chemin_gml(tmp_path, gml)
        assert chemin == gml.resolve()
        assert motif is None

    def test_chemin_explicite_introuvable(self, tmp_path: Path) -> None:
        chemin, motif = resoudre_chemin_gml(tmp_path, tmp_path / "absent.gml")
        assert chemin is None
        assert motif is not None and "introuvable" in motif

    def test_detection_automatique_si_unique(self, tmp_path: Path) -> None:
        gml = tmp_path / "unique.gml"
        gml.write_text("<gml/>", encoding="utf-8")
        chemin, motif = resoudre_chemin_gml(tmp_path, None)
        assert chemin == gml
        assert motif is None

    def test_plusieurs_gml_aucun_choix_arbitraire(self, tmp_path: Path) -> None:
        (tmp_path / "a.gml").write_text("<gml/>", encoding="utf-8")
        (tmp_path / "b.gml").write_text("<gml/>", encoding="utf-8")
        chemin, motif = resoudre_chemin_gml(tmp_path, None)
        assert chemin is None
        assert motif is not None and "--gml" in motif

    def test_aucun_gml(self, tmp_path: Path) -> None:
        chemin, motif = resoudre_chemin_gml(tmp_path, None)
        assert chemin is None
        assert motif == "Aucun fichier GML dans le repertoire"


# --------------------------------------------------------------------------- #
# Execution globale
# --------------------------------------------------------------------------- #


def _ecrire_geojson(chemin: Path, features: list[dict[str, Any]]) -> None:
    """Ecrit un FeatureCollection minimal."""
    chemin.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def jeu_minimal(tmp_path: Path) -> Path:
    """Jeu de donnees GeoJSON minimal, sans GML."""
    _ecrire_geojson(
        tmp_path / "RPD_CableElectrique_Reco.geojson",
        [
            {
                "type": "Feature",
                "properties": {"id": "c1", "Statut": "Commissioned"},
                "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
            }
        ],
    )
    return tmp_path


class TestExecuterPipeline:
    """Tests de executer_pipeline."""

    def test_repertoire_introuvable(self, tmp_path: Path) -> None:
        resultat = executer_pipeline(str(tmp_path / "absent"))
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_arborescence_creee(self, jeu_minimal: Path) -> None:
        """Un sous-dossier par famille, dans le dossier controle/."""
        executer_pipeline(str(jeu_minimal))
        dossier = jeu_minimal / DOSSIER_CONTROLE
        assert dossier.is_dir()
        for famille in FAMILLES:
            if famille.mode == MODE_GML:
                continue  # aucun GML dans ce jeu : famille non executee
            assert (dossier / famille.sortie).is_dir(), famille.cle

    def test_rapports_produits(self, jeu_minimal: Path) -> None:
        resultat = executer_pipeline(str(jeu_minimal))
        assert resultat["succes"] is True
        assert os.path.isfile(resultat["rapport_pdf"])
        assert os.path.isfile(resultat["rapport_json"])
        assert Path(resultat["rapport_pdf"]).name == FICHIER_RAPPORT_PDF
        assert Path(resultat["rapport_json"]).name == FICHIER_RAPPORT_JSON

    def test_structuration_non_executee_sans_gml(self, jeu_minimal: Path) -> None:
        """L'absence de GML n'empeche pas les autres familles."""
        resultat = executer_pipeline(str(jeu_minimal))
        structuration = resultat["familles"]["structuration"]
        assert structuration["execute"] is False
        assert structuration["statut"] == STATUT_NON_EXECUTE
        assert "Aucun fichier GML" in structuration["motif"]

    def test_toutes_les_familles_presentes(self, jeu_minimal: Path) -> None:
        resultat = executer_pipeline(str(jeu_minimal))
        assert set(resultat["familles"]) == {f.cle for f in FAMILLES}

    def test_familles_geojson_executees(self, jeu_minimal: Path) -> None:
        resultat = executer_pipeline(str(jeu_minimal))
        for cle in ("altimetrie", "cheminement", "cable"):
            assert resultat["familles"][cle]["execute"] is True, cle
            assert resultat["familles"][cle]["nombre_controles"] > 0, cle

    def test_rapport_json_relisible(self, jeu_minimal: Path) -> None:
        resultat = executer_pipeline(str(jeu_minimal))
        with open(resultat["rapport_json"], encoding="utf-8") as fichier:
            rapport = json.load(fichier)
        assert rapport["statut_global"] in {"Conforme", "Non conforme", "Incomplet"}
        assert isinstance(rapport["familles_non_conformes"], list)
        assert isinstance(rapport["familles_incompletes"], list)

    def test_sortie_distincte(self, jeu_minimal: Path, tmp_path: Path) -> None:
        """Le dossier controle/ peut etre cree hors du repertoire des donnees."""
        sortie = tmp_path / "ailleurs"
        resultat = executer_pipeline(str(jeu_minimal), str(sortie))
        assert (sortie / DOSSIER_CONTROLE).is_dir()
        assert resultat["dossier_controle"] == str(sortie / DOSSIER_CONTROLE)

    def test_numero_affaire_transmis_a_projection(self, jeu_minimal: Path) -> None:
        """Sans numero d'affaire, E303 ne peut pas s'executer ; avec, il s'execute."""
        sans = executer_pipeline(str(jeu_minimal))
        codes_en_echec = set(sans["familles"]["projection"]["controles_en_echec"])
        assert "E303" in codes_en_echec

        avec = executer_pipeline(str(jeu_minimal), numero_affaire="RAC-ABC-12-345678")
        controles = {c["code"]: c for c in avec["familles"]["projection"]["controles"]}
        assert controles["E303"]["erreur"] != "Parametre --numero_affaire requis"

    def test_gml_explicite_execute_la_structuration(self, jeu_minimal: Path) -> None:
        gml = jeu_minimal / "donnees.gml"
        gml.write_text("<?xml version='1.0'?><root/>", encoding="utf-8")
        resultat = executer_pipeline(str(jeu_minimal), chemin_gml=str(gml))
        assert resultat["familles"]["structuration"]["execute"] is True


# --------------------------------------------------------------------------- #
# Rapport PDF
# --------------------------------------------------------------------------- #


class TestGenererRapportPdf:
    """Tests de generer_rapport_pdf."""

    def _familles(self) -> tuple[ResultatFamille, ...]:
        """Jeu de familles couvrant les trois statuts."""
        return (
            ResultatFamille(
                "cable",
                "Câble",
                (
                    ResultatControle("E500", "Cohérence du DomaineTension", True, 0, {}),
                    ResultatControle("E506", "Raccordement", True, 3, {PRIORITE_BLOQUANT: 3}),
                ),
            ),
            ResultatFamille(
                "projection",
                "Projection",
                (ResultatControle("E303", "Emprise DR", False, 0, {}, "Parametre requis"),),
            ),
            ResultatFamille("structuration", "Structuration", execute=False, motif="Aucun GML"),
        )

    def test_pdf_genere(self, tmp_path: Path) -> None:
        familles = self._familles()
        chemin = tmp_path / "rapport.pdf"
        generer_rapport_pdf(familles, agreger(familles), chemin, tmp_path)
        assert chemin.is_file()
        assert chemin.stat().st_size > 1000

    def test_pdf_valide(self, tmp_path: Path) -> None:
        """L'en-tete PDF doit etre presente et le document non vide."""
        familles = self._familles()
        chemin = tmp_path / "rapport.pdf"
        generer_rapport_pdf(familles, agreger(familles), chemin, tmp_path)
        contenu = chemin.read_bytes()
        assert contenu.startswith(b"%PDF-")
        assert contenu.rstrip().endswith(b"%%EOF")

    def test_pdf_sans_aucune_anomalie(self, tmp_path: Path) -> None:
        familles = (ResultatFamille("cable", "Câble", (ResultatControle("E500", "Libelle", True, 0, {}),)),)
        chemin = tmp_path / "rapport.pdf"
        generer_rapport_pdf(familles, agreger(familles), chemin, tmp_path)
        assert chemin.is_file()

    def test_pdf_sans_famille(self, tmp_path: Path) -> None:
        """Cas limite : aucun resultat a presenter."""
        chemin = tmp_path / "rapport.pdf"
        generer_rapport_pdf((), agreger(()), chemin, tmp_path)
        assert chemin.is_file()
