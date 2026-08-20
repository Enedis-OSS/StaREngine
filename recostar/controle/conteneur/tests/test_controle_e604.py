"""
Tests du controle E604 : types de noeuds autorises a se rattacher a un coffret.

Couvre :
  - la derivation du nom de couche depuis le nom de fichier
  - le chargement et le filtre de perimetre des coffrets (Statut)
  - la liste des couches autorisees
  - la detection par couche et sur l'ensemble des couches
  - les comptages du rapport
  - la construction du GeoJSON d'ecarts, geometrie de repli comprise
  - l'execution CLI, dont le parcours reel du repertoire
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from controle_e604 import (
    CHAMP_CONTENEUR_HREF,
    CHAMP_STATUT,
    COUCHES_NOEUDS_AUTORISEES,
    FICHIER_COFFRET,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    STATUTS_CONTROLES,
    TYPE_NOEUD_NON_AUTORISE,
    charger_coffrets_a_controler,
    compter_coffrets_non_conformes,
    compter_liens_couche,
    construire_geojson_ecarts,
    couche_autorisee,
    detecter_anomalies,
    detecter_anomalies_couche,
    executer_controle_cli,
    nom_couche,
    parcourir_couches,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

COUCHE_AUTORISEE: str = "RPD_Terre_Reco"
COUCHE_INTERDITE: str = "RPD_Jonction_Reco"


def _feature_coffret(identifiant: str = "c1", statut: str = "UnderCommissionning") -> dict[str, Any]:
    """Feature GeoJSON Point representant un coffret."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, CHAMP_STATUT: statut},
        "geometry": {"type": "Point", "coordinates": [10.0, 20.0, 30.0]},
    }


def _feature_noeud(
    identifiant: str = "n1",
    conteneur_href: Any = "c1",
    geometrie: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Feature GeoJSON d'un noeud referencant un conteneur."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, CHAMP_CONTENEUR_HREF: conteneur_href},
        "geometry": geometrie if geometrie is not None else {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
    }


def _coffrets(*identifiants: str) -> dict[str, dict[str, Any] | None]:
    """Index {id_coffret: geometrie} tel que produit par le chargement."""
    return {i: {"type": "Point", "coordinates": [10.0, 20.0, 30.0]} for i in identifiants}


# --------------------------------------------------------------------------- #
# Nom de couche
# --------------------------------------------------------------------------- #


class TestNomCouche:
    """Tests de nom_couche."""

    def test_extension_retiree(self) -> None:
        assert nom_couche("RPD_Terre_Reco.geojson") == "RPD_Terre_Reco"

    def test_extension_majuscules(self) -> None:
        assert nom_couche("RPD_Terre_Reco.GEOJSON") == "RPD_Terre_Reco"

    def test_sans_extension_inchange(self) -> None:
        assert nom_couche("RPD_Terre_Reco") == "RPD_Terre_Reco"


class TestCoucheAutorisee:
    """Tests de couche_autorisee."""

    def test_les_sept_couches_declarees(self) -> None:
        assert COUCHES_NOEUDS_AUTORISEES == frozenset(
            {
                "RPD_CoupeCircuitAFusibles_Reco",
                "RPD_JeuBarres_Reco",
                "RPD_ModuleRaccordement_Reco",
                "RPD_OuvrageCollectifBranchement_Reco",
                "RPD_PointDeComptage_Reco",
                "RPD_SupportModules_Reco",
                "RPD_Terre_Reco",
            }
        )

    def test_couche_autorisee(self) -> None:
        assert couche_autorisee("RPD_SupportModules_Reco") is True

    def test_couche_interdite(self) -> None:
        assert couche_autorisee(COUCHE_INTERDITE) is False

    def test_couche_inconnue_interdite(self) -> None:
        """Toute couche hors liste est interdite, y compris une couche future."""
        assert couche_autorisee("RPD_NouvelleEntite_Reco") is False

    def test_coffret_lui_meme_interdit(self) -> None:
        assert couche_autorisee("RPD_Coffret_Reco") is False


# --------------------------------------------------------------------------- #
# Chargement des coffrets
# --------------------------------------------------------------------------- #


class TestChargerCoffretsAControler:
    """Tests de charger_coffrets_a_controler."""

    def test_fichier_absent(self, tmp_path: Any) -> None:
        index, crs, absent = charger_coffrets_a_controler(str(tmp_path))
        assert (index, crs, absent) == ({}, None, True)

    def test_les_deux_statuts_retenus(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_COFFRET),
            [_feature_coffret("c1", "UnderCommissionning"), _feature_coffret("c2", "Functional")],
        )
        index, _, absent = charger_coffrets_a_controler(str(tmp_path))
        assert set(index) == {"c1", "c2"}
        assert absent is False

    def test_autre_statut_ecarte(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_COFFRET),
            [_feature_coffret("c1", "Decommissioned"), _feature_coffret("c2", "Projected")],
        )
        index, _, _ = charger_coffrets_a_controler(str(tmp_path))
        assert index == {}

    def test_statuts_declares(self) -> None:
        assert STATUTS_CONTROLES == frozenset({"UnderCommissionning", "Functional"})

    def test_coffret_sans_identifiant_ecarte(self, tmp_path: Any) -> None:
        feature = _feature_coffret("c1")
        feature["properties"].pop("id")
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [feature])
        index, _, _ = charger_coffrets_a_controler(str(tmp_path))
        assert index == {}

    def test_geometrie_conservee(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_feature_coffret("c1")])
        index, _, _ = charger_coffrets_a_controler(str(tmp_path))
        assert index["c1"] == {"type": "Point", "coordinates": [10.0, 20.0, 30.0]}

    def test_crs_remonte(self, tmp_path: Any) -> None:
        ecrire_collection_avec_crs(str(tmp_path / FICHIER_COFFRET), [_feature_coffret("c1")], "EPSG:2154")
        _, crs, _ = charger_coffrets_a_controler(str(tmp_path))
        assert crs is not None and "2154" in crs["properties"]["name"]


