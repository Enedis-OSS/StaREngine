"""
Tests unitaires du module controle_e113.
Couvre l'analyseur d'en-tête, la conversion d'erreurs et la génération du rapport JSON.
"""

import json
from pathlib import Path
from xml.etree.ElementTree import Element  # nosec B405

import pytest
from controle_e113 import (
    AnalyseurEntete,
    _construire_rapport,
    _convertir_erreur_ordre,
    _extraire_gml_id,
    _extraire_texte_enfant,
    _lire_namespaces,
    _nom_local,
    _resoudre_chemin_sortie,
    _verifier_namespaces,
    generer_rapport,
)
from regles_entete import (
    CODE_CHAMP_HORS_ORDRE,
    CODE_CHAMP_INATTENDU,
    CODE_CHAMP_OBLIGATOIRE_MANQUANT,
    CODE_GML_ID_DUPLIQUE,
    CODE_NAMESPACE_MANQUANT,
    CODE_NAMESPACE_URI_INCORRECTE,
    CODE_OBJET_ENTETE_MANQUANT,
    CODE_OBJET_ENTETE_TROP_NOMBREUX,
    CODE_SCHEMA_LOCATION_MANQUANT,
    CODE_SCHEMA_LOCATION_VERSION_INCORRECTE,
    CODE_SRS_INVALIDE,
    ErreurEntete,
)
from sequenceur_xsd import ErreurOrdre
from utils_gml import (
    NS_RECOSTAR,
    creer_feature_member_avec_valeurs,
    creer_metadata_conforme,
    creer_reseau_utilite_conforme,
)

# ---------------------------------------------------------------------------
# Tests des utilitaires de bas niveau
# ---------------------------------------------------------------------------


class TestUtilitairesNamespace:
    """Helpers communs aux trois contrôles E110/E111/E113."""

    def test_nom_local_extrait_le_tag(self):
        assert _nom_local("{ns}Statut") == "Statut"

    def test_nom_local_sans_namespace(self):
        assert _nom_local("Statut") == "Statut"

    def test_extraire_gml_id_present(self):
        elem = Element("test")
        elem.set("{http://www.opengis.net/gml/3.2}id", "abc")
        assert _extraire_gml_id(elem) == "abc"

    def test_extraire_gml_id_absent(self):
        assert _extraire_gml_id(Element("test")) == "<sans id>"


class TestExtraireTexteEnfant:
    """Extraction du texte d'un enfant par son nom local."""

    def test_enfant_present(self):
        parent = Element("p")
        enfant = Element(f"{{{NS_RECOSTAR}}}SRS")
        enfant.text = "EPSG:2154"
        parent.append(enfant)
        assert _extraire_texte_enfant(parent, "SRS") == "EPSG:2154"

    def test_texte_strip(self):
        parent = Element("p")
        enfant = Element(f"{{{NS_RECOSTAR}}}X")
        enfant.text = "  Reseau  "
        parent.append(enfant)
        assert _extraire_texte_enfant(parent, "X") == "Reseau"

    def test_enfant_absent_retourne_none(self):
        parent = Element("p")
        assert _extraire_texte_enfant(parent, "Inconnu") is None

    def test_enfant_sans_texte_retourne_none(self):
        parent = Element("p")
        parent.append(Element(f"{{{NS_RECOSTAR}}}Vide"))
        assert _extraire_texte_enfant(parent, "Vide") is None


# ---------------------------------------------------------------------------
# Tests de la conversion ErreurOrdre -> ErreurEntete
# ---------------------------------------------------------------------------


