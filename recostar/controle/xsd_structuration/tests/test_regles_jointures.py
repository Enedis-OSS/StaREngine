"""
Tests des deux contrôles portant sur les tables de jointure :
E0116 / E0016 (doublons, E-0012) et E0117 / E0017 (champ manquant, E-0013).

Couvre :
  - la lecture d'un bout de jointure, forme fragmentée comprise
  - l'identité d'un lien : le couple de ses bouts, sans ses annotations
  - la détection des couples déclarés plus d'une fois
  - l'indépendance des trois tables entre elles
  - le relevé des bouts non renseignés et l'exclusivité des deux règles
  - le rapport JSON et l'identité du contrôle selon la version
"""

import json
from pathlib import Path
from typing import Any

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element  # nosec B405

import defusedxml.ElementTree as DefusedET  # type: ignore

from recostar.controle.xsd_structuration.codes_controle import (
    RANG_JOINTURES,
    RANG_JOINTURES_CHAMPS,
    identite_controle,
)
from recostar.controle.xsd_structuration.codes_verificateur_xsd import resoudre_code_erreur_xsd
from recostar.controle.xsd_structuration.e0116 import AnalyseurJointures, generer_rapport
from recostar.controle.xsd_structuration.e0117 import AnalyseurChampsJointure
from recostar.controle.xsd_structuration.e0117 import generer_rapport as generer_rapport_champs
from recostar.controle.xsd_structuration.priorites_structuration import PRIORITE_FORTE
from recostar.controle.xsd_structuration.regles_jointures import (
    CODE_CHAMP_MANQUANT,
    CODE_DOUBLON,
    SANS_REFERENCE,
    TABLES_JOINTURE,
    TABLES_PAR_TYPE,
    champs_manquants,
    compter_couples,
    couple_jointure,
    detecter_champs_manquants,
    detecter_doublons,
    reference_bout,
)
from recostar.controle.xsd_structuration.versions.v1_0 import PROFIL_V1_0

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_ENTETE: str = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2"'
    ' xmlns:RecoStaR="http://StaR-Elec.com"'
    ' xmlns:xlink="http://www.w3.org/1999/xlink">'
)

_MEMBRE: str = """  <gml:featureMember>
    <RecoStaR:{type_rpd}>
      <RecoStaR:{source} xlink:href="{ref_source}"/>
      <RecoStaR:{cible} xlink:href="{ref_cible}"/>
    </RecoStaR:{type_rpd}>
  </gml:featureMember>"""


def _jointure(
    type_rpd: str = "Ouvrage_Materiel",
    ref_source: str = "j1",
    ref_cible: str = "m1",
) -> str:
    table = TABLES_PAR_TYPE[type_rpd]
    return _MEMBRE.format(
        type_rpd=type_rpd,
        source=table.bout_source,
        cible=table.bout_cible,
        ref_source=ref_source,
        ref_cible=ref_cible,
    )


def _ecrire_gml(tmp_path: Any, membres: list[str], nom: str = "recolement.gml") -> Path:
    chemin = tmp_path / nom
    chemin.write_text(f"{_ENTETE}\n" + "\n".join(membres) + "\n</gml:FeatureCollection>", encoding="utf-8")
    return chemin


def _element(membre: str) -> Element:
    """Retourne l'objet de jointure porté par un featureMember isolé."""
    racine = DefusedET.fromstring(f"{_ENTETE}\n{membre}\n</gml:FeatureCollection>")
    return list(list(racine)[0])[0]


# --------------------------------------------------------------------------- #
# Les trois tables
# --------------------------------------------------------------------------- #


