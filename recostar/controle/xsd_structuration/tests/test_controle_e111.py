"""
Tests unitaires du module controle_e111.
Couvre l'extraction des valeurs GML, l'analyse des RPD et la génération du rapport JSON.
"""

import json
from xml.etree.ElementTree import Element, SubElement  # nosec B405

from controle_e111 import (
    AnalyseurGML,
    _construire_rapport,
    _extraire_gml_id,
    _extraire_valeur,
    _nom_local,
    _resoudre_chemin_sortie,
    generer_rapport,
)
from regles_metier import ErreurMetier
from utils_gml import creer_feature_member_avec_valeurs

NS_GML = "http://www.opengis.net/gml/3.2"
NS_RECOSTAR = "http://StaR-Elec.com"
NS_XLINK = "http://www.w3.org/1999/xlink"


# ---------------------------------------------------------------------------
# Tests des utilitaires d'extraction de valeurs
# ---------------------------------------------------------------------------


class TestExtraireValeur:
    """Tests de _extraire_valeur (texte direct vs xlink:href vs absent)."""

    def test_valeur_texte_direct(self):
        """Texte non vide directement porté par l'élément."""
        elem = Element(f"{{{NS_RECOSTAR}}}Statut")
        elem.text = "UnderCommissionning"
        assert _extraire_valeur(elem) == "UnderCommissionning"

    def test_valeur_texte_espaces_strippees(self):
        """Espaces parasites en début/fin sont éliminés."""
        elem = Element(f"{{{NS_RECOSTAR}}}Statut")
        elem.text = "  Functional  "
        assert _extraire_valeur(elem) == "Functional"

    def test_valeur_xlink_href(self):
        """Référence xlink:href : le fragment après '#' est extrait."""
        elem = Element(f"{{{NS_RECOSTAR}}}TypeCoffret")
        elem.set(f"{{{NS_XLINK}}}href", "http://example.com/codelist.xml#RMBT300")
        assert _extraire_valeur(elem) == "RMBT300"

    def test_valeur_xlink_href_sans_fragment(self):
        """xlink:href sans '#' : la valeur retournée est l'URI complète."""
        elem = Element(f"{{{NS_RECOSTAR}}}Ref")
        elem.set(f"{{{NS_XLINK}}}href", "valeur_brute")
        assert _extraire_valeur(elem) == "valeur_brute"

    def test_valeur_texte_prioritaire_sur_xlink(self):
        """Si texte et href coexistent, le texte prime (cas marginal)."""
        elem = Element(f"{{{NS_RECOSTAR}}}X")
        elem.text = "texte_direct"
        elem.set(f"{{{NS_XLINK}}}href", "url#fragment")
        assert _extraire_valeur(elem) == "texte_direct"

    def test_valeur_absente(self):
        """Élément vide sans href : retourne None."""
        elem = Element(f"{{{NS_RECOSTAR}}}Vide")
        assert _extraire_valeur(elem) is None

    def test_valeur_texte_uniquement_espaces(self):
        """Texte composé uniquement d'espaces : traité comme absent."""
        elem = Element(f"{{{NS_RECOSTAR}}}Espaces")
        elem.text = "   "
        assert _extraire_valeur(elem) is None


# ---------------------------------------------------------------------------
# Tests des utilitaires namespace (héritage E110)
# ---------------------------------------------------------------------------


class TestUtilitairesNamespace:
    """Vérifications de cohérence des utilitaires namespace."""

    def test_nom_local_avec_namespace(self):
        """Extraction du nom local depuis un tag qualifié."""
        assert _nom_local(f"{{{NS_GML}}}featureMember") == "featureMember"

    def test_nom_local_sans_namespace(self):
        """Tag sans accolade : retourné tel quel."""
        assert _nom_local("Statut") == "Statut"

    def test_extraire_gml_id_present(self):
        """gml:id est correctement lu."""
        elem = Element("test")
        elem.set(f"{{{NS_GML}}}id", "mon_id")
        assert _extraire_gml_id(elem) == "mon_id"

    def test_extraire_gml_id_absent(self):
        """gml:id absent : sentinelle textuelle retournée."""
        elem = Element("test")
        assert _extraire_gml_id(elem) == "<sans id>"


# ---------------------------------------------------------------------------
# Tests de AnalyseurGML
# ---------------------------------------------------------------------------