class TestConvertirErreurOrdre:
    """Mapping des types d'erreur de séquence vers les codes E113."""

    def _erreur_ordre(self, type_err: str) -> ErreurOrdre:
        return ErreurOrdre(
            type_rpd="Metadata",
            gml_id="meta_001",
            type_erreur=type_err,
            position=0,
            element_trouve="X",
            element_attendu="Y",
            message="msg",
        )

    def test_requis_manquant(self):
        e = _convertir_erreur_ordre(self._erreur_ordre("ELEMENT_REQUIS_MANQUANT"))
        assert e.code == CODE_CHAMP_OBLIGATOIRE_MANQUANT

    def test_ordre_incorrect(self):
        e = _convertir_erreur_ordre(self._erreur_ordre("ORDRE_INCORRECT"))
        assert e.code == CODE_CHAMP_HORS_ORDRE

    def test_element_inattendu(self):
        e = _convertir_erreur_ordre(self._erreur_ordre("ELEMENT_INATTENDU"))
        assert e.code == CODE_CHAMP_INATTENDU

    def test_type_erreur_inconnu_retombe_sur_inattendu(self):
        """Tout code non mappé tombe sur CODE_CHAMP_INATTENDU (sécurité)."""
        e = _convertir_erreur_ordre(self._erreur_ordre("CODE_INCONNU"))
        assert e.code == CODE_CHAMP_INATTENDU

    def test_metadonnees_transmises(self):
        """element, valeur_trouvee, valeur_attendue, message sont propagés."""
        e = _convertir_erreur_ordre(self._erreur_ordre("ELEMENT_REQUIS_MANQUANT"))
        assert e.element == "Metadata"
        assert e.valeur_trouvee == "X"
        assert e.valeur_attendue == "Y"
        assert e.message == "msg"


# ---------------------------------------------------------------------------
# Tests de la lecture et de la vérification des namespaces
# ---------------------------------------------------------------------------


class TestNamespaces:
    """Lecture iterparse et confrontation au catalogue NAMESPACES_ATTENDUS."""

    def test_lecture_namespaces_conformes(self, gml_entete_conforme):
        """Les 4 préfixes attendus sont lus depuis un GML conforme."""
        namespaces = _lire_namespaces(gml_entete_conforme)
        assert "gml" in namespaces
        assert "RecoStaR" in namespaces
        assert "xlink" in namespaces
        assert "xsi" in namespaces

    def test_aucune_erreur_si_tous_presents(self, gml_entete_conforme):
        """GML conforme : aucune erreur de namespace."""
        namespaces = _lire_namespaces(gml_entete_conforme)
        assert _verifier_namespaces(namespaces) == []

    def test_namespace_manquant_detecte(self, chemin_gml_entete_tmp):
        """Sans namespace RecoStaR/xsi/xlink déclaré : erreurs émises.

        Le schemaLocation est aussi désactivé car son préfixe 'xsi:' devient
        invalide sans la déclaration correspondante : on isole ici la
        détection des namespaces manquants.
        """
        chemin = chemin_gml_entete_tmp([], inclure_namespaces=False, inclure_schema_location=False)
        namespaces = _lire_namespaces(chemin)
        erreurs = _verifier_namespaces(namespaces)
        codes = {e.code for e in erreurs}
        assert CODE_NAMESPACE_MANQUANT in codes
        elements_manquants = {e.element for e in erreurs}
        assert {"RecoStaR", "xlink", "xsi"} <= elements_manquants

    def test_uri_incorrecte_detectee(self, chemin_gml_entete_tmp):
        """Une URI fautive sur RecoStaR (casse erronée) est signalée."""
        chemin = chemin_gml_entete_tmp([], uri_recostar_override="http://Star-Elec.com")
        namespaces = _lire_namespaces(chemin)
        erreurs = _verifier_namespaces(namespaces)
        assert any(e.code == CODE_NAMESPACE_URI_INCORRECTE and e.element == "RecoStaR" for e in erreurs)

    def test_prefixe_recostar_avec_mauvaise_casse_signale(self, chemin_gml_entete_tmp):
        """Préfixe 'recostar' (casse minuscule) ne satisfait pas la règle."""
        chemin = chemin_gml_entete_tmp([], prefixe_recostar="recostar")
        namespaces = _lire_namespaces(chemin)
        erreurs = _verifier_namespaces(namespaces)
        # 'RecoStaR' attendu : absent → NAMESPACE_MANQUANT pour cette clé exacte.
        assert any(e.code == CODE_NAMESPACE_MANQUANT and e.element == "RecoStaR" for e in erreurs)


