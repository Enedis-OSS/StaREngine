"""
Tests du controle E600 : conformite du materiel de jonction au catalogue.

Couvre :
  - la normalisation des valeurs comparees au catalogue
  - la construction de l'index du catalogue (valide / vide / invalide)
  - le chargement du catalogue (absent / illisible / vide / valide)
  - le filtre de perimetre (lien materiel, Statut, TypeJonction)
  - le classement des anomalies (domaine, fabricant, modele, association)
  - la resolution du lien jonction -> materiel
  - la construction du GeoJSON d'ecarts
  - l'execution CLI (catalogue mocke + integration sur le vrai catalogue)
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any
from unittest.mock import patch

from controle_e600 import (
    FICHIER_JONCTION,
    FICHIER_MATERIEL,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    STATUT_CONTROLE,
    TYPE_COUPLE_NON_REFERENCE,
    TYPE_DOMAINE_HORS_CATALOGUE,
    TYPE_FABRICANT_NON_REFERENCE,
    TYPE_MATERIEL_INTROUVABLE,
    TYPE_MODELE_NON_REFERENCE,
    TYPES_JONCTION_CONTROLES,
    CatalogueMateriel,
    _construire_catalogue,
    charger_catalogue,
    classifier_materiel,
    compter_jonctions_a_controler,
    construire_geojson_ecarts,
    detecter_anomalies,
    est_a_controler,
    executer_controle_cli,
    indexer_materiels,
    normaliser_valeur,
)
from utils_tests import (
    construire_feature_jonction,
    construire_feature_materiel,
    ecrire_collection,
    ecrire_collection_avec_crs,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# Combinaisons presentes dans le vrai catalogue du depot
_FABRICANT_REEL: str = "3M"
_MODELE_HTA_REEL: str = "DTIM-PS-RSM-24-50(50)/240 AL/CU"
_MODELE_BT_REEL: str = "BPR Papier DIPH-TRIP 100-150"


def _catalogue_mock() -> CatalogueMateriel:
    """Catalogue reduit et volontairement NON cartesien.

    L'association (hta, maec, modele-b) est absente alors que « maec » et
    « modele-b » existent chacun : c'est le seul moyen de couvrir l'anomalie
    d'association, le vrai catalogue etant aujourd'hui cartesien.
    """
    return CatalogueMateriel(
        entrees=frozenset(
            {
                ("hta", "3m", "modele-a"),
                ("hta", "3m", "modele-b"),
                ("hta", "maec", "modele-a"),
                ("bt", "3m", "modele-c"),
            }
        ),
        fabricants_par_domaine={"hta": frozenset({"3m", "maec"}), "bt": frozenset({"3m"})},
        modeles_par_domaine={"hta": frozenset({"modele-a", "modele-b"}), "bt": frozenset({"modele-c"})},
    )


def _jeu_conforme(tmp_path: Any) -> None:
    """Ecrit une jonction HTA conforme au catalogue mocke et son materiel."""
    ecrire_collection(
        str(tmp_path / FICHIER_JONCTION),
        [construire_feature_jonction("j1", materiel_href="m1")],
    )
    ecrire_collection(
        str(tmp_path / FICHIER_MATERIEL),
        [construire_feature_materiel("m1", fabricant="3M", modele="Modele-A")],
    )


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #


class TestNormaliserValeur:
    """Tests de normaliser_valeur."""

    def test_minuscule_et_strip(self) -> None:
        assert normaliser_valeur("  3M ") == "3m"

    def test_none(self) -> None:
        assert normaliser_valeur(None) is None

    def test_chaine_vide_assimilee_a_absente(self) -> None:
        assert normaliser_valeur("   ") is None

    def test_valeur_non_textuelle_convertie(self) -> None:
        assert normaliser_valeur(24) == "24"

    def test_saut_de_ligne_interne_replie(self) -> None:
        """Cas reel : le GML source replie les libelles longs sur plusieurs lignes."""
        assert normaliser_valeur("DDC 240-35 \nv2006") == "ddc 240-35 v2006"

    def test_espaces_multiples_replies(self) -> None:
        assert normaliser_valeur("DDC   240-35\tv2006") == "ddc 240-35 v2006"


# --------------------------------------------------------------------------- #
# Construction et chargement du catalogue
# --------------------------------------------------------------------------- #


class TestConstruireCatalogue:
    """Tests de _construire_catalogue."""

    def test_index_normalise(self) -> None:
        catalogue = _construire_catalogue(
            {"entrees": [{"domaineTension": "HTA", "fabricant": " 3M ", "modele": "DTIM"}]}
        )
        assert catalogue is not None
        assert catalogue.entrees == frozenset({("hta", "3m", "dtim")})
        assert catalogue.fabricants_par_domaine["hta"] == frozenset({"3m"})
        assert catalogue.modeles_par_domaine["hta"] == frozenset({"dtim"})

    def test_domaines_exposes(self) -> None:
        catalogue = _construire_catalogue(
            {
                "entrees": [
                    {"domaineTension": "HTA", "fabricant": "3M", "modele": "A"},
                    {"domaineTension": "BT", "fabricant": "3M", "modele": "B"},
                ]
            }
        )
        assert catalogue is not None
        assert catalogue.domaines == frozenset({"hta", "bt"})

    def test_entrees_incompletes_ignorees(self) -> None:
        catalogue = _construire_catalogue(
            {
                "entrees": [
                    {"domaineTension": "HTA", "fabricant": "3M"},
                    {"domaineTension": "HTA", "fabricant": "3M", "modele": "A"},
                ]
            }
        )
        assert catalogue is not None
        assert catalogue.entrees == frozenset({("hta", "3m", "a")})

    def test_doublons_dedupliques(self) -> None:
        catalogue = _construire_catalogue(
            {
                "entrees": [
                    {"domaineTension": "HTA", "fabricant": "3M", "modele": "A"},
                    {"domaineTension": "hta", "fabricant": "3m", "modele": "a"},
                ]
            }
        )
        assert catalogue is not None
        assert len(catalogue.entrees) == 1

    def test_liste_entrees_vide(self) -> None:
        assert _construire_catalogue({"entrees": []}) is None

    def test_cle_entrees_absente(self) -> None:
        assert _construire_catalogue({"version": "1.0.0"}) is None

    def test_racine_non_dictionnaire(self) -> None:
        assert _construire_catalogue([{"domaineTension": "HTA"}]) is None

    def test_entrees_toutes_invalides(self) -> None:
        assert _construire_catalogue({"entrees": ["texte", 42, {}]}) is None


class TestChargerCatalogue:
    """Tests de charger_catalogue."""

    def test_fichier_absent(self) -> None:
        catalogue, erreur = charger_catalogue("/chemin/inexistant.json")
        assert catalogue is None
        assert erreur is not None
        assert "introuvable" in erreur

    def test_json_invalide(self, tmp_path: Any) -> None:
        chemin = tmp_path / "catalogue.json"
        chemin.write_text("{ pas du json", encoding="utf-8")
        catalogue, erreur = charger_catalogue(str(chemin))
        assert catalogue is None
        assert erreur is not None
        assert "illisible" in erreur

    def test_catalogue_vide(self, tmp_path: Any) -> None:
        chemin = tmp_path / "catalogue.json"
        chemin.write_text(json.dumps({"entrees": []}), encoding="utf-8")
        catalogue, erreur = charger_catalogue(str(chemin))
        assert catalogue is None
        assert erreur is not None
        assert "vide ou invalide" in erreur

    def test_catalogue_valide(self, tmp_path: Any) -> None:
        chemin = tmp_path / "catalogue.json"
        contenu = {"entrees": [{"domaineTension": "BT", "fabricant": "3M", "modele": "A"}]}
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        catalogue, erreur = charger_catalogue(str(chemin))
        assert erreur is None
        assert catalogue is not None
        assert len(catalogue.entrees) == 1

    def test_catalogue_reel_du_depot(self) -> None:
        """Le catalogue versionne se charge et couvre les domaines BT et HTA."""
        from controle_e600 import CHEMIN_CATALOGUE

        catalogue, erreur = charger_catalogue(CHEMIN_CATALOGUE)
        assert erreur is None
        assert catalogue is not None
        assert catalogue.domaines == frozenset({"bt", "hta"})
        assert len(catalogue.entrees) > 0


# --------------------------------------------------------------------------- #
# Perimetre
# --------------------------------------------------------------------------- #


class TestEstAControler:
    """Tests du filtre de perimetre est_a_controler."""

    def test_jonction_eligible(self) -> None:
        props = construire_feature_jonction("j1", materiel_href="m1")["properties"]
        assert est_a_controler(props) is True

    def test_derivation_eligible(self) -> None:
        props = construire_feature_jonction("j1", type_jonction="Derivation", materiel_href="m1")["properties"]
        assert est_a_controler(props) is True

    def test_statut_hors_perimetre(self) -> None:
        props = construire_feature_jonction("j1", statut="Functional", materiel_href="m1")["properties"]
        assert est_a_controler(props) is False

    def test_type_jonction_hors_perimetre(self) -> None:
        props = construire_feature_jonction("j1", type_jonction="ExtremiteReseau", materiel_href="m1")["properties"]
        assert est_a_controler(props) is False

    def test_sans_materiel_href(self) -> None:
        props = construire_feature_jonction("j1", materiel_href=None)["properties"]
        assert est_a_controler(props) is False

    def test_materiel_href_vide(self) -> None:
        props = construire_feature_jonction("j1", materiel_href="   ")["properties"]
        assert est_a_controler(props) is False

    def test_les_deux_types_declares_sont_controles(self) -> None:
        assert TYPES_JONCTION_CONTROLES == frozenset({"Derivation", "Jonction"})


# --------------------------------------------------------------------------- #
# Classement des anomalies
# --------------------------------------------------------------------------- #


class TestClassifierMateriel:
    """Tests de classifier_materiel (fonction pure)."""

    def test_materiel_conforme(self) -> None:
        assert classifier_materiel("HTA", "3M", "Modele-A", _catalogue_mock()) == []

    def test_casse_et_espaces_ignores(self) -> None:
        assert classifier_materiel(" hta ", " 3m", "MODELE-A ", _catalogue_mock()) == []

    def test_domaine_hors_catalogue(self) -> None:
        assert classifier_materiel("HTB", "3M", "Modele-A", _catalogue_mock()) == [TYPE_DOMAINE_HORS_CATALOGUE]

    def test_domaine_absent(self) -> None:
        assert classifier_materiel(None, "3M", "Modele-A", _catalogue_mock()) == [TYPE_DOMAINE_HORS_CATALOGUE]

    def test_domaine_invalide_court_circuite_les_autres_regles(self) -> None:
        """Sans domaine de reference, Fabricant et Modele ne sont pas evaluables."""
        codes = classifier_materiel("HTB", "Inconnu", "Inconnu", _catalogue_mock())
        assert codes == [TYPE_DOMAINE_HORS_CATALOGUE]

    def test_fabricant_non_reference(self) -> None:
        assert classifier_materiel("HTA", "Inconnu", "Modele-A", _catalogue_mock()) == [TYPE_FABRICANT_NON_REFERENCE]

    def test_modele_non_reference(self) -> None:
        assert classifier_materiel("HTA", "3M", "Inconnu", _catalogue_mock()) == [TYPE_MODELE_NON_REFERENCE]

    def test_fabricant_et_modele_non_references_cumulent(self) -> None:
        codes = classifier_materiel("HTA", "Inconnu", "Inconnu", _catalogue_mock())
        assert codes == [TYPE_FABRICANT_NON_REFERENCE, TYPE_MODELE_NON_REFERENCE]

    def test_fabricant_absent(self) -> None:
        assert classifier_materiel("HTA", None, "Modele-A", _catalogue_mock()) == [TYPE_FABRICANT_NON_REFERENCE]

    def test_modele_absent(self) -> None:
        assert classifier_materiel("HTA", "3M", None, _catalogue_mock()) == [TYPE_MODELE_NON_REFERENCE]

    def test_association_non_referencee(self) -> None:
        """Les deux valeurs existent pour HTA, mais pas leur association."""
        assert classifier_materiel("HTA", "MAEC", "Modele-B", _catalogue_mock()) == [TYPE_COUPLE_NON_REFERENCE]

    def test_valeur_valide_dans_un_autre_domaine(self) -> None:
        """Modele-C n'est reference qu'en BT : il est invalide en HTA."""
        assert classifier_materiel("HTA", "3M", "Modele-C", _catalogue_mock()) == [TYPE_MODELE_NON_REFERENCE]


# --------------------------------------------------------------------------- #
# Index des materiels
# --------------------------------------------------------------------------- #


class TestIndexerMateriels:
    """Tests de indexer_materiels."""

    def test_index_par_identifiant(self) -> None:
        index = indexer_materiels(
            [
                construire_feature_materiel("m1", fabricant="3M", modele="A"),
                construire_feature_materiel("m2", fabricant="MAEC", modele="B"),
            ]
        )
        assert set(index) == {"m1", "m2"}
        assert index["m1"]["Fabricant"] == "3M"

    def test_materiel_sans_identifiant_ignore(self) -> None:
        feature = construire_feature_materiel("m1")
        feature["properties"].pop("id")
        assert indexer_materiels([feature]) == {}

    def test_liste_vide(self) -> None:
        assert indexer_materiels([]) == {}


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_aucune_anomalie(self) -> None:
        jonctions = [construire_feature_jonction("j1", materiel_href="m1")]
        materiels = indexer_materiels([construire_feature_materiel("m1", fabricant="3M", modele="Modele-A")])
        assert detecter_anomalies(jonctions, materiels, _catalogue_mock()) == []

    def test_materiel_introuvable(self) -> None:
        jonctions = [construire_feature_jonction("j1", materiel_href="m_absent")]
        anomalies = detecter_anomalies(jonctions, {}, _catalogue_mock())
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_MATERIEL_INTROUVABLE
        assert anomalies[0]["id_materiel"] == "m_absent"
        assert anomalies[0]["fabricant"] is None

    def test_hors_perimetre_ignore(self) -> None:
        jonctions = [
            construire_feature_jonction("j1", statut="Functional", materiel_href="m_absent"),
            construire_feature_jonction("j2", type_jonction="ExtremiteReseau", materiel_href="m_absent"),
            construire_feature_jonction("j3", materiel_href=None),
        ]
        assert detecter_anomalies(jonctions, {}, _catalogue_mock()) == []

    def test_deux_anomalies_pour_une_jonction(self) -> None:
        jonctions = [construire_feature_jonction("j1", materiel_href="m1")]
        materiels = indexer_materiels([construire_feature_materiel("m1", fabricant="X", modele="Y")])
        anomalies = detecter_anomalies(jonctions, materiels, _catalogue_mock())
        assert [a["type_anomalie"] for a in anomalies] == [
            TYPE_FABRICANT_NON_REFERENCE,
            TYPE_MODELE_NON_REFERENCE,
        ]
        assert {a["id_jonction"] for a in anomalies} == {"j1"}

    def test_href_espace_resolu(self) -> None:
        """Un href entoure d'espaces resout le materiel sans faux positif."""
        jonctions = [construire_feature_jonction("j1", materiel_href=" m1 ")]
        materiels = indexer_materiels([construire_feature_materiel("m1", fabricant="3M", modele="Modele-A")])
        assert detecter_anomalies(jonctions, materiels, _catalogue_mock()) == []

    def test_valeurs_brutes_conservees(self) -> None:
        jonctions = [construire_feature_jonction("j1", domaine_tension="HTB", materiel_href="m1")]
        materiels = indexer_materiels([construire_feature_materiel("m1", fabricant="3M", modele="Modele-A")])
        anomalie = detecter_anomalies(jonctions, materiels, _catalogue_mock())[0]
        assert anomalie["domaine_tension"] == "HTB"
        assert anomalie["type_jonction"] == "Jonction"
        assert anomalie["geometrie"]["type"] == "Point"

    def test_plusieurs_jonctions_partagent_un_materiel(self) -> None:
        jonctions = [
            construire_feature_jonction("j1", materiel_href="m1"),
            construire_feature_jonction("j2", materiel_href="m1"),
        ]
        materiels = indexer_materiels([construire_feature_materiel("m1", fabricant="X", modele="Modele-A")])
        anomalies = detecter_anomalies(jonctions, materiels, _catalogue_mock())
        assert {a["id_jonction"] for a in anomalies} == {"j1", "j2"}


