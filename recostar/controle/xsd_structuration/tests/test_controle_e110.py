"""
Tests unitaires du module controle_e110.
Couvre l'analyse GML et la génération de rapport JSON.
"""

import json

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import (
    Element,  # nosec B405
)

from controle_e110 import (
    AnalyseurGML,
    _construire_rapport,
    _extraire_gml_id,
    _nom_local,
    _resoudre_chemin_sortie,
    generer_rapport,
)
from sequenceur_xsd import ErreurOrdre
from utils_gml import creer_feature_member

NS_GML = "http://www.opengis.net/gml/3.2"
NS_RECOSTAR = "http://StaR-Elec.com"


# ---------------------------------------------------------------------------
# Tests des utilitaires namespace
# ---------------------------------------------------------------------------


class TestUtilitairesNamespace:
    """Tests des fonctions utilitaires de manipulation de namespace."""

    def test_nom_local_avec_namespace(self):
        """Extrait le nom local d'un tag qualifié."""
        assert _nom_local(f"{{{NS_GML}}}featureMember") == "featureMember"

    def test_nom_local_avec_namespace_recostar(self):
        """Extrait le nom local d'un tag RecoStar."""
        assert _nom_local(f"{{{NS_RECOSTAR}}}RPD_Jonction_Reco") == "RPD_Jonction_Reco"

    def test_nom_local_sans_namespace(self):
        """Retourne le tag inchangé si aucun namespace."""
        assert _nom_local("Statut") == "Statut"

    def test_extraire_gml_id_present(self):
        """Extrait gml:id si présent."""
        elem = Element("test")
        elem.set(f"{{{NS_GML}}}id", "mon_id")
        assert _extraire_gml_id(elem) == "mon_id"

    def test_extraire_gml_id_absent(self):
        """Retourne '<sans id>' si gml:id est absent."""
        elem = Element("test")
        assert _extraire_gml_id(elem) == "<sans id>"


# ---------------------------------------------------------------------------
# Tests de AnalyseurGML
# ---------------------------------------------------------------------------


class TestAnalyseurGML:
    """Tests de l'analyse des fichiers GML."""

    def test_analyser_fichier_conforme(self, chemin_gml_tmp, membre_jonction_conforme):
        """Un fichier GML conforme ne génère aucune erreur."""
        chemin = chemin_gml_tmp([membre_jonction_conforme])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        assert erreurs == []

    def test_analyser_detecte_ordre_incorrect(self, chemin_gml_tmp, membre_jonction_ordre_incorrect):
        """Détecte une erreur d'ordre dans un fichier GML non conforme."""
        chemin = chemin_gml_tmp([membre_jonction_ordre_incorrect])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        ordres = [e for e in erreurs if e.type_erreur == "ORDRE_INCORRECT"]
        assert len(ordres) >= 1

    def test_analyser_ignore_elements_ep(self, chemin_gml_tmp, membre_ep_ignore):
        """Les featureMember EP sont ignorés et ne génèrent pas d'erreur."""
        chemin = chemin_gml_tmp([membre_ep_ignore])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        assert erreurs == []

    def test_analyser_multi_membres(
        self,
        chemin_gml_tmp,
        membre_aerien_conforme,
        membre_jonction_ordre_incorrect,
        membre_ep_ignore,
    ):
        """Analyse plusieurs featureMember : seul le non-conforme génère une erreur."""
        membres = [
            membre_aerien_conforme,
            membre_jonction_ordre_incorrect,
            membre_ep_ignore,
        ]
        chemin = chemin_gml_tmp(membres)
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        assert any(e.gml_id == "jonction_002" for e in erreurs)
        assert not any(e.gml_id == "aerien_001" for e in erreurs)

    def test_analyser_cable_electrique_conforme(self, chemin_gml_tmp, membre_cable_electrique_conforme):
        """RPD_CableElectrique_Reco conforme ne génère aucune erreur."""
        chemin = chemin_gml_tmp([membre_cable_electrique_conforme])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        assert erreurs == []

    def test_analyser_type_non_rpd_ignore(self, chemin_gml_tmp):
        """Les featureMember non-RPD (Metadata, ReseauUtilite) sont ignorés."""
        membre_metadata = creer_feature_member("Metadata", "meta_001", ["Datecreation", "Logiciel"])
        chemin = chemin_gml_tmp([membre_metadata])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        assert erreurs == []

    def test_analyser_feature_member_vide_ignore(self, chemin_gml_tmp):
        """Un featureMember vide ne génère aucune erreur."""
        membre_vide = Element(f"{{{NS_GML}}}featureMember")
        chemin = chemin_gml_tmp([membre_vide])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        assert erreurs == []

    def test_analyser_erreurs_contiennent_gml_id(self, chemin_gml_tmp, membre_jonction_ordre_incorrect):
        """Les erreurs contiennent le gml:id de l'élément concerné."""
        chemin = chemin_gml_tmp([membre_jonction_ordre_incorrect])
        analyseur = AnalyseurGML(chemin)
        erreurs = analyseur.analyser()
        assert all(e.gml_id is not None for e in erreurs)