# ---------------------------------------------------------------------------
# Tests de l'analyseur sur un fichier complet
# ---------------------------------------------------------------------------


class TestAnalyseurEnteteConforme:
    """Cas nominal : un fichier entièrement conforme à E113."""

    def test_aucune_erreur(self, gml_entete_conforme):
        analyseur = AnalyseurEntete(gml_entete_conforme)
        assert analyseur.analyser() == []


class TestAnalyseurSchemaLocation:
    """Détection des anomalies sur xsi:schemaLocation."""

    def test_schema_location_absent(
        self,
        chemin_gml_entete_tmp,
        membre_metadata_conforme,
        membre_reseau_utilite_conforme,
    ):
        chemin = chemin_gml_entete_tmp(
            [membre_metadata_conforme, membre_reseau_utilite_conforme],
            inclure_schema_location=False,
        )
        erreurs = AnalyseurEntete(chemin).analyser()
        assert any(e.code == CODE_SCHEMA_LOCATION_MANQUANT for e in erreurs)

    def test_schema_location_pointe_main(
        self,
        chemin_gml_entete_tmp,
        membre_metadata_conforme,
        membre_reseau_utilite_conforme,
    ):
        """URL pointant sur la branche main : message dédié."""
        url_main = (
            "http://StaR-Elec.com https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/main/RecoStaR/SchemaStarElecRecoStar.xsd"
        )
        chemin = chemin_gml_entete_tmp(
            [membre_metadata_conforme, membre_reseau_utilite_conforme],
            schema_location_override=url_main,
        )
        erreurs = AnalyseurEntete(chemin).analyser()
        cibles = [e for e in erreurs if e.code == CODE_SCHEMA_LOCATION_VERSION_INCORRECTE]
        assert len(cibles) == 1
        assert "main" in (cibles[0].message or "")

    def test_schema_location_autre_version(
        self,
        chemin_gml_entete_tmp,
        membre_metadata_conforme,
        membre_reseau_utilite_conforme,
    ):
        """URL d'une version non-v1.1 : erreur de version."""
        url_v1_0 = (
            "http://StaR-Elec.com "
            "https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/RecoStar-v1.0/"
            "RecoStaR/SchemaStarElecRecoStar.xsd"
        )
        chemin = chemin_gml_entete_tmp(
            [membre_metadata_conforme, membre_reseau_utilite_conforme],
            schema_location_override=url_v1_0,
        )
        erreurs = AnalyseurEntete(chemin).analyser()
        assert any(e.code == CODE_SCHEMA_LOCATION_VERSION_INCORRECTE for e in erreurs)


