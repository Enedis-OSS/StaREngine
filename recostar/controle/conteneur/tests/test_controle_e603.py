"""
Tests du controle E603 : caracteristiques de poteau conformes au catalogue.

Couvre :
  - la normalisation des mesures et la conversion d'unite
  - la construction de l'index du catalogue (par matiere, valide / invalide)
  - le chargement du catalogue (absent / illisible / vide / valide)
  - le filtre de perimetre (Statut)
  - le classement des anomalies (matiere, classe, effort, hauteur)
  - la construction du GeoJSON d'ecarts
  - l'execution CLI (catalogue mocke + integration sur le vrai catalogue)
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any
from unittest.mock import patch

from controle_e603 import (
    CHAMP_STATUT,
    FACTEURS_EFFORT,
    FACTEURS_HAUTEUR,
    FICHIER_SORTIE,
    FICHIER_SUPPORT,
    PRIORITE_ANOMALIE,
    STATUT_CONTROLE,
    TYPE_CLASSE_NON_REFERENCEE,
    TYPE_EFFORT_NON_REFERENCE,
    TYPE_HAUTEUR_NON_REFERENCEE,
    TYPE_MATIERE_HORS_CATALOGUE,
    UOM_EFFORT_CATALOGUE,
    UOM_HAUTEUR_CATALOGUE,
    CaracteristiquesPoteau,
    CataloguePoteau,
    _construire_catalogue,
    caracteristiques_depuis_proprietes,
    charger_catalogue,
    classifier_support,
    compter_supports_a_controler,
    compter_supports_non_conformes,
    construire_geojson_ecarts,
    detecter_anomalies,
    est_a_controler,
    normaliser_mesure,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _catalogue_mock() -> CataloguePoteau:
    """Catalogue reduit a deux matieres, aux axes volontairement disjoints.

    « c » n'est valide qu'en beton et « cfx » qu'en bois : le filtrage par
    matiere est ainsi verifiable, une valeur pouvant etre correcte pour une
    matiere et fautive pour l'autre.
    """
    return CataloguePoteau(
        classes_par_matiere={"beton": frozenset({"c", "d"}), "bois": frozenset({"cfx"})},
        efforts_par_matiere={"beton": frozenset({4.0, 12.5}), "bois": frozenset({1.0})},
        hauteurs_par_matiere={"beton": frozenset({12.0, 16.0}), "bois": frozenset({7.0})},
    )


def _caracteristiques(
    matiere: Any = "Beton",
    classe: Any = "D",
    effort: Any = 4.0,
    effort_uom: Any = "kN",
    hauteur: Any = 12.0,
    hauteur_uom: Any = "m",
) -> CaracteristiquesPoteau:
    return CaracteristiquesPoteau(matiere, classe, effort, effort_uom, hauteur, hauteur_uom)


def _feature_support(
    identifiant: str = "s1",
    statut: str = STATUT_CONTROLE,
    proprietes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Feature GeoJSON Point representant un support conforme au catalogue mocke."""
    props: dict[str, Any] = {
        "id": identifiant,
        CHAMP_STATUT: statut,
        "Matiere_href": "Beton",
        "Classe_href": "D",
        "Effort": 4.0,
        "Effort_uom": "kN",
        "HauteurPoteau": 12.0,
        "HauteurPoteau_uom": "m",
    }
    props.update(proprietes or {})
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
    }


# --------------------------------------------------------------------------- #
# Normalisation des mesures
# --------------------------------------------------------------------------- #