# ---------------------------------------------------------------------------
# Tests de la génération de rapport JSON
# ---------------------------------------------------------------------------


class TestGenererRapport:
    """Tests de la génération du fichier JSON de rapport."""

    def _creer_erreur(self) -> ErreurOrdre:
        """Crée une erreur de test."""
        return ErreurOrdre(
            type_rpd="RPD_Jonction_Reco",
            gml_id="jonction_001",
            type_erreur="ORDRE_INCORRECT",
            position=2,
            element_trouve="conteneur",
            element_attendu="conteneur",
            message="Erreur test",
        )

    def test_rapport_cree_fichier_json(self, chemin_gml_vide):
        """Vérifie que generer_rapport crée un fichier JSON."""
        chemin_sortie = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        assert chemin_sortie.exists()
        assert chemin_sortie.suffix == ".json"

    def test_rapport_nom_base_sur_gml(self, tmp_path):
        """Le nom du JSON est dérivé du nom du fichier GML."""
        chemin_gml = tmp_path / "monFichier.gml"
        chemin_gml.touch()
        chemin_sortie = generer_rapport(chemin_gml, [], tmp_path)
        assert "monFichier" in chemin_sortie.name

    def test_rapport_sans_repertoire_sortie(self, chemin_gml_vide):
        """Sans output_dir, le JSON est créé dans le même répertoire que le GML."""
        chemin_sortie = generer_rapport(chemin_gml_vide, [])
        assert chemin_sortie.parent == chemin_gml_vide.parent

    def test_rapport_avec_repertoire_sortie(self, chemin_gml_vide, tmp_path):
        """Avec output_dir, le JSON est créé dans le répertoire spécifié."""
        dossier_sortie = tmp_path / "sortie"
        dossier_sortie.mkdir()
        chemin_sortie = generer_rapport(chemin_gml_vide, [], dossier_sortie)
        assert chemin_sortie.parent == dossier_sortie

    def test_rapport_json_valide(self, chemin_gml_vide):
        """Le fichier JSON généré est valide et lisible."""
        erreurs = [self._creer_erreur()]
        chemin_sortie = generer_rapport(chemin_gml_vide, erreurs, chemin_gml_vide.parent)
        with open(chemin_sortie, encoding="utf-8") as f:
            contenu = json.load(f)
        assert isinstance(contenu, dict)

    def test_rapport_structure_attendue(self, chemin_gml_vide):
        """Le rapport JSON contient les champs attendus."""
        erreurs = [self._creer_erreur()]
        chemin_sortie = generer_rapport(chemin_gml_vide, erreurs, chemin_gml_vide.parent)
        with open(chemin_sortie, encoding="utf-8") as f:
            contenu = json.load(f)
        champs_attendus = {
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
        assert champs_attendus == set(contenu.keys())

    def test_rapport_nb_erreurs_correct(self, chemin_gml_vide):
        """Le champ nb_erreurs reflète le nombre réel d'erreurs."""
        erreurs = [self._creer_erreur(), self._creer_erreur()]
        chemin_sortie = generer_rapport(chemin_gml_vide, erreurs, chemin_gml_vide.parent)
        with open(chemin_sortie, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["nb_erreurs"] == 2

    def test_rapport_sans_erreur(self, chemin_gml_vide):
        """Un rapport sans erreur contient une liste vide et nb_erreurs=0."""
        chemin_sortie = generer_rapport(chemin_gml_vide, [], chemin_gml_vide.parent)
        with open(chemin_sortie, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["nb_erreurs"] == 0
        assert contenu["erreurs"] == []

    def test_rapport_erreurs_serialisees(self, chemin_gml_vide):
        """Les erreurs sont correctement sérialisées dans le rapport."""
        erreur = self._creer_erreur()
        chemin_sortie = generer_rapport(chemin_gml_vide, [erreur], chemin_gml_vide.parent)
        with open(chemin_sortie, encoding="utf-8") as f:
            contenu = json.load(f)
        assert len(contenu["erreurs"]) == 1
        err_dict = contenu["erreurs"][0]
        assert err_dict["type_rpd"] == "RPD_Jonction_Reco"
        assert err_dict["type_erreur"] == "ORDRE_INCORRECT"


# ---------------------------------------------------------------------------
# Tests de _construire_rapport et _resoudre_chemin_sortie
# ---------------------------------------------------------------------------


class TestUtilitairesRapport:
    """Tests des fonctions utilitaires de rapport."""

    def test_construire_rapport_champs(self, chemin_gml_vide):
        """Vérifie les champs du dictionnaire rapport."""
        rapport = _construire_rapport(chemin_gml_vide, [])
        assert "fichier" in rapport
        assert "date_controle" in rapport
        assert "conformite" in rapport
        assert "nb_erreurs" in rapport
        assert "erreurs" in rapport

    def test_construire_rapport_conforme_sans_erreur(self, chemin_gml_vide):
        """Sans erreur, le champ conformite vaut 'CONFORME'."""
        rapport = _construire_rapport(chemin_gml_vide, [])
        assert rapport["conformite"] == "CONFORME"

    def test_construire_rapport_non_conforme_avec_erreurs(self, chemin_gml_vide):
        """Avec au moins une erreur, le champ conformite vaut 'NON_CONFORME'."""
        erreur = ErreurOrdre(
            type_rpd="RPD_Jonction_Reco",
            gml_id="id1",
            element_attendu="DomaineTension",
            element_trouve="Statut",
            position=1,
            message="ordre invalide",
            type_erreur="ORDRE_INCORRECT",
        )
        rapport = _construire_rapport(chemin_gml_vide, [erreur])
        assert rapport["conformite"] == "NON_CONFORME"

    def test_resoudre_chemin_sans_output_dir(self, tmp_path):
        """Sans output_dir, le JSON est dans le même dossier que le GML."""
        chemin_gml = tmp_path / "mon_fichier.gml"
        chemin_sortie = _resoudre_chemin_sortie(chemin_gml, None)
        assert chemin_sortie.parent == chemin_gml.parent
        assert chemin_sortie.suffix == ".json"

    def test_resoudre_chemin_avec_output_dir(self, tmp_path):
        """Avec output_dir, le JSON est dans le répertoire spécifié."""
        chemin_gml = tmp_path / "mon_fichier.gml"
        dossier = tmp_path / "output"
        dossier.mkdir()
        chemin_sortie = _resoudre_chemin_sortie(chemin_gml, dossier)
        assert chemin_sortie.parent == dossier