class TestCompterJonctionsAControler:
    """Tests de compter_jonctions_a_controler."""

    def test_comptage(self) -> None:
        jonctions = [
            construire_feature_jonction("j1", materiel_href="m1"),
            construire_feature_jonction("j2", type_jonction="Derivation", materiel_href="m2"),
            construire_feature_jonction("j3", statut="Projected", materiel_href="m3"),
            construire_feature_jonction("j4", materiel_href=None),
        ]
        assert compter_jonctions_a_controler(jonctions) == 2

    def test_liste_vide(self) -> None:
        assert compter_jonctions_a_controler([]) == 0


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_FABRICANT_NON_REFERENCE,
            "id_jonction": "j1",
            "id_materiel": "m1",
            "type_jonction": "Jonction",
            "domaine_tension": "HTA",
            "fabricant": "Inconnu",
            "modele": "Modele-A",
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }

    def test_socle_commun(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["code_controle"] == "E600"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_entite"] == "j1"
        assert props["type_anomalie"] == TYPE_FABRICANT_NON_REFERENCE
        assert props["description"]

    def test_proprietes_metier(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["fichier_source"] == FICHIER_JONCTION
        assert props["id_jonction"] == "j1"
        assert props["id_materiel"] == "m1"
        assert props["domaine_tension"] == "HTA"
        assert props["fabricant"] == "Inconnu"
        assert props["modele"] == "Modele-A"

    def test_geometrie_de_la_jonction_conservee(self) -> None:
        geom = construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"]
        assert geom["type"] == "Point"
        assert geom["coordinates"] == [1.0, 2.0, 3.0]

    def test_description_par_type(self) -> None:
        anomalie = {**self._anomalie(), "type_anomalie": TYPE_MATERIEL_INTROUVABLE}
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert "n'existe pas" in props["description"]

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI (catalogue mocke)
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli avec catalogue mocke."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    @patch("controle_e600.charger_catalogue")
    def test_catalogue_indisponible_erreur(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (None, "Catalogue introuvable : x")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "Catalogue" in resultat["erreur"]

    @patch("controle_e600.charger_catalogue")
    def test_fichiers_absents_non_bloquants(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_jonction_absent"] is True
        assert resultat["fichier_materiel_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    @patch("controle_e600.charger_catalogue")
    def test_nominal_conforme(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        _jeu_conforme(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_jonctions_controlees"] == 1
        assert resultat["nombre_materiels"] == 1
        assert resultat["nombre_entrees_catalogue"] == 4

    @patch("controle_e600.charger_catalogue")
    def test_fichier_materiel_absent_signale_le_lien_rompu(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", materiel_href="m1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["fichier_materiel_absent"] is True
        assert resultat["anomalies_par_type"] == {TYPE_MATERIEL_INTROUVABLE: 1}

    @patch("controle_e600.charger_catalogue")
    def test_nominal_non_conforme(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", materiel_href="m1")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_MATERIEL),
            [construire_feature_materiel("m1", fabricant="Inconnu", modele="Modele-A")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
        assert resultat["anomalies_par_type"] == {TYPE_FABRICANT_NON_REFERENCE: 1}
        assert resultat["priorite"] == "majeur"

    @patch("controle_e600.charger_catalogue")
    def test_fichier_ecarts_cree(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", materiel_href="m_absent")],
        )
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    @patch("controle_e600.charger_catalogue")
    def test_aucun_fichier_sans_anomalie(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        _jeu_conforme(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    @patch("controle_e600.charger_catalogue")
    def test_crs_propage(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection_avec_crs(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", materiel_href="m_absent")],
            "EPSG:2154",
        )
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert "2154" in ecarts["crs"]["properties"]["name"]

    @patch("controle_e600.charger_catalogue")
    def test_rapport_champs_obligatoires(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        _jeu_conforme(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "anomalies_par_type",
            "nombre_jonctions_analysees",
            "nombre_jonctions_controlees",
            "nombre_materiels",
            "nombre_entrees_catalogue",
            "fichier_jonction_absent",
            "fichier_materiel_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Integration sur le vrai catalogue du depot
# --------------------------------------------------------------------------- #


class TestIntegrationCatalogueReel:
    """Tests utilisant le catalogue reel versionne dans le depot."""

    def test_materiel_hta_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", domaine_tension="HTA", materiel_href="m1")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_MATERIEL),
            [construire_feature_materiel("m1", fabricant=_FABRICANT_REEL, modele=_MODELE_HTA_REEL)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_entrees_catalogue"] > 0

    def test_materiel_bt_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", domaine_tension="BT", materiel_href="m1")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_MATERIEL),
            [construire_feature_materiel("m1", fabricant=_FABRICANT_REEL, modele=_MODELE_BT_REEL)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0

    def test_modele_bt_utilise_en_hta_signale(self, tmp_path: Any) -> None:
        """Le catalogue est indexe par domaine : un modele BT est invalide en HTA."""
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", domaine_tension="HTA", materiel_href="m1")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_MATERIEL),
            [construire_feature_materiel("m1", fabricant=_FABRICANT_REEL, modele=_MODELE_BT_REEL)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_MODELE_NON_REFERENCE: 1}

    def test_jonction_htb_signalee(self, tmp_path: Any) -> None:
        """Le catalogue ne couvre que BT et HTA : une jonction HTB est signalee."""
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", domaine_tension="HTB", materiel_href="m1")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_MATERIEL),
            [construire_feature_materiel("m1", fabricant=_FABRICANT_REEL, modele=_MODELE_HTA_REEL)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_DOMAINE_HORS_CATALOGUE: 1}

    def test_modele_avec_saut_de_ligne_reconnu(self, tmp_path: Any) -> None:
        """Cas reel (Echantillon/) : « DDC 240-35 \\nv2006 » designe bien le modele
        « DDC 240-35 v2006 » du catalogue. Sans repliement des espaces internes,
        ce materiel conforme serait signale a tort.
        """
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", domaine_tension="BT", materiel_href="m1")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_MATERIEL),
            [construire_feature_materiel("m1", fabricant="SICAME", modele="DDC 240-35 \nv2006")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0

    def test_fabricant_inconnu_signale(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", domaine_tension="HTA", materiel_href="m1")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_MATERIEL),
            [construire_feature_materiel("m1", fabricant="FabricantFictif", modele=_MODELE_HTA_REEL)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_FABRICANT_NON_REFERENCE: 1}


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Le materiel est controle identiquement en V1.0 et V1.1.

    Les champs additionnels de la V1.1 (Commentaire sur la jonction, Etiquette)
    n'interviennent ni dans le perimetre ni dans la comparaison au catalogue.
    """

    @patch("controle_e600.charger_catalogue")
    def test_v11_champs_extra_sans_effet(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [
                construire_feature_jonction(
                    "j1",
                    materiel_href="m1",
                    proprietes_extra={"Commentaire": "note", "Etiquette": "E1"},
                )
            ],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_MATERIEL),
            [
                construire_feature_materiel(
                    "m1",
                    fabricant="3M",
                    modele="Modele-A",
                    proprietes_extra={"NumeroLot": "LOT-2024-001", "NumeroSerie": "SN-12345"},
                )
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    @patch("controle_e600.charger_catalogue")
    def test_statut_est_le_meme_dans_les_deux_versions(self, mock_cat: Any, tmp_path: Any) -> None:
        mock_cat.return_value = (_catalogue_mock(), None)
        assert STATUT_CONTROLE == "UnderCommissionning"