# --------------------------------------------------------------------------- #
# Detection par couche
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesCouche:
    """Tests de detecter_anomalies_couche."""

    def test_couche_autorisee_jamais_signalee(self) -> None:
        assert detecter_anomalies_couche(COUCHE_AUTORISEE, [_feature_noeud()], _coffrets("c1")) == []

    def test_couche_interdite_visant_un_coffret(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_INTERDITE, [_feature_noeud()], _coffrets("c1"))
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_NOEUD_NON_AUTORISE
        assert anomalies[0]["id_coffret"] == "c1"
        assert anomalies[0]["id_noeud"] == "n1"
        assert anomalies[0]["couche_noeud"] == COUCHE_INTERDITE

    def test_couche_interdite_visant_un_autre_conteneur(self) -> None:
        """Un conteneur_href designant un support ne releve pas de cette regle."""
        noeud = _feature_noeud(conteneur_href="support_1")
        assert detecter_anomalies_couche(COUCHE_INTERDITE, [noeud], _coffrets("c1")) == []

    def test_coffret_hors_perimetre_ignore(self) -> None:
        """Un coffret d'un autre statut n'est pas dans l'index : rien n'est signale."""
        assert detecter_anomalies_couche(COUCHE_INTERDITE, [_feature_noeud()], {}) == []

    def test_noeud_sans_reference_ignore(self) -> None:
        noeud = _feature_noeud(conteneur_href=None)
        assert detecter_anomalies_couche(COUCHE_INTERDITE, [noeud], _coffrets("c1")) == []

    def test_reference_vide_ignoree(self) -> None:
        noeud = _feature_noeud(conteneur_href="   ")
        assert detecter_anomalies_couche(COUCHE_INTERDITE, [noeud], _coffrets("c1")) == []

    def test_reference_avec_espaces_resolue(self) -> None:
        noeud = _feature_noeud(conteneur_href=" c1 ")
        assert len(detecter_anomalies_couche(COUCHE_INTERDITE, [noeud], _coffrets("c1"))) == 1

    def test_geometrie_du_noeud_retenue(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_INTERDITE, [_feature_noeud()], _coffrets("c1"))
        assert anomalies[0]["geometrie"] == {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}

    def test_geometrie_du_coffret_en_repli(self) -> None:
        """Certains noeuds n'ont pas de geometrie propre (ModuleRaccordement)."""
        noeud = _feature_noeud(geometrie=None)
        noeud["geometry"] = None
        anomalies = detecter_anomalies_couche(COUCHE_INTERDITE, [noeud], _coffrets("c1"))
        assert anomalies[0]["geometrie"] == {"type": "Point", "coordinates": [10.0, 20.0, 30.0]}

    def test_une_anomalie_par_lien(self) -> None:
        noeuds = [_feature_noeud("n1"), _feature_noeud("n2")]
        anomalies = detecter_anomalies_couche(COUCHE_INTERDITE, noeuds, _coffrets("c1"))
        assert [a["id_noeud"] for a in anomalies] == ["n1", "n2"]

    def test_couche_vide(self) -> None:
        assert detecter_anomalies_couche(COUCHE_INTERDITE, [], _coffrets("c1")) == []