class TestAnalyseurGML:
    """Tests de l'analyse de fichiers GML par E111."""

    def test_cable_en_attente_conforme(self, chemin_gml_tmp, membre_cable_elec_en_attente_complet):
        """Un câble en attente complet ne déclenche aucune erreur métier."""
        chemin = chemin_gml_tmp([membre_cable_elec_en_attente_complet])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        assert erreurs == []

    def test_cable_en_attente_incomplet_detecte(self, chemin_gml_tmp, membre_cable_elec_en_attente_incomplet):
        """Un câble en attente sans Section ni Isolant : erreurs détectées."""
        chemin = chemin_gml_tmp([membre_cable_elec_en_attente_incomplet])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        champs = {e.champ_attendu for e in erreurs}
        assert {"Section", "Isolant"} <= champs

    def test_cable_bt_sans_hierarchie_detecte(self, chemin_gml_tmp, membre_cable_elec_bt_sans_hierarchie):
        """Câble BT sans HierarchieBT : règle R002 violée."""
        chemin = chemin_gml_tmp([membre_cable_elec_bt_sans_hierarchie])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        regles_violees = {e.regle for e in erreurs}
        assert "R002_CABLE_ELEC_BT" in regles_violees

    def test_type_sans_regle_ignore(self, chemin_gml_tmp):
        """RPD_Jonction_Reco n'a pas de règle métier : aucune erreur."""
        membre = creer_feature_member_avec_valeurs(
            "RPD_Jonction_Reco",
            "jonction_001",
            [("Statut", "UnderCommissionning"), ("DomaineTension", "HTA")],
        )
        chemin = chemin_gml_tmp([membre])
        analyseur = AnalyseurGML(chemin)
        assert analyseur.analyser() == []

    def test_type_ep_ignore(self, chemin_gml_tmp):
        """Les objets EP_ sont ignorés même s'ils ont des champs métier."""
        membre = creer_feature_member_avec_valeurs(
            "EP_CableElectrique_Reco",
            "ep_cable_001",
            [("Statut", "UnderCommissionning")],
        )
        chemin = chemin_gml_tmp([membre])
        analyseur = AnalyseurGML(chemin)
        assert analyseur.analyser() == []

    def test_membre_vide_ignore(self, chemin_gml_tmp):
        """featureMember sans enfant : aucune erreur générée."""
        membre_vide = Element(f"{{{NS_GML}}}featureMember")
        chemin = chemin_gml_tmp([membre_vide])
        analyseur = AnalyseurGML(chemin)
        assert analyseur.analyser() == []

    def test_extraction_xlink_dans_gml_reel(self, chemin_gml_tmp):
        """Vérifie que les valeurs portées par xlink:href sont bien décodées."""
        # Construction manuelle avec xlink:href pour simuler une référence à code-list.
        membre = Element(f"{{{NS_GML}}}featureMember")
        rpd = SubElement(membre, f"{{{NS_RECOSTAR}}}RPD_CableElectrique_Reco")
        rpd.set(f"{{{NS_GML}}}id", "cable_xlink_001")
        statut = SubElement(rpd, f"{{{NS_RECOSTAR}}}Statut")
        statut.set(f"{{{NS_XLINK}}}href", "codelist.xml#UnderCommissionning")
        dt = SubElement(rpd, f"{{{NS_RECOSTAR}}}DomaineTension")
        dt.text = "HTA"
        # Statut "UnderCommissionning" via xlink doit déclencher R001 → 4 champs manquants.
        chemin = chemin_gml_tmp([membre])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        # Si l'extraction xlink fonctionne, R001 doit s'activer.
        assert any(e.regle == "R001_CABLE_ELEC_EN_ATTENTE" for e in erreurs)

    def test_multi_membres_isolation(
        self,
        chemin_gml_tmp,
        membre_cable_elec_en_attente_complet,
        membre_cable_elec_bt_sans_hierarchie,
    ):
        """Plusieurs membres : seul le non-conforme génère des erreurs."""
        membres = [
            membre_cable_elec_en_attente_complet,
            membre_cable_elec_bt_sans_hierarchie,
        ]
        chemin = chemin_gml_tmp(membres)
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        gml_ids = {e.gml_id for e in erreurs}
        assert "cable_bt_001" in gml_ids
        assert "cable_en_attente_001" not in gml_ids


# ---------------------------------------------------------------------------
# Tests de la génération du rapport JSON
# ---------------------------------------------------------------------------