class TestTablesJointure:
    """Le modèle RecoStaR porte trois tables de jointure."""

    def test_les_trois_tables(self) -> None:
        assert {table.type_rpd for table in TABLES_JOINTURE} == {
            "Ouvrage_Materiel",
            "CableElectrique_NoeudReseau",
            "Cheminement_Cables",
        }

    def test_bouts_declares(self) -> None:
        """Les noms des bouts sont ceux que lit le convertisseur."""
        par_type = {t.type_rpd: (t.bout_source, t.bout_cible) for t in TABLES_JOINTURE}
        assert par_type["Ouvrage_Materiel"] == ("ouvrage", "materiel")
        assert par_type["CableElectrique_NoeudReseau"] == ("cableelectrique", "noeudreseau")
        assert par_type["Cheminement_Cables"] == ("cheminement", "cables")

    def test_index_par_type_complet(self) -> None:
        assert set(TABLES_PAR_TYPE) == {t.type_rpd for t in TABLES_JOINTURE}


# --------------------------------------------------------------------------- #
# Lecture d'un lien
# --------------------------------------------------------------------------- #


class TestReferenceBout:
    """Tests de reference_bout."""

    def test_reference_simple(self) -> None:
        assert reference_bout(_element(_jointure()), "ouvrage") == "j1"

    def test_forme_fragmentee_resolue(self) -> None:
        """Le GML admet « #idXXXX » : les distinguer laisserait passer un doublon."""
        assert reference_bout(_element(_jointure(ref_source="#j1")), "ouvrage") == "j1"

    def test_bout_absent(self) -> None:
        assert reference_bout(_element(_jointure()), "inexistant") is None

    def test_reference_vide(self) -> None:
        assert reference_bout(_element(_jointure(ref_source="  ")), "ouvrage") is None


class TestCoupleJointure:
    """Tests de couple_jointure."""

    def test_couple_complet(self) -> None:
        table = TABLES_PAR_TYPE["Ouvrage_Materiel"]
        assert couple_jointure(_element(_jointure()), table) == ("j1", "m1")

    def test_bout_manquant_ignore(self) -> None:
        """Une jointure incomplète ne décrit aucun lien : elle relève d'E0117."""
        incomplete = (
            "  <gml:featureMember>"
            '<RecoStaR:Ouvrage_Materiel><RecoStaR:ouvrage xlink:href="j1"/></RecoStaR:Ouvrage_Materiel>'
            "</gml:featureMember>"
        )
        assert couple_jointure(_element(incomplete), TABLES_PAR_TYPE["Ouvrage_Materiel"]) is None


# --------------------------------------------------------------------------- #
# Détection des doublons
# --------------------------------------------------------------------------- #


class TestDetecterDoublons:
    """Tests de detecter_doublons."""

    @staticmethod
    def _elements(membres: list[tuple[str, str]]) -> list[tuple[str, Element]]:
        return [(TABLES_PAR_TYPE[t].type_rpd, _element(m)) for t, m in membres]

    def test_lien_unique_conforme(self) -> None:
        assert detecter_doublons(self._elements([("Ouvrage_Materiel", _jointure())])) == []

    def test_doublon_signale(self) -> None:
        elements = self._elements([("Ouvrage_Materiel", _jointure())] * 2)
        erreurs = detecter_doublons(elements)
        assert len(erreurs) == 1
        assert erreurs[0].type_erreur == CODE_DOUBLON
        assert erreurs[0].occurrences == 2
        assert erreurs[0].source == "j1"
        assert erreurs[0].cible == "m1"

    def test_une_anomalie_par_couple(self) -> None:
        """Trois déclarations du même lien sont un seul doublon à corriger."""
        erreurs = detecter_doublons(self._elements([("Ouvrage_Materiel", _jointure())] * 3))
        assert len(erreurs) == 1
        assert erreurs[0].occurrences == 3

    def test_forme_fragmentee_fait_doublon(self) -> None:
        """« #j1 » et « j1 » désignent le même objet."""
        elements = self._elements(
            [
                ("Ouvrage_Materiel", _jointure(ref_source="j1")),
                ("Ouvrage_Materiel", _jointure(ref_source="#j1")),
            ]
        )
        assert len(detecter_doublons(elements)) == 1

    def test_cibles_differentes_conformes(self) -> None:
        elements = self._elements(
            [
                ("Ouvrage_Materiel", _jointure(ref_cible="m1")),
                ("Ouvrage_Materiel", _jointure(ref_cible="m2")),
            ]
        )
        assert detecter_doublons(elements) == []

    def test_tables_differentes_independantes(self) -> None:
        """Deux tables peuvent relier les mêmes identifiants sans faire doublon."""
        elements = self._elements(
            [
                ("Ouvrage_Materiel", _jointure("Ouvrage_Materiel", "a", "b")),
                ("Cheminement_Cables", _jointure("Cheminement_Cables", "a", "b")),
            ]
        )
        assert detecter_doublons(elements) == []

    def test_doublons_multiples(self) -> None:
        elements = self._elements(
            [
                ("Ouvrage_Materiel", _jointure(ref_source="j1")),
                ("Ouvrage_Materiel", _jointure(ref_source="j1")),
                ("Ouvrage_Materiel", _jointure(ref_source="j2")),
                ("Ouvrage_Materiel", _jointure(ref_source="j2")),
            ]
        )
        assert len(detecter_doublons(elements)) == 2

    def test_comptage_par_table(self) -> None:
        elements = self._elements([("Ouvrage_Materiel", _jointure())] * 2)
        assert compter_couples(elements) == {("Ouvrage_Materiel", "j1", "m1"): 2}

    def test_collection_vide(self) -> None:
        assert detecter_doublons([]) == []