class TestNormaliserMesure:
    """Tests de normaliser_mesure."""

    def test_unite_du_catalogue_inchangee(self) -> None:
        assert normaliser_mesure(4.0, "kN", FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE) == 4.0

    def test_conversion_depuis_dan(self) -> None:
        """400 daN valent 4,00 kN — l'unite du catalogue."""
        assert normaliser_mesure(400.0, "daN", FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE) == 4.0

    def test_conversion_sans_bruit_flottant(self) -> None:
        """L'arrondi absorbe le bruit de la multiplication par un facteur decimal."""
        assert normaliser_mesure(1250.0, "daN", FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE) == 12.5

    def test_casse_de_l_unite_ignoree(self) -> None:
        assert normaliser_mesure(400.0, " DAN ", FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE) == 4.0

    def test_unite_absente_vaut_celle_du_catalogue(self) -> None:
        assert normaliser_mesure(4.0, None, FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE) == 4.0

    def test_unite_inconnue_rend_la_mesure_inexploitable(self) -> None:
        assert normaliser_mesure(4.0, "tonnes", FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE) is None

    def test_valeur_absente(self) -> None:
        assert normaliser_mesure(None, "kN", FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE) is None

    def test_valeur_non_numerique(self) -> None:
        assert normaliser_mesure("4.0", "kN", FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE) is None

    def test_booleen_refuse(self) -> None:
        """bool est un int en Python : le laisser passer donnerait un effort de 1 kN."""
        assert normaliser_mesure(True, "kN", FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE) is None

    def test_entier_accepte(self) -> None:
        assert normaliser_mesure(12, "m", FACTEURS_HAUTEUR, UOM_HAUTEUR_CATALOGUE) == 12.0

    def test_hauteur_depuis_centimetres(self) -> None:
        assert normaliser_mesure(1200.0, "cm", FACTEURS_HAUTEUR, UOM_HAUTEUR_CATALOGUE) == 12.0


# --------------------------------------------------------------------------- #
# Construction et chargement du catalogue
# --------------------------------------------------------------------------- #


class TestConstruireCatalogue:
    """Tests de _construire_catalogue."""

    def _donnees(self, **axes: Any) -> dict[str, Any]:
        base = {"classes": ["A", "B"], "efforts": ["4.00"], "hauteurs": ["12"]}
        base.update(axes)
        return {"correspondancesParMatiere": {"Beton": base}}

    def test_index_normalise(self) -> None:
        catalogue = _construire_catalogue(self._donnees())
        assert catalogue is not None
        assert catalogue.classes_par_matiere["beton"] == frozenset({"a", "b"})
        assert catalogue.efforts_par_matiere["beton"] == frozenset({4.0})
        assert catalogue.hauteurs_par_matiere["beton"] == frozenset({12.0})

    def test_matieres_exposees(self) -> None:
        donnees = {
            "correspondancesParMatiere": {
                "Beton": {"classes": ["A"], "efforts": ["4.00"], "hauteurs": ["12"]},
                "Bois": {"classes": ["CFX"], "efforts": ["1.00"], "hauteurs": ["7"]},
            }
        }
        catalogue = _construire_catalogue(donnees)
        assert catalogue is not None
        assert catalogue.matieres == frozenset({"beton", "bois"})

    def test_listes_de_premier_niveau_ignorees(self) -> None:
        """Seul correspondancesParMatiere est indexe : l'union accepterait une
        classe bois sur un poteau beton."""
        donnees = self._donnees()
        donnees["classes"] = [{"value": "ZZZ"}]
        catalogue = _construire_catalogue(donnees)
        assert catalogue is not None
        assert "zzz" not in catalogue.classes_par_matiere["beton"]

    def test_matiere_a_axe_vide_ecartee(self) -> None:
        assert _construire_catalogue(self._donnees(efforts=[])) is None

    def test_valeurs_non_numeriques_ignorees(self) -> None:
        catalogue = _construire_catalogue(self._donnees(efforts=["4.00", "abc"]))
        assert catalogue is not None
        assert catalogue.efforts_par_matiere["beton"] == frozenset({4.0})

    def test_correspondances_absentes(self) -> None:
        assert _construire_catalogue({"version": "2.0.0"}) is None

    def test_racine_non_dictionnaire(self) -> None:
        assert _construire_catalogue([1, 2, 3]) is None

    def test_matieres_toutes_invalides(self) -> None:
        assert _construire_catalogue({"correspondancesParMatiere": {"Beton": "texte"}}) is None