class TestAnalyseurMetadata:
    """Cardinalité et conformité de l'objet Metadata."""

    def test_metadata_absent(self, chemin_gml_entete_tmp, membre_reseau_utilite_conforme):
        chemin = chemin_gml_entete_tmp([membre_reseau_utilite_conforme])
        erreurs = AnalyseurEntete(chemin).analyser()
        assert any(e.code == CODE_OBJET_ENTETE_MANQUANT and e.element == "Metadata" for e in erreurs)

    def test_metadata_multiple_signale(self, chemin_gml_entete_tmp, membre_reseau_utilite_conforme):
        """Deux Metadata dans le fichier : cardinalité (1,1) violée."""
        meta1 = creer_metadata_conforme("meta_001")
        meta2 = creer_metadata_conforme("meta_002")
        chemin = chemin_gml_entete_tmp([meta1, meta2, membre_reseau_utilite_conforme])
        erreurs = AnalyseurEntete(chemin).analyser()
        assert any(e.code == CODE_OBJET_ENTETE_TROP_NOMBREUX and e.element == "Metadata" for e in erreurs)

    def test_metadata_champ_obligatoire_manquant(self, chemin_gml_entete_tmp, membre_reseau_utilite_conforme):
        """Metadata sans SRS : règle de séquence violée → CHAMP_OBLIGATOIRE_MANQUANT."""
        metadata_partiel = creer_feature_member_avec_valeurs(
            "Metadata",
            "meta_001",
            [
                ("Datecreation", "2026-05-25"),
                ("Logiciel", "Test 1.0"),
                ("Producteur", "X"),
                ("Responsable", "Y"),
                # SRS absent.
            ],
        )
        chemin = chemin_gml_entete_tmp([metadata_partiel, membre_reseau_utilite_conforme])
        erreurs = AnalyseurEntete(chemin).analyser()
        manquants = [e for e in erreurs if e.code == CODE_CHAMP_OBLIGATOIRE_MANQUANT and e.valeur_attendue == "SRS"]
        assert len(manquants) == 1


class TestAnalyseurReseauUtilite:
    """Cardinalité et conformité de ReseauUtilite."""

    def test_reseau_utilite_absent(self, chemin_gml_entete_tmp, membre_metadata_conforme):
        chemin = chemin_gml_entete_tmp([membre_metadata_conforme])
        erreurs = AnalyseurEntete(chemin).analyser()
        assert any(e.code == CODE_OBJET_ENTETE_MANQUANT and e.element == "ReseauUtilite" for e in erreurs)

    def test_plusieurs_reseau_utilite_acceptes(self, chemin_gml_entete_tmp, membre_metadata_conforme):
        """Plusieurs ReseauUtilite (tranches de travaux) : aucune erreur de cardinalité."""
        r1 = creer_reseau_utilite_conforme("reseau_001")
        r2 = creer_reseau_utilite_conforme("reseau_002")
        chemin = chemin_gml_entete_tmp([membre_metadata_conforme, r1, r2])
        erreurs = AnalyseurEntete(chemin).analyser()
        # Aucune erreur de type "trop nombreux" sur ReseauUtilite.
        assert not any(e.code == CODE_OBJET_ENTETE_TROP_NOMBREUX and e.element == "ReseauUtilite" for e in erreurs)


# ---------------------------------------------------------------------------
# Tests du SRS
# ---------------------------------------------------------------------------


class TestAnalyseurSrs:
    """Validation de la valeur SRS contre l'énumération."""

    def test_srs_valide_aucune_erreur(self, gml_entete_conforme):
        """EPSG:2154 (par défaut dans la fixture) est conforme."""
        erreurs = AnalyseurEntete(gml_entete_conforme).analyser()
        assert not any(e.code == CODE_SRS_INVALIDE for e in erreurs)

    def test_srs_hors_liste_signale(self, chemin_gml_entete_tmp, membre_reseau_utilite_conforme):
        """EPSG:4326 (WGS84) n'est pas dans l'énumération RecoStaR."""
        metadata_wgs = creer_feature_member_avec_valeurs(
            "Metadata",
            "meta_001",
            [
                ("Datecreation", "2026-05-25"),
                ("Logiciel", "Test 1.0"),
                ("Producteur", "X"),
                ("Responsable", "Y"),
                ("SRS", "EPSG:4326"),
            ],
        )
        chemin = chemin_gml_entete_tmp([metadata_wgs, membre_reseau_utilite_conforme])
        erreurs = AnalyseurEntete(chemin).analyser()
        cibles = [e for e in erreurs if e.code == CODE_SRS_INVALIDE]
        assert len(cibles) == 1
        assert cibles[0].valeur_trouvee == "EPSG:4326"


# ---------------------------------------------------------------------------
# Tests de l'unicité gml:id
# ---------------------------------------------------------------------------