class TestErreurJointure:
    """Forme et priorité de l'anomalie."""

    @staticmethod
    def _erreur() -> Any:
        elements = [("Ouvrage_Materiel", _element(_jointure()))] * 2
        return detecter_doublons(elements)[0]

    def test_priorite_forte(self) -> None:
        """E-0012 est « bloquante » au vérificateur, rendu « forte » par la famille."""
        assert self._erreur().priorite == PRIORITE_FORTE

    def test_code_erreur_du_rang(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_JOINTURES, CODE_DOUBLON) == "E-0012"

    def test_identite_tient_lieu_de_gml_id(self) -> None:
        """Une jointure ne porte pas de gml:id : le couple l'identifie."""
        assert self._erreur().gml_id == "j1 -> m1"

    def test_serialisation(self) -> None:
        donnees = self._erreur().vers_dict()
        assert donnees["severite"] == "ERREUR"
        assert donnees["occurrences"] == 2
        assert "déclarée 2 fois" in donnees["message"]


# --------------------------------------------------------------------------- #
# Analyseur et rapport
# --------------------------------------------------------------------------- #


class TestAnalyseurJointures:
    """Parcours d'un document complet."""

    def test_document_conforme(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jointure(ref_cible="m1"), _jointure(ref_cible="m2")])
        assert AnalyseurJointures(chemin).analyser() == []

    def test_doublon_detecte(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jointure(), _jointure()])
        assert len(AnalyseurJointures(chemin).analyser()) == 1

    def test_objets_hors_jointure_ignores(self, tmp_path: Any) -> None:
        """Un objet RPD ordinaire n'est pas une table de jointure."""
        autre = '  <gml:featureMember><RecoStaR:RPD_Coffret_Reco gml:id="k1"/></gml:featureMember>'
        chemin = _ecrire_gml(tmp_path, [autre, autre, _jointure()])
        assert AnalyseurJointures(chemin).analyser() == []

    def test_document_vide(self, tmp_path: Any) -> None:
        chemin = tmp_path / "vide.gml"
        chemin.write_text(f"{_ENTETE}\n</gml:FeatureCollection>", encoding="utf-8")
        assert AnalyseurJointures(chemin).analyser() == []