class TestChargerCatalogue:
    """Tests de charger_catalogue."""

    def test_fichier_absent(self) -> None:
        catalogue, erreur = charger_catalogue("/chemin/inexistant.json")
        assert catalogue is None
        assert erreur is not None and "introuvable" in erreur

    def test_json_invalide(self, tmp_path: Any) -> None:
        chemin = tmp_path / "catalogue.json"
        chemin.write_text("{ pas du json", encoding="utf-8")
        catalogue, erreur = charger_catalogue(str(chemin))
        assert catalogue is None
        assert erreur is not None and "illisible" in erreur

    def test_catalogue_vide(self, tmp_path: Any) -> None:
        chemin = tmp_path / "catalogue.json"
        chemin.write_text(json.dumps({"correspondancesParMatiere": {}}), encoding="utf-8")
        catalogue, erreur = charger_catalogue(str(chemin))
        assert catalogue is None
        assert erreur is not None and "vide ou invalide" in erreur

    def test_catalogue_reel_du_depot(self) -> None:
        """Le catalogue versionne se charge et couvre les trois matieres."""
        from controle_e603 import CHEMIN_CATALOGUE

        catalogue, erreur = charger_catalogue(CHEMIN_CATALOGUE)
        assert erreur is None
        assert catalogue is not None
        assert catalogue.matieres == frozenset({"bois", "beton", "metal"})

    def test_axes_reels_disjoints_par_matiere(self) -> None:
        """La classe « M » est propre au metal : le filtrage par matiere a un effet."""
        from controle_e603 import CHEMIN_CATALOGUE

        catalogue, _ = charger_catalogue(CHEMIN_CATALOGUE)
        assert catalogue is not None
        assert "m" in catalogue.classes_par_matiere["metal"]
        assert "m" not in catalogue.classes_par_matiere["beton"]


# --------------------------------------------------------------------------- #
# Perimetre
# --------------------------------------------------------------------------- #


class TestEstAControler:
    """Tests du filtre de perimetre."""

    def test_statut_controle(self) -> None:
        assert est_a_controler({CHAMP_STATUT: STATUT_CONTROLE}) is True

    def test_autre_statut(self) -> None:
        assert est_a_controler({CHAMP_STATUT: "Functional"}) is False

    def test_statut_absent(self) -> None:
        assert est_a_controler({}) is False


class TestCaracteristiquesDepuisProprietes:
    """Tests de l'extraction des caracteristiques."""

    def test_extraction(self) -> None:
        caracteristiques = caracteristiques_depuis_proprietes(_feature_support()["properties"])
        assert caracteristiques == _caracteristiques()

    def test_champs_absents(self) -> None:
        caracteristiques = caracteristiques_depuis_proprietes({})
        assert caracteristiques == CaracteristiquesPoteau(None, None, None, None, None, None)


# --------------------------------------------------------------------------- #
# Classement
# --------------------------------------------------------------------------- #