class TestDetecterAnomalies:
    """Tests de detecter_anomalies sur l'ensemble des couches."""

    def test_agregation_des_couches(self) -> None:
        couches = [
            (COUCHE_AUTORISEE, [_feature_noeud("n1")]),
            (COUCHE_INTERDITE, [_feature_noeud("n2")]),
            ("RPD_PosteElectrique_Reco", [_feature_noeud("n3")]),
        ]
        anomalies = detecter_anomalies(couches, _coffrets("c1"))
        assert {a["id_noeud"] for a in anomalies} == {"n2", "n3"}

    def test_aucune_couche(self) -> None:
        assert detecter_anomalies([], _coffrets("c1")) == []

    def test_generateur_accepte(self) -> None:
        """La detection consomme un iterable : le CLI lui passe un generateur."""
        couches = ((COUCHE_INTERDITE, [_feature_noeud()]) for _ in range(1))
        assert len(detecter_anomalies(couches, _coffrets("c1"))) == 1


class TestComptages:
    """Tests des comptages du rapport."""

    def test_liens_couche_autorisee_comptes(self) -> None:
        """Un lien conforme reste un lien controle."""
        assert compter_liens_couche([_feature_noeud()], _coffrets("c1")) == 1

    def test_liens_hors_coffret_non_comptes(self) -> None:
        noeud = _feature_noeud(conteneur_href="support_1")
        assert compter_liens_couche([noeud], _coffrets("c1")) == 0

    def test_liens_sans_reference_non_comptes(self) -> None:
        assert compter_liens_couche([_feature_noeud(conteneur_href=None)], _coffrets("c1")) == 0

    def test_coffrets_non_conformes_dedoublonnes(self) -> None:
        anomalies = [{"id_coffret": "c1"}, {"id_coffret": "c1"}, {"id_coffret": "c2"}]
        assert compter_coffrets_non_conformes(anomalies) == 2

    def test_coffrets_non_conformes_liste_vide(self) -> None:
        assert compter_coffrets_non_conformes([]) == 0


# --------------------------------------------------------------------------- #
# Parcours des couches
# --------------------------------------------------------------------------- #