class TestRapport:
    """Le rapport JSON et l'identité du contrôle selon la version."""

    def test_identite_v1_1(self) -> None:
        identite = identite_controle("1.1", RANG_JOINTURES)
        assert identite.code == "E0116"
        assert identite.type_controle == "E0116_JOINTURES"

    def test_identite_v1_0(self) -> None:
        assert identite_controle(PROFIL_V1_0.code, RANG_JOINTURES).code == "E0016"

    def test_rapport_conforme(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jointure()])
        sortie = generer_rapport(chemin, AnalyseurJointures(chemin).analyser(), tmp_path)
        with open(sortie, encoding="utf-8") as flux:
            rapport = json.load(flux)
        assert rapport["conformite"] == "CONFORME"
        assert rapport["nb_erreurs"] == 0
        assert rapport["type_controle"] == "E0116_JOINTURES"

    def test_rapport_non_conforme(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jointure(), _jointure()])
        sortie = generer_rapport(chemin, AnalyseurJointures(chemin).analyser(), tmp_path)
        with open(sortie, encoding="utf-8") as flux:
            rapport = json.load(flux)
        assert rapport["conformite"] == "NON_CONFORME"
        assert rapport["nb_par_priorite"] == {PRIORITE_FORTE: 1}
        assert rapport["erreurs"][0]["type_rpd"] == "Ouvrage_Materiel"

    def test_nom_du_rapport_suit_la_version(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jointure()])
        sortie = generer_rapport(chemin, [], tmp_path, PROFIL_V1_0.code)
        assert sortie.name.endswith("_controle_e0016.json")


# --------------------------------------------------------------------------- #
# Champs manquants (E0117 / E-0013)
# --------------------------------------------------------------------------- #

_MEMBRE_PARTIEL: str = """  <gml:featureMember>
    <RecoStaR:{type_rpd}>
      <RecoStaR:{bout} xlink:href="{reference}"/>
    </RecoStaR:{type_rpd}>
  </gml:featureMember>"""

_MEMBRE_VIDE: str = """  <gml:featureMember>
    <RecoStaR:{type_rpd}/>
  </gml:featureMember>"""


def _jointure_partielle(bout: str = "ouvrage", reference: str = "j1") -> str:
    """Jointure ne portant qu'un seul de ses deux bouts."""
    return _MEMBRE_PARTIEL.format(type_rpd="Ouvrage_Materiel", bout=bout, reference=reference)


class TestChampsManquants:
    """Relevé des bouts non renseignés."""

    def test_jointure_complete(self) -> None:
        table = TABLES_PAR_TYPE["Ouvrage_Materiel"]
        assert champs_manquants(_element(_jointure()), table) == []

    def test_cible_manquante(self) -> None:
        table = TABLES_PAR_TYPE["Ouvrage_Materiel"]
        assert champs_manquants(_element(_jointure_partielle("ouvrage")), table) == ["materiel"]

    def test_source_manquante(self) -> None:
        table = TABLES_PAR_TYPE["Ouvrage_Materiel"]
        assert champs_manquants(_element(_jointure_partielle("materiel", "m1")), table) == ["ouvrage"]

    def test_les_deux_manquants(self) -> None:
        table = TABLES_PAR_TYPE["Ouvrage_Materiel"]
        vide = _MEMBRE_VIDE.format(type_rpd="Ouvrage_Materiel")
        assert champs_manquants(_element(vide), table) == ["ouvrage", "materiel"]

    def test_href_vide_vaut_absence(self) -> None:
        """Un bout present sans reference exploitable ne designe rien."""
        table = TABLES_PAR_TYPE["Ouvrage_Materiel"]
        assert champs_manquants(_element(_jointure(ref_cible="  ")), table) == ["materiel"]