class TestClassifierSupport:
    """Tests de classifier_support (fonction pure)."""

    def test_support_conforme(self) -> None:
        assert classifier_support(_caracteristiques(), _catalogue_mock()) == []

    def test_casse_et_espaces_ignores(self) -> None:
        caracteristiques = _caracteristiques(matiere=" beton ", classe="d ")
        assert classifier_support(caracteristiques, _catalogue_mock()) == []

    def test_effort_en_dan_converti(self) -> None:
        caracteristiques = _caracteristiques(effort=400.0, effort_uom="daN")
        assert classifier_support(caracteristiques, _catalogue_mock()) == []

    def test_matiere_hors_catalogue(self) -> None:
        caracteristiques = _caracteristiques(matiere="Autre")
        assert classifier_support(caracteristiques, _catalogue_mock()) == [TYPE_MATIERE_HORS_CATALOGUE]

    def test_matiere_absente(self) -> None:
        caracteristiques = _caracteristiques(matiere=None)
        assert classifier_support(caracteristiques, _catalogue_mock()) == [TYPE_MATIERE_HORS_CATALOGUE]

    def test_matiere_invalide_court_circuite_les_autres_regles(self) -> None:
        """Sans listes de reference, les trois axes ne sont pas evaluables."""
        caracteristiques = _caracteristiques(matiere="Autre", classe="X", effort=99.0, hauteur=99.0)
        assert classifier_support(caracteristiques, _catalogue_mock()) == [TYPE_MATIERE_HORS_CATALOGUE]

    def test_classe_non_referencee(self) -> None:
        caracteristiques = _caracteristiques(classe="ZZZ")
        assert classifier_support(caracteristiques, _catalogue_mock()) == [TYPE_CLASSE_NON_REFERENCEE]

    def test_effort_non_reference(self) -> None:
        caracteristiques = _caracteristiques(effort=99.0)
        assert classifier_support(caracteristiques, _catalogue_mock()) == [TYPE_EFFORT_NON_REFERENCE]

    def test_hauteur_non_referencee(self) -> None:
        caracteristiques = _caracteristiques(hauteur=99.0)
        assert classifier_support(caracteristiques, _catalogue_mock()) == [TYPE_HAUTEUR_NON_REFERENCEE]

    def test_valeurs_absentes_signalees(self) -> None:
        """Une combinaison incomplete ne correspond a aucune entree du catalogue."""
        caracteristiques = _caracteristiques(classe=None, effort=None, hauteur=None)
        assert classifier_support(caracteristiques, _catalogue_mock()) == [
            TYPE_CLASSE_NON_REFERENCEE,
            TYPE_EFFORT_NON_REFERENCE,
            TYPE_HAUTEUR_NON_REFERENCEE,
        ]

    def test_les_trois_axes_cumulent(self) -> None:
        caracteristiques = _caracteristiques(classe="ZZZ", effort=99.0, hauteur=99.0)
        assert len(classifier_support(caracteristiques, _catalogue_mock())) == 3

    def test_valeur_valide_dans_une_autre_matiere(self) -> None:
        """« CFX » n'est reference qu'en bois : il est fautif sur un poteau beton."""
        caracteristiques = _caracteristiques(matiere="Beton", classe="CFX")
        assert classifier_support(caracteristiques, _catalogue_mock()) == [TYPE_CLASSE_NON_REFERENCEE]

    def test_unite_inconnue_rend_l_effort_non_reference(self) -> None:
        caracteristiques = _caracteristiques(effort_uom="tonnes")
        assert classifier_support(caracteristiques, _catalogue_mock()) == [TYPE_EFFORT_NON_REFERENCE]


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_support_conforme(self) -> None:
        assert detecter_anomalies([_feature_support()], _catalogue_mock()) == []

    def test_hors_perimetre_ignore(self) -> None:
        feature = _feature_support(statut="Functional", proprietes={"Classe_href": "ZZZ"})
        assert detecter_anomalies([feature], _catalogue_mock()) == []

    def test_anomalie_avec_valeurs_brutes(self) -> None:
        feature = _feature_support(proprietes={"Effort": 999.0})
        anomalies = detecter_anomalies([feature], _catalogue_mock())
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_EFFORT_NON_REFERENCE
        assert anomalies[0]["effort"] == 999.0
        assert anomalies[0]["effort_uom"] == "kN"
        assert anomalies[0]["geometrie"]["type"] == "Point"

    def test_plusieurs_anomalies_pour_un_support(self) -> None:
        feature = _feature_support(proprietes={"Classe_href": "ZZZ", "HauteurPoteau": 99.0})
        anomalies = detecter_anomalies([feature], _catalogue_mock())
        assert [a["type_anomalie"] for a in anomalies] == [
            TYPE_CLASSE_NON_REFERENCEE,
            TYPE_HAUTEUR_NON_REFERENCEE,
        ]
        assert {a["id_support"] for a in anomalies} == {"s1"}

    def test_plusieurs_supports(self) -> None:
        features = [_feature_support("s1"), _feature_support("s2", proprietes={"Classe_href": "ZZZ"})]
        anomalies = detecter_anomalies(features, _catalogue_mock())
        assert {a["id_support"] for a in anomalies} == {"s2"}


