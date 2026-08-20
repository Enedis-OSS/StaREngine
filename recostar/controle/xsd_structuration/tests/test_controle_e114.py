"""
Tests unitaires du module controle_e114.
Couvre l'analyseur de valeurs et la génération du rapport JSON.
"""

import json
from pathlib import Path

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import (  # nosec B405
    Element,
    SubElement,
)

import pytest
from controle_e114 import (
    AnalyseurValeurs,
    _compter_par_severite,
    _construire_rapport,
    _extraire_gml_id,
    _extraire_valeur,
    _nom_local,
    _resoudre_chemin_sortie,
    generer_rapport,
)
from priorites_structuration import (
    PRIORITE_BLOQUANT,
    PRIORITE_MINEUR,
    statut_conformite,
    ventiler_par_priorite,
)
from regles_valeurs import (
    CODE_FORMAT_INVALIDE,
    CODE_VALEUR_HORS_CODELIST,
    CODE_VALEUR_HORS_ENUMERATION,
    SEVERITE_ERREUR,
    ErreurValeur,
)
from utils_gml import (
    NS_GML,
    NS_RECOSTAR,
    NS_XLINK,
    creer_feature_member_avec_valeurs,
)

# ---------------------------------------------------------------------------
# Tests des utilitaires d'extraction (parité avec E111)
# ---------------------------------------------------------------------------


class TestExtraireValeur:
    """Mêmes contrats que controle_e111._extraire_valeur."""

    def test_texte_direct(self):
        elem = Element(f"{{{NS_RECOSTAR}}}Statut")
        elem.text = "Functional"
        assert _extraire_valeur(elem) == "Functional"

    def test_texte_strip(self):
        elem = Element(f"{{{NS_RECOSTAR}}}Statut")
        elem.text = "  HTA  "
        assert _extraire_valeur(elem) == "HTA"

    def test_xlink_href_fragment(self):
        elem = Element(f"{{{NS_RECOSTAR}}}TypeCoffret")
        elem.set(f"{{{NS_XLINK}}}href", "codelist.xml#RMBT300")
        assert _extraire_valeur(elem) == "RMBT300"

    def test_priorite_texte_sur_href(self):
        elem = Element(f"{{{NS_RECOSTAR}}}X")
        elem.text = "ValeurTexte"
        elem.set(f"{{{NS_XLINK}}}href", "ignore#x")
        assert _extraire_valeur(elem) == "ValeurTexte"

    def test_aucun_retourne_none(self):
        elem = Element(f"{{{NS_RECOSTAR}}}Vide")
        assert _extraire_valeur(elem) is None


class TestUtilitairesNamespace:
    """Helpers communs aux contrôles E110/E111/E113/E114."""

    def test_nom_local(self):
        assert _nom_local(f"{{{NS_GML}}}featureMember") == "featureMember"

    def test_extraire_gml_id_present(self):
        elem = Element("test")
        elem.set(f"{{{NS_GML}}}id", "abc")
        assert _extraire_gml_id(elem) == "abc"

    def test_extraire_gml_id_absent(self):
        assert _extraire_gml_id(Element("test")) == "<sans id>"


# ---------------------------------------------------------------------------
# Tests de l'AnalyseurValeurs
# ---------------------------------------------------------------------------


class TestAnalyseurValeursConforme:
    """Cas nominaux : aucune erreur attendue."""

    def test_cable_valide_aucune_erreur(self, chemin_gml_tmp):
        membre = creer_feature_member_avec_valeurs(
            "RPD_CableElectrique_Reco",
            "cable_001",
            [
                ("reseau", None),
                ("DomaineTension", "HTA"),
                ("FonctionCable", "DistributionEnergie"),
                ("NombreConducteurs", "3"),
                ("Section", "240"),
                ("Isolant", "Reticulee"),
                ("Materiau", "Alu"),
                ("Statut", "Functional"),
            ],
        )
        analyseur = AnalyseurValeurs(chemin_gml_tmp([membre]))
        assert analyseur.analyser() == []

    def test_ep_objects_ignores(self, chemin_gml_tmp):
        """Objets EP_* ignorés même si valeur fautive."""
        membre = creer_feature_member_avec_valeurs(
            "EP_CableElectrique_Reco",
            "ep_001",
            [("Statut", "ValeurFantaisiste")],
        )
        assert AnalyseurValeurs(chemin_gml_tmp([membre])).analyser() == []

    def test_type_sans_regle_ignore(self, chemin_gml_tmp):
        """Type qui n'a aucune règle dans le catalogue est ignoré."""
        membre = creer_feature_member_avec_valeurs(
            "RPD_TypeInconnu_Reco",
            "x_001",
            [("Statut", "ValeurFantaisiste")],
        )
        assert AnalyseurValeurs(chemin_gml_tmp([membre])).analyser() == []