class TestGenererRapport:
    """Tests de la génération JSON du rapport E111."""

    def _erreur_test(self) -> ErreurMetier:
        """Erreur métier prête à l'emploi pour les tests."""
        return ErreurMetier(
            type_rpd="RPD_CableElectrique_Reco",
            gml_id="cable_001",
            regle="R001_CABLE_ELEC_EN_ATTENTE",
            champ_attendu="Section",
            contexte="câble en attente",
            message="Champ requis 'Section' manquant",
        )

    def test_rapport_cree_fichier_json(self, chemin_gml_vide):
        """Un fichier JSON est créé au chemin attendu."""
        chemin = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        assert chemin.exists()
        assert chemin.suffix == ".json"

    def test_nom_fichier_suffixe_e111(self, chemin_gml_vide):
        """Le nom du fichier de sortie est suffixé '_controle_e111'."""
        chemin = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        assert "_controle_e111" in chemin.name

    def test_rapport_sans_repertoire_sortie(self, chemin_gml_vide):
        """Sans output_dir, le JSON est créé à côté du GML."""
        chemin = generer_rapport(chemin_gml_vide, [])
        assert chemin.parent == chemin_gml_vide.parent

    def test_rapport_avec_repertoire_sortie(self, chemin_gml_vide, tmp_path):
        """Avec output_dir, le JSON est créé dans le répertoire spécifié."""
        dossier = tmp_path / "sortie"
        dossier.mkdir()
        chemin = generer_rapport(chemin_gml_vide, [], dossier)
        assert chemin.parent == dossier

    def test_rapport_json_valide(self, chemin_gml_vide):
        """Le JSON généré est syntaxiquement valide et désérialisable."""
        erreurs = [self._erreur_test()]
        chemin = generer_rapport(chemin_gml_vide, erreurs, chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        assert isinstance(contenu, dict)

    def test_rapport_champs_attendus(self, chemin_gml_vide):
        """Le rapport JSON contient tous les champs documentés."""
        chemin = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        attendus = {
            "fichier",
            "date_controle",
            "niveau",
            "type_controle",
            "version_controlee",
            "conformite",
            "nb_erreurs",
            "nb_par_severite",
            "erreurs",
        }
        assert attendus == set(contenu.keys())

    def test_rapport_type_controle_e111(self, chemin_gml_vide):
        """Le champ type_controle identifie bien E111_METIER."""
        chemin = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["type_controle"] == "E111_METIER"

    def test_rapport_conforme_sans_erreur(self, chemin_gml_vide):
        """0 erreur : conformite = CONFORME."""
        chemin = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["conformite"] == "CONFORME"
        assert contenu["nb_erreurs"] == 0

    def test_rapport_non_conforme_avec_erreurs(self, chemin_gml_vide):
        """≥1 erreur : conformite = NON_CONFORME."""
        erreurs = [self._erreur_test()]
        chemin = generer_rapport(chemin_gml_vide, erreurs, chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["conformite"] == "NON_CONFORME"
        assert contenu["nb_erreurs"] == 1

    def test_rapport_erreurs_serialisees(self, chemin_gml_vide):
        """Le champ erreurs contient les ErreurMetier sérialisées."""
        erreur = self._erreur_test()
        chemin = generer_rapport(chemin_gml_vide, [erreur], chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        assert len(contenu["erreurs"]) == 1
        err = contenu["erreurs"][0]
        assert err["regle"] == "R001_CABLE_ELEC_EN_ATTENTE"
        assert err["champ_attendu"] == "Section"


# ---------------------------------------------------------------------------
# Tests des utilitaires internes
# ---------------------------------------------------------------------------


class TestUtilitairesRapport:
    """Tests des helpers internes de génération du rapport."""

    def test_construire_rapport_inclut_e111(self, chemin_gml_vide):
        """_construire_rapport identifie le type de contrôle."""
        rapport = _construire_rapport(chemin_gml_vide, [])
        assert rapport["type_controle"] == "E111_METIER"

    def test_resoudre_chemin_sans_output_dir(self, tmp_path):
        """Sans output_dir, le JSON est au même endroit que le GML."""
        chemin_gml = tmp_path / "fichier.gml"
        chemin_sortie = _resoudre_chemin_sortie(chemin_gml, None)
        assert chemin_sortie.parent == chemin_gml.parent

    def test_resoudre_chemin_avec_output_dir(self, tmp_path):
        """Avec output_dir, le JSON est dans le répertoire indiqué."""
        chemin_gml = tmp_path / "fichier.gml"
        dossier = tmp_path / "out"
        dossier.mkdir()
        chemin_sortie = _resoudre_chemin_sortie(chemin_gml, dossier)
        assert chemin_sortie.parent == dossier