class TestUniciteGmlId:
    """Unicité globale des gml:id dans le fichier."""

    def test_aucun_doublon_aucune_erreur(self, gml_entete_conforme):
        erreurs = AnalyseurEntete(gml_entete_conforme).analyser()
        assert not any(e.code == CODE_GML_ID_DUPLIQUE for e in erreurs)

    def test_doublon_signale(self, chemin_gml_entete_tmp, membre_metadata_conforme):
        """Deux objets partageant le même gml:id : 1 erreur émise."""
        # ReseauUtilite avec le même gml:id que Metadata → conflit.
        r = creer_reseau_utilite_conforme("metadata_001")
        chemin = chemin_gml_entete_tmp([membre_metadata_conforme, r])
        erreurs = AnalyseurEntete(chemin).analyser()
        doublons = [e for e in erreurs if e.code == CODE_GML_ID_DUPLIQUE]
        assert len(doublons) == 1
        assert doublons[0].element == "metadata_001"
        assert doublons[0].valeur_trouvee == "2"


# ---------------------------------------------------------------------------
# Tests de la génération du rapport JSON
# ---------------------------------------------------------------------------


class TestGenererRapport:
    """Sérialisation du rapport JSON."""

    @pytest.fixture
    def chemin_gml_vide(self, tmp_path: Path) -> Path:
        chemin = tmp_path / "vide.gml"
        chemin.touch()
        return chemin

    def _erreur_test(self) -> ErreurEntete:
        return ErreurEntete(
            code=CODE_SRS_INVALIDE,
            element="SRS",
            valeur_trouvee="EPSG:4326",
            valeur_attendue="énumération SRSValue",
            message="SRS hors liste",
        )

    def test_fichier_cree(self, chemin_gml_vide):
        chemin = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        assert chemin.exists()
        assert chemin.suffix == ".json"

    def test_nom_suffixe_e113(self, chemin_gml_vide):
        chemin = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        assert "_controle_e113" in chemin.name

    def test_rapport_conforme_si_aucune_erreur(self, chemin_gml_vide):
        chemin = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["conformite"] == "CONFORME"
        assert rapport["nb_erreurs"] == 0

    def test_rapport_non_conforme_avec_erreurs(self, chemin_gml_vide):
        chemin = generer_rapport(chemin_gml_vide, [self._erreur_test()], chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["conformite"] == "NON_CONFORME"
        assert rapport["nb_erreurs"] == 1

    def test_champ_type_controle(self, chemin_gml_vide):
        rapport = _construire_rapport(chemin_gml_vide, [])
        assert rapport["type_controle"] == "E113_ENTETE"

    def test_champs_attendus_presents(self, chemin_gml_vide):
        rapport = _construire_rapport(chemin_gml_vide, [])
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
        assert set(rapport.keys()) == attendus

    def test_erreurs_serialisees(self, chemin_gml_vide):
        chemin = generer_rapport(chemin_gml_vide, [self._erreur_test()], chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            rapport = json.load(f)
        err = rapport["erreurs"][0]
        assert err["code"] == CODE_SRS_INVALIDE
        assert err["valeur_trouvee"] == "EPSG:4326"

    def test_chemin_sans_repertoire_sortie(self, tmp_path: Path):
        """Sans output_dir, le JSON est créé à côté du GML."""
        chemin_gml = tmp_path / "fichier.gml"
        chemin = _resoudre_chemin_sortie(chemin_gml, None)
        assert chemin.parent == chemin_gml.parent

    def test_chemin_avec_repertoire_sortie(self, tmp_path: Path):
        """Avec output_dir, le JSON est dans le répertoire indiqué."""
        chemin_gml = tmp_path / "fichier.gml"
        dossier = tmp_path / "out"
        dossier.mkdir()
        chemin = _resoudre_chemin_sortie(chemin_gml, dossier)
        assert chemin.parent == dossier