class TestAnalyseurValeursErreurs:
    """Détection effective des violations sur les énumérations strictes."""

    def test_domaine_tension_invalide_signale(self, chemin_gml_tmp):
        membre = creer_feature_member_avec_valeurs(
            "RPD_CableElectrique_Reco",
            "cable_002",
            [
                ("reseau", None),
                ("DomaineTension", "MTA"),
                ("FonctionCable", "DistributionEnergie"),
                ("Statut", "Functional"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([membre])).analyser()
        cibles = [e for e in erreurs if e.champ == "DomaineTension"]
        assert len(cibles) == 1
        assert cibles[0].severite == SEVERITE_ERREUR
        assert cibles[0].valeur_trouvee == "MTA"

    def test_statut_invalide_signale(self, chemin_gml_tmp):
        membre = creer_feature_member_avec_valeurs(
            "RPD_Coffret_Reco",
            "cof_001",
            [
                ("reseau", None),
                ("FonctionCoffret", "Manoeuvrable"),
                ("Geometrie", None),
                ("PrecisionXY", "A"),
                ("PrecisionZ", "A"),
                ("Statut", "Active"),
                ("TypeCoffret", "RMBT300"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([membre])).analyser()
        assert any(e.champ == "Statut" and e.severite == SEVERITE_ERREUR for e in erreurs)

    def test_precision_invalide_signale(self, chemin_gml_tmp):
        membre = creer_feature_member_avec_valeurs(
            "RPD_Support_Reco",
            "sup_001",
            [
                ("reseau", None),
                ("Geometrie", None),
                ("NatureSupport", "Poteau"),
                ("PrecisionXY", "Z"),
                ("PrecisionZ", "A"),
                ("Statut", "Functional"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([membre])).analyser()
        cibles = [e for e in erreurs if e.champ == "PrecisionXY"]
        assert len(cibles) == 1
        assert cibles[0].valeur_trouvee == "Z"

    def test_srs_invalide_sur_metadata(self, chemin_gml_tmp):
        membre = creer_feature_member_avec_valeurs(
            "Metadata",
            "meta_001",
            [
                ("Datecreation", "2026-05-26"),
                ("Logiciel", "Test 1.0"),
                ("Producteur", "X"),
                ("Responsable", "Y"),
                ("SRS", "EPSG:4326"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([membre])).analyser()
        cibles = [e for e in erreurs if e.champ == "SRS"]
        assert len(cibles) == 1
        assert cibles[0].code == CODE_VALEUR_HORS_ENUMERATION


class TestAnalyseurValeursCodeListsErreur:
    """Les CodeLists hors liste documentée émettent une ERREUR (bloquante)."""

    def test_type_coffret_etrange_erreur(self, chemin_gml_tmp):
        membre = creer_feature_member_avec_valeurs(
            "RPD_Coffret_Reco",
            "cof_001",
            [
                ("reseau", None),
                ("FonctionCoffret", "Manoeuvrable"),
                ("Geometrie", None),
                ("PrecisionXY", "A"),
                ("PrecisionZ", "A"),
                ("Statut", "Functional"),
                ("TypeCoffret", "MonExtensionLocale"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([membre])).analyser()
        cibles = [e for e in erreurs if e.champ == "TypeCoffret"]
        assert len(cibles) == 1
        assert cibles[0].severite == SEVERITE_ERREUR
        assert cibles[0].code == CODE_VALEUR_HORS_CODELIST


class TestAnalyseurValeursTheme:
    """Theme RPD : ELECTRD obligatoire (plus strict que CodeList §10.6.2)."""

    def test_theme_electrd_valide(self, chemin_gml_tmp):
        membre = creer_feature_member_avec_valeurs(
            "ReseauUtilite",
            "reseau_001",
            [
                ("Mention", "Récolement"),
                ("Nom", "AFFAIRE-001"),
                ("Responsable", "Enedis"),
                ("Theme", "ELECTRD"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([membre])).analyser()
        assert not [e for e in erreurs if e.champ == "Theme"]

    def test_theme_elec_rejete_avec_erreur(self, chemin_gml_tmp):
        """ELEC est valide dans la CodeList NatureReseauValue mais pas en RPD."""
        membre = creer_feature_member_avec_valeurs(
            "ReseauUtilite",
            "reseau_001",
            [
                ("Mention", "Récolement"),
                ("Nom", "AFFAIRE-001"),
                ("Responsable", "Enedis"),
                ("Theme", "ELEC"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([membre])).analyser()
        cibles = [e for e in erreurs if e.champ == "Theme"]
        assert len(cibles) == 1
        assert cibles[0].severite == SEVERITE_ERREUR


class TestAnalyseurValeursNumeroPRM:
    """Format strict 14 chiffres pour NumeroPRM."""

    def test_quatorze_chiffres_valide(self, chemin_gml_tmp):
        membre = creer_feature_member_avec_valeurs(
            "RPD_PointDeComptage_Reco",
            "pdc_001",
            [
                ("reseau", None),
                ("Geometrie", None),
                ("NumeroPRM", "12345678901234"),
                ("PrecisionXY", "A"),
                ("PrecisionZ", "A"),
                ("Statut", "Functional"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([membre])).analyser()
        assert not [e for e in erreurs if e.champ == "NumeroPRM"]

    def test_format_invalide_signale(self, chemin_gml_tmp):
        membre = creer_feature_member_avec_valeurs(
            "RPD_PointDeComptage_Reco",
            "pdc_002",
            [
                ("reseau", None),
                ("Geometrie", None),
                ("NumeroPRM", "ABC123"),
                ("PrecisionXY", "A"),
                ("PrecisionZ", "A"),
                ("Statut", "Functional"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([membre])).analyser()
        cibles = [e for e in erreurs if e.champ == "NumeroPRM"]
        assert len(cibles) == 1
        assert cibles[0].code == CODE_FORMAT_INVALIDE


class TestAnalyseurValeursXlink:
    """Extraction des valeurs portées par xlink:href (cas CodeList)."""

    def test_statut_via_xlink_evalue(self, chemin_gml_tmp):
        """Statut référencé par xlink:href doit être évalué normalement."""
        membre = Element(f"{{{NS_GML}}}featureMember")
        rpd = SubElement(membre, f"{{{NS_RECOSTAR}}}RPD_Coffret_Reco")
        rpd.set(f"{{{NS_GML}}}id", "cof_xlink_001")
        for nom in ("FonctionCoffret", "Geometrie"):
            SubElement(rpd, f"{{{NS_RECOSTAR}}}{nom}")
        prec = SubElement(rpd, f"{{{NS_RECOSTAR}}}PrecisionXY")
        prec.text = "A"
        prec2 = SubElement(rpd, f"{{{NS_RECOSTAR}}}PrecisionZ")
        prec2.text = "A"
        statut = SubElement(rpd, f"{{{NS_RECOSTAR}}}Statut")
        statut.set(f"{{{NS_XLINK}}}href", "codelist.xml#InvalidValue")
        type_cof = SubElement(rpd, f"{{{NS_RECOSTAR}}}TypeCoffret")
        type_cof.text = "RMBT300"

        chemin = chemin_gml_tmp([membre])
        erreurs = AnalyseurValeurs(chemin).analyser()
        cibles = [e for e in erreurs if e.champ == "Statut"]
        assert len(cibles) == 1
        assert cibles[0].valeur_trouvee == "InvalidValue"


class TestAnalyseurValeursIsolation:
    """Plusieurs membres : les erreurs sont rattachées au bon gml_id."""

    def test_multi_membres_id_correct(self, chemin_gml_tmp):
        m1 = creer_feature_member_avec_valeurs(
            "RPD_CableElectrique_Reco",
            "cable_OK",
            [
                ("reseau", None),
                ("DomaineTension", "HTA"),
                ("FonctionCable", "DistributionEnergie"),
                ("Statut", "Functional"),
            ],
        )
        m2 = creer_feature_member_avec_valeurs(
            "RPD_CableElectrique_Reco",
            "cable_KO",
            [
                ("reseau", None),
                ("DomaineTension", "MTA"),
                ("FonctionCable", "DistributionEnergie"),
                ("Statut", "Functional"),
            ],
        )
        erreurs = AnalyseurValeurs(chemin_gml_tmp([m1, m2])).analyser()
        gml_ids = {e.gml_id for e in erreurs}
        assert gml_ids == {"cable_KO"}


# ---------------------------------------------------------------------------
# Tests des helpers de sévérité et de conformité
# ---------------------------------------------------------------------------


class TestCompterParSeverite:
    """Comptage par sévérité pour rapport."""

    def _err(self, severite: str) -> ErreurValeur:
        return ErreurValeur(
            "T",
            "id",
            "C",
            "V",
            "CODE",
            severite,
            "R",
            "src",
            "msg",
        )

    def test_aucune_erreur(self):
        assert _compter_par_severite([]) == {}

    def test_uniquement_erreurs(self):
        compteur = _compter_par_severite([self._err(SEVERITE_ERREUR)] * 3)
        assert compteur == {SEVERITE_ERREUR: 3}


class TestConformite:
    """Conformité E114 : seules les entrées bloquantes invalident le fichier."""

    def _err(self, priorite: str = PRIORITE_BLOQUANT) -> ErreurValeur:
        return ErreurValeur(
            "T",
            "id",
            "C",
            "V",
            "CODE",
            SEVERITE_ERREUR,
            "R",
            "src",
            "msg",
            priorite,
        )

    def test_aucune_erreur_conforme(self):
        assert statut_conformite(ventiler_par_priorite([])) == "CONFORME"

    def test_erreur_bloquante_invalide(self):
        """Une entrée bloquante — le cas de la quasi-totalité des règles."""
        assert statut_conformite(ventiler_par_priorite([self._err()])) == "NON_CONFORME"

    def test_erreur_mineure_seule_reste_conforme(self):
        """Une entrée mineure (E_THEME_RPD) est signalée sans déclasser."""
        erreurs = [self._err(PRIORITE_MINEUR)]
        assert ventiler_par_priorite(erreurs) == {PRIORITE_MINEUR: 1}
        assert statut_conformite(ventiler_par_priorite(erreurs)) == "CONFORME"

    def test_melange_declasse_sur_la_seule_bloquante(self):
        erreurs = [self._err(PRIORITE_MINEUR), self._err()]
        assert statut_conformite(ventiler_par_priorite(erreurs)) == "NON_CONFORME"


# ---------------------------------------------------------------------------
# Tests de la génération du rapport JSON
# ---------------------------------------------------------------------------


class TestGenererRapport:
    """Sérialisation du rapport JSON."""

    @pytest.fixture
    def _gml_vide(self, tmp_path: Path) -> Path:
        chemin = tmp_path / "vide.gml"
        chemin.touch()
        return chemin

    def _erreur_test(self) -> ErreurValeur:
        return ErreurValeur(
            type_rpd="RPD_CableElectrique_Reco",
            gml_id="cable_001",
            champ="DomaineTension",
            valeur_trouvee="MTA",
            code=CODE_VALEUR_HORS_ENUMERATION,
            severite=SEVERITE_ERREUR,
            regle="E_DOMAINE_TENSION",
            source="PDF §10.1.1",
            message="Valeur 'MTA' invalide",
        )

    def test_fichier_cree(self, _gml_vide):
        chemin = generer_rapport(_gml_vide, [], _gml_vide.parent)
        assert chemin.exists()
        assert chemin.suffix == ".json"

    def test_nom_suffixe_e114(self, _gml_vide):
        chemin = generer_rapport(_gml_vide, [], _gml_vide.parent)
        assert "_controle_e114" in chemin.name

    def test_rapport_conforme_aucune_erreur(self, _gml_vide):
        chemin = generer_rapport(_gml_vide, [], _gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["conformite"] == "CONFORME"
        assert rapport["nb_erreurs"] == 0

    def test_rapport_non_conforme_avec_erreur(self, _gml_vide):
        chemin = generer_rapport(
            _gml_vide,
            [self._erreur_test()],
            _gml_vide.parent,
        )
        with open(chemin, encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["conformite"] == "NON_CONFORME"
        assert rapport["nb_erreurs"] == 1
        assert rapport["nb_par_severite"][SEVERITE_ERREUR] == 1

    def test_champ_type_controle(self, _gml_vide):
        rapport = _construire_rapport(_gml_vide, [])
        assert rapport["type_controle"] == "E114_VALEURS"

    def test_champs_attendus_presents(self, _gml_vide):
        rapport = _construire_rapport(_gml_vide, [])
        attendus = {
            "fichier",
            "date_controle",
            "niveau",
            "type_controle",
            "version_controlee",
            "conformite",
            "nb_erreurs",
            "nb_par_severite",
            "nb_par_priorite",
            "erreurs",
        }
        assert set(rapport.keys()) == attendus

    def test_erreurs_serialisees(self, _gml_vide):
        chemin = generer_rapport(
            _gml_vide,
            [self._erreur_test()],
            _gml_vide.parent,
        )
        with open(chemin, encoding="utf-8") as f:
            rapport = json.load(f)
        err = rapport["erreurs"][0]
        assert err["regle"] == "E_DOMAINE_TENSION"
        assert err["valeur_trouvee"] == "MTA"
        assert err["source"] == "PDF §10.1.1"

    def test_chemin_sans_repertoire_sortie(self, tmp_path: Path):
        chemin_gml = tmp_path / "fichier.gml"
        chemin = _resoudre_chemin_sortie(chemin_gml, None)
        assert chemin.parent == chemin_gml.parent

    def test_chemin_avec_repertoire_sortie(self, tmp_path: Path):
        chemin_gml = tmp_path / "fichier.gml"
        dossier = tmp_path / "out"
        dossier.mkdir()
        chemin = _resoudre_chemin_sortie(chemin_gml, dossier)
        assert chemin.parent == dossier