class TestParcourirCouches:
    """Tests de parcourir_couches."""

    def test_toutes_les_couches_parcourues(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_feature_coffret()])
        ecrire_collection(str(tmp_path / f"{COUCHE_INTERDITE}.geojson"), [_feature_noeud()])
        couches = dict(parcourir_couches(str(tmp_path)))
        assert set(couches) == {"RPD_Coffret_Reco", COUCHE_INTERDITE}

    def test_fichiers_ecarts_exclus(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_feature_coffret()])
        ecrire_collection(str(tmp_path / "ecarts_quelque_chose.geojson"), [])
        assert set(dict(parcourir_couches(str(tmp_path)))) == {"RPD_Coffret_Reco"}

    def test_repertoire_sans_geojson(self, tmp_path: Any) -> None:
        assert list(parcourir_couches(str(tmp_path))) == []


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_NOEUD_NON_AUTORISE,
            "id_coffret": "c1",
            "id_noeud": "n1",
            "couche_noeud": COUCHE_INTERDITE,
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }

    def test_socle_commun(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["code_controle"] == "E604"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_entite"] == "c1"
        assert props["type_anomalie"] == TYPE_NOEUD_NON_AUTORISE
        assert props["description"]

    def test_proprietes_metier(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["fichier_source"] == FICHIER_COFFRET
        assert props["id_coffret"] == "c1"
        assert props["id_noeud"] == "n1"
        assert props["couche_noeud"] == COUCHE_INTERDITE

    def test_geometrie_conservee(self) -> None:
        geom = construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"]
        assert geom == {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def _jeu(self, tmp_path: Any, couche: str, statut: str = "UnderCommissionning") -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_feature_coffret("c1", statut)])
        ecrire_collection(str(tmp_path / f"{couche}.geojson"), [_feature_noeud("n1", "c1")])

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichier_coffret_absent_non_bloquant(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_coffret_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_nominal_conforme(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, COUCHE_AUTORISEE)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_coffrets_controles"] == 1
        assert resultat["nombre_liens_controles"] == 1
        assert resultat["priorite"] == "mineur"

    def test_nominal_non_conforme(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, COUCHE_INTERDITE)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_coffrets_non_conformes"] == 1

    def test_statut_functional_controle(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, COUCHE_INTERDITE, statut="Functional")
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 1

    def test_coffret_hors_statut_ignore(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, COUCHE_INTERDITE, statut="Decommissioned")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_coffrets_controles"] == 0
        assert resultat["nombre_anomalies"] == 0

    def test_coffret_sans_noeud_conforme(self, tmp_path: Any) -> None:
        """La regle porte sur le type du noeud, pas sur l'existence du lien."""
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_feature_coffret("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_coffrets_controles"] == 1
        assert resultat["nombre_anomalies"] == 0

    def test_couches_comptees(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, COUCHE_INTERDITE)
        assert executer_controle_cli(str(tmp_path))["nombre_couches_analysees"] == 2

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, COUCHE_INTERDITE)
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, COUCHE_AUTORISEE)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_ecarts_exclus_du_parcours(self, tmp_path: Any) -> None:
        """Une seconde execution ne doit pas analyser le fichier d'ecarts produit."""
        self._jeu(tmp_path, COUCHE_INTERDITE)
        premier = executer_controle_cli(str(tmp_path))
        second = executer_controle_cli(str(tmp_path))
        assert premier["nombre_couches_analysees"] == second["nombre_couches_analysees"]
        assert premier["nombre_anomalies"] == second["nombre_anomalies"]

    def test_crs_propage(self, tmp_path: Any) -> None:
        ecrire_collection_avec_crs(str(tmp_path / FICHIER_COFFRET), [_feature_coffret("c1")], "EPSG:2154")
        ecrire_collection(str(tmp_path / f"{COUCHE_INTERDITE}.geojson"), [_feature_noeud("n1", "c1")])
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert "2154" in ecarts["crs"]["properties"]["name"]

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, COUCHE_AUTORISEE)
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "nombre_coffrets_controles",
            "nombre_coffrets_non_conformes",
            "nombre_couches_analysees",
            "nombre_liens_controles",
            "fichier_coffret_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


class TestCouchesReellesDesJeux:
    """Les couches qui portent conteneur_href sans etre autorisees.

    RPD_Jonction_Reco et RPD_PosteElectrique_Reco en portent dans les jeux de
    reference, mais visent un support ou un batiment technique. Ces tests
    verrouillent le fait qu'elles ne sont signalees que si elles visent un
    coffret — c'est ce qui evite une avalanche de faux positifs.
    """

    def test_jonction_vers_support_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_feature_coffret("c1")])
        ecrire_collection(
            str(tmp_path / "RPD_Jonction_Reco.geojson"),
            [_feature_noeud("j1", "support_1")],
        )
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_poste_electrique_vers_coffret_signale(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_feature_coffret("c1")])
        ecrire_collection(
            str(tmp_path / "RPD_PosteElectrique_Reco.geojson"),
            [_feature_noeud("p1", "c1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_coffrets_non_conformes"] == 1


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Le rattachement est controle identiquement en V1.0 et V1.1."""

    def test_v11_champs_extra_sans_effet(self, tmp_path: Any) -> None:
        coffret = _feature_coffret("c1")
        coffret["properties"]["Commentaire"] = "note"
        noeud = _feature_noeud("n1", "c1")
        noeud["properties"]["Commentaire"] = "note"
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [coffret])
        ecrire_collection(str(tmp_path / f"{COUCHE_AUTORISEE}.geojson"), [noeud])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