class TestDetecterChampsManquants:
    """Tests de detecter_champs_manquants."""

    @staticmethod
    def _elements(membres: list[str]) -> list[tuple[str, Element]]:
        return [("Ouvrage_Materiel", _element(m)) for m in membres]

    def test_jointure_complete_conforme(self) -> None:
        assert detecter_champs_manquants(self._elements([_jointure()])) == []

    def test_un_bout_manquant(self) -> None:
        erreurs = detecter_champs_manquants(self._elements([_jointure_partielle()]))
        assert len(erreurs) == 1
        assert erreurs[0].champ == "materiel"
        assert erreurs[0].type_erreur == CODE_CHAMP_MANQUANT

    def test_le_bout_present_situe_l_anomalie(self) -> None:
        erreurs = detecter_champs_manquants(self._elements([_jointure_partielle("ouvrage", "j7")]))
        assert erreurs[0].reference_presente == "j7"
        assert erreurs[0].gml_id == "j7"
        assert "j7" in erreurs[0].message

    def test_une_anomalie_par_champ(self) -> None:
        """Une jointure privee de ses deux bouts ne decrit plus rien : deux champs."""
        vide = _MEMBRE_VIDE.format(type_rpd="Ouvrage_Materiel")
        erreurs = detecter_champs_manquants(self._elements([vide]))
        assert [e.champ for e in erreurs] == ["ouvrage", "materiel"]
        assert erreurs[0].gml_id == SANS_REFERENCE

    def test_priorite_forte(self) -> None:
        """E-0013 est « bloquante » au verificateur, rendu « forte » par la famille."""
        erreurs = detecter_champs_manquants(self._elements([_jointure_partielle()]))
        assert erreurs[0].priorite == PRIORITE_FORTE

    def test_code_erreur_du_rang(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_JOINTURES_CHAMPS, CODE_CHAMP_MANQUANT) == "E-0013"

    def test_serialisation(self) -> None:
        donnees = detecter_champs_manquants(self._elements([_jointure_partielle()]))[0].vers_dict()
        assert donnees["severite"] == "ERREUR"
        assert donnees["champ"] == "materiel"
        assert donnees["type_rpd"] == "Ouvrage_Materiel"

    def test_collection_vide(self) -> None:
        assert detecter_champs_manquants([]) == []


class TestExclusiviteDesDeuxRegles:
    """Une jointure ne peut relever des deux codes."""

    @staticmethod
    def _elements(membres: list[str]) -> list[tuple[str, Element]]:
        return [("Ouvrage_Materiel", _element(m)) for m in membres]

    def test_incomplete_ne_fait_pas_doublon(self) -> None:
        """Deux jointures incompletes identiques ne forment aucun couple."""
        elements = self._elements([_jointure_partielle(), _jointure_partielle()])
        assert detecter_doublons(elements) == []
        assert len(detecter_champs_manquants(elements)) == 2

    def test_doublon_n_a_aucun_champ_manquant(self) -> None:
        elements = self._elements([_jointure(), _jointure()])
        assert len(detecter_doublons(elements)) == 1
        assert detecter_champs_manquants(elements) == []


class TestCliChampsJointure:
    """Analyseur et rapport du contrôle E0117."""

    def test_document_conforme(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jointure()])
        assert AnalyseurChampsJointure(chemin).analyser() == []

    def test_bout_manquant_detecte(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jointure_partielle()])
        assert len(AnalyseurChampsJointure(chemin).analyser()) == 1

    def test_meme_perimetre_que_e0116(self, tmp_path: Any) -> None:
        """Les deux controles lisent exactement les memes objets."""
        autre = '  <gml:featureMember><RecoStaR:RPD_Coffret_Reco gml:id="k1"/></gml:featureMember>'
        chemin = _ecrire_gml(tmp_path, [autre, _jointure_partielle()])
        assert len(AnalyseurChampsJointure(chemin).analyser()) == 1

    def test_identite_selon_la_version(self) -> None:
        assert identite_controle("1.1", RANG_JOINTURES_CHAMPS).code == "E0117"
        assert identite_controle(PROFIL_V1_0.code, RANG_JOINTURES_CHAMPS).code == "E0017"

    def test_rapport_non_conforme(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jointure_partielle()])
        sortie = generer_rapport_champs(chemin, AnalyseurChampsJointure(chemin).analyser(), tmp_path)
        with open(sortie, encoding="utf-8") as flux:
            rapport = json.load(flux)
        assert rapport["conformite"] == "NON_CONFORME"
        assert rapport["type_controle"] == "E0117_JOINTURES_CHAMPS"
        assert rapport["erreurs"][0]["champ"] == "materiel"

    def test_nom_du_rapport_suit_la_version(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jointure()])
        sortie = generer_rapport_champs(chemin, [], tmp_path, PROFIL_V1_0.code)
        assert sortie.name.endswith("_controle_e0017.json")