class TestComptages:
    """Tests des comptages du rapport."""

    def test_supports_a_controler(self) -> None:
        features = [_feature_support("s1"), _feature_support("s2", statut="Projected")]
        assert compter_supports_a_controler(features) == 1

    def test_supports_a_controler_liste_vide(self) -> None:
        assert compter_supports_a_controler([]) == 0

    def test_supports_non_conformes_dedoublonnes(self) -> None:
        anomalies = [
            {"id_support": "s1", "type_anomalie": TYPE_CLASSE_NON_REFERENCEE},
            {"id_support": "s1", "type_anomalie": TYPE_EFFORT_NON_REFERENCE},
            {"id_support": "s2", "type_anomalie": TYPE_EFFORT_NON_REFERENCE},
        ]
        assert compter_supports_non_conformes(anomalies) == 2

    def test_supports_non_conformes_liste_vide(self) -> None:
        assert compter_supports_non_conformes([]) == 0


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_EFFORT_NON_REFERENCE,
            "id_support": "s1",
            "matiere": "Beton",
            "classe": "D",
            "effort": 400.0,
            "effort_uom": "kN",
            "hauteur": 12.0,
            "hauteur_uom": "m",
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }

    def test_socle_commun(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["code_controle"] == "E603"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_entite"] == "s1"
        assert props["type_anomalie"] == TYPE_EFFORT_NON_REFERENCE
        assert props["description"]

    def test_proprietes_metier(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["fichier_source"] == FICHIER_SUPPORT
        assert props["matiere"] == "Beton"
        assert props["classe"] == "D"
        assert props["effort"] == 400.0
        assert props["hauteur"] == 12.0

    def test_unites_exposees(self) -> None:
        """C'est souvent l'unite qui est en cause : elle doit figurer a l'ecart."""
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["effort_uom"] == "kN"
        assert props["hauteur_uom"] == "m"

    def test_geometrie_conservee(self) -> None:
        geom = construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"]
        assert geom == {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}

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
        from controle_e603 import executer_controle_cli

        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    @patch("controle_e603.charger_catalogue")
    def test_catalogue_indisponible_erreur(self, mock_cat: Any, tmp_path: Any) -> None:
        from controle_e603 import executer_controle_cli

        mock_cat.return_value = (None, "Catalogue introuvable : x")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "Catalogue" in resultat["erreur"]

    @patch("controle_e603.charger_catalogue")
    def test_fichier_support_absent_non_bloquant(self, mock_cat: Any, tmp_path: Any) -> None:
        from controle_e603 import executer_controle_cli

        mock_cat.return_value = (_catalogue_mock(), None)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_support_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    @patch("controle_e603.charger_catalogue")
    def test_nominal_conforme(self, mock_cat: Any, tmp_path: Any) -> None:
        from controle_e603 import executer_controle_cli

        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection(str(tmp_path / FICHIER_SUPPORT), [_feature_support()])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_supports_controles"] == 1
        assert resultat["priorite"] == "majeur"
        assert resultat["matieres_catalogue"] == ["beton", "bois"]

    @patch("controle_e603.charger_catalogue")
    def test_nominal_non_conforme(self, mock_cat: Any, tmp_path: Any) -> None:
        from controle_e603 import executer_controle_cli

        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection(str(tmp_path / FICHIER_SUPPORT), [_feature_support(proprietes={"Classe_href": "ZZZ"})])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_CLASSE_NON_REFERENCEE: 1}
        assert resultat["nombre_supports_non_conformes"] == 1

    @patch("controle_e603.charger_catalogue")
    def test_fichier_ecarts_cree(self, mock_cat: Any, tmp_path: Any) -> None:
        from controle_e603 import executer_controle_cli

        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection(str(tmp_path / FICHIER_SUPPORT), [_feature_support(proprietes={"Classe_href": "ZZZ"})])
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    @patch("controle_e603.charger_catalogue")
    def test_aucun_fichier_sans_anomalie(self, mock_cat: Any, tmp_path: Any) -> None:
        from controle_e603 import executer_controle_cli

        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection(str(tmp_path / FICHIER_SUPPORT), [_feature_support()])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    @patch("controle_e603.charger_catalogue")
    def test_crs_propage(self, mock_cat: Any, tmp_path: Any) -> None:
        from controle_e603 import executer_controle_cli

        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection_avec_crs(
            str(tmp_path / FICHIER_SUPPORT),
            [_feature_support(proprietes={"Classe_href": "ZZZ"})],
            "EPSG:2154",
        )
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert "2154" in ecarts["crs"]["properties"]["name"]

    @patch("controle_e603.charger_catalogue")
    def test_rapport_champs_obligatoires(self, mock_cat: Any, tmp_path: Any) -> None:
        from controle_e603 import executer_controle_cli

        mock_cat.return_value = (_catalogue_mock(), None)
        ecrire_collection(str(tmp_path / FICHIER_SUPPORT), [_feature_support()])
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "anomalies_par_type",
            "nombre_supports_analyses",
            "nombre_supports_controles",
            "nombre_supports_non_conformes",
            "matieres_catalogue",
            "fichier_support_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Integration sur le vrai catalogue du depot
# --------------------------------------------------------------------------- #


class TestIntegrationCatalogueReel:
    """Tests utilisant le catalogue reel versionne dans le depot."""

    def _executer(self, tmp_path: Any, proprietes: dict[str, Any]) -> dict[str, Any]:
        from controle_e603 import executer_controle_cli

        ecrire_collection(str(tmp_path / FICHIER_SUPPORT), [_feature_support(proprietes=proprietes)])
        return executer_controle_cli(str(tmp_path))

    def test_poteau_beton_conforme(self, tmp_path: Any) -> None:
        resultat = self._executer(
            tmp_path,
            {"Matiere_href": "Beton", "Classe_href": "D", "Effort": 4.0, "HauteurPoteau": 12.0},
        )
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_effort_en_dan_reconnu(self, tmp_path: Any) -> None:
        """400 daN valent 4,00 kN : la conversion evite un faux positif."""
        resultat = self._executer(
            tmp_path,
            {
                "Matiere_href": "Beton",
                "Classe_href": "D",
                "Effort": 400.0,
                "Effort_uom": "daN",
                "HauteurPoteau": 12.0,
            },
        )
        assert resultat["nombre_anomalies"] == 0

    def test_effort_dan_declare_en_kn_signale(self, tmp_path: Any) -> None:
        """Cas reel du jeu Echantillon : 400 declares en kN, hors catalogue.

        Le catalogue plafonne a 160 kN. La valeur n'est interpretable qu'en daN,
        mais l'unite declaree fait foi : l'ecart est reel, il porte sur la donnee.
        """
        resultat = self._executer(
            tmp_path,
            {
                "Matiere_href": "Beton",
                "Classe_href": "D",
                "Effort": 400.0,
                "Effort_uom": "kN",
                "HauteurPoteau": 12.0,
            },
        )
        assert resultat["anomalies_par_type"] == {TYPE_EFFORT_NON_REFERENCE: 1}

    def test_classe_metal_sur_poteau_beton_signalee(self, tmp_path: Any) -> None:
        """Le filtrage par matiere a un effet sur le catalogue reel."""
        resultat = self._executer(
            tmp_path,
            {"Matiere_href": "Beton", "Classe_href": "M", "Effort": 4.0, "HauteurPoteau": 12.0},
        )
        assert resultat["anomalies_par_type"] == {TYPE_CLASSE_NON_REFERENCEE: 1}

    def test_matiere_autre_signalee(self, tmp_path: Any) -> None:
        """Cas reel du jeu Echantillon2 : « Autre » n'est pas au catalogue."""
        resultat = self._executer(tmp_path, {"Matiere_href": "Autre"})
        assert resultat["anomalies_par_type"] == {TYPE_MATIERE_HORS_CATALOGUE: 1}


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Les caracteristiques sont controlees identiquement en V1.0 et V1.1."""

    @patch("controle_e603.charger_catalogue")
    def test_v11_champs_extra_sans_effet(self, mock_cat: Any, tmp_path: Any) -> None:
        from controle_e603 import executer_controle_cli

        mock_cat.return_value = (_catalogue_mock(), None)
        feature = _feature_support(proprietes={"Commentaire": "note", "PrecisionXY": "A"})
        ecrire_collection(str(tmp_path / FICHIER_SUPPORT), [feature])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
