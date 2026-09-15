"""
Tests du controle E-6114 : coffret de telecommunication lie a un noeud electrique.

Couvre :
  - les predicats partages de separation des reseaux
  - le chargement et le double filtre de perimetre des coffrets (Statut, TypeCoffret)
  - la resolution du TypeCoffret sous ses deux formes (code seul, reference fragmentee)
  - la detection par couche, et l'exclusion des couches hors perimetre
  - les comptages du rapport
  - la construction du GeoJSON d'ecarts, geometrie de repli comprise
  - l'execution CLI, dont le parcours reel du repertoire
"""

import json
from typing import Any

from recostar.controle.conteneur.e6114 import (
    COUCHES_CIBLES,
    FICHIER_SORTIE,
    STATUTS_CONTROLES,
    TYPE_NOEUD_ELECTRIQUE,
    charger_coffrets_telecom,
    compter_coffrets_non_conformes,
    compter_liens_couche,
    construire_geojson_ecarts,
    detecter_anomalies_couche,
    executer_controle_cli,
)
from recostar.controle.conteneur.tests.utils_tests import ecrire_collection, ecrire_collection_avec_crs
from recostar.controle.fonctions_communes.geojson import PRIORITE_FORTE
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CONTENEUR_HREF,
    CHAMP_STATUT,
    CHAMP_TYPE_COFFRET_HREF,
    EXTENSION_COUCHE,
    FICHIER_COFFRET,
)
from recostar.controle.fonctions_communes.separation_reseaux import est_coffret_telecom

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

COUCHE_JONCTION: str = "RPD_Jonction_Reco"
COUCHE_ELECTRIQUE: str = "RPD_JeuBarres_Reco"
GEOM_NOEUD: dict[str, Any] = {"type": "Point", "coordinates": [1.0, 2.0]}
GEOM_COFFRET: dict[str, Any] = {"type": "Point", "coordinates": [10.0, 20.0]}


def _feature(identifiant: str, proprietes: dict[str, Any], geometrie: Any = GEOM_NOEUD) -> dict[str, Any]:
    props: dict[str, Any] = {"id": identifiant}
    props.update(proprietes)
    return {"type": "Feature", "properties": props, "geometry": geometrie}


def _coffret(
    identifiant: str = "k1",
    type_coffret: Any = "Telecom",
    statut: str = "UnderCommissionning",
) -> dict[str, Any]:
    proprietes: dict[str, Any] = {CHAMP_STATUT: statut}
    if type_coffret is not None:
        proprietes[CHAMP_TYPE_COFFRET_HREF] = type_coffret
    return _feature(identifiant, proprietes, GEOM_COFFRET)


def _noeud(
    identifiant: str = "n1",
    conteneur_href: Any = "k1",
    proprietes: dict[str, Any] | None = None,
    geometrie: Any = GEOM_NOEUD,
) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if conteneur_href is not None:
        props[CHAMP_CONTENEUR_HREF] = conteneur_href
    props.update(proprietes or {})
    return _feature(identifiant, props, geometrie)


# Index minimal : un coffret de telecommunication du perimetre
COFFRETS: dict[str, dict[str, Any] | None] = {"k1": GEOM_COFFRET}


def _types(anomalies: list[dict[str, Any]]) -> list[str]:
    return [anomalie["type_anomalie"] for anomalie in anomalies]


def _ecrire_jeu(
    tmp_path: Any,
    noeuds: list[dict[str, Any]],
    couche: str = COUCHE_ELECTRIQUE,
    coffrets: list[dict[str, Any]] | None = None,
) -> None:
    """Ecrit un jeu complet : une couche de noeuds, la couche coffret."""
    ecrire_collection(str(tmp_path / f"{couche}{EXTENSION_COUCHE}"), noeuds)
    ecrire_collection(
        str(tmp_path / FICHIER_COFFRET),
        coffrets if coffrets is not None else [_coffret()],
    )


# --------------------------------------------------------------------------- #
# Predicats partages
# --------------------------------------------------------------------------- #


class TestPredicatsSeparation:
    """Predicats de `fonctions_communes.separation_reseaux`."""

    def test_coffret_telecom(self) -> None:
        assert est_coffret_telecom({CHAMP_TYPE_COFFRET_HREF: "Telecom"}) is True

    def test_coffret_telecom_reference_fragmentee(self) -> None:
        """Le convertisseur restitue l'attribut brut : « ...#Telecom »."""
        assert est_coffret_telecom({CHAMP_TYPE_COFFRET_HREF: "codelist.xml#Telecom"}) is True

    def test_coffret_d_un_autre_type(self) -> None:
        assert est_coffret_telecom({CHAMP_TYPE_COFFRET_HREF: "RMBT300"}) is False

    def test_coffret_sans_type(self) -> None:
        assert est_coffret_telecom({}) is False


# --------------------------------------------------------------------------- #
# Chargement et perimetre
# --------------------------------------------------------------------------- #


class TestChargerCoffretsTelecom:
    """Double filtre : Statut en service et TypeCoffret Telecom."""

    def test_coffret_telecom_indexe(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_coffret()])
        index, _, absent = charger_coffrets_telecom(str(tmp_path))
        assert absent is False
        assert index == {"k1": GEOM_COFFRET}

    def test_coffret_d_un_autre_type_ecarte(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_coffret(type_coffret="RMBT300")])
        assert charger_coffrets_telecom(str(tmp_path))[0] == {}

    def test_coffret_sans_type_ecarte(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_coffret(type_coffret=None)])
        assert charger_coffrets_telecom(str(tmp_path))[0] == {}

    def test_coffret_hors_statut_ecarte(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [_coffret(statut="Abandoned")])
        assert charger_coffrets_telecom(str(tmp_path))[0] == {}

    def test_statuts_controles(self) -> None:
        assert STATUTS_CONTROLES == frozenset({"UnderCommissionning", "Functional"})

    def test_fichier_absent_signale(self, tmp_path: Any) -> None:
        index, _, absent = charger_coffrets_telecom(str(tmp_path))
        assert absent is True
        assert index == {}


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesCouche:
    """Tests de detecter_anomalies_couche."""

    def test_noeud_electrique_signale(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_ELECTRIQUE, [_noeud()], COFFRETS)
        assert _types(anomalies) == [TYPE_NOEUD_ELECTRIQUE]
        assert anomalies[0]["id_coffret"] == "k1"
        assert anomalies[0]["id_noeud"] == "n1"
        assert anomalies[0]["couche_noeud"] == COUCHE_ELECTRIQUE

    def test_couche_jonction_hors_perimetre(self) -> None:
        """Une jonction dans un coffret releve d'E-6108, pas de ce controle."""
        assert detecter_anomalies_couche(COUCHE_JONCTION, [_noeud("j1")], COFFRETS) == []

    def test_couche_inconnue_hors_perimetre(self) -> None:
        assert detecter_anomalies_couche("RPD_NouvelleEntite_Reco", [_noeud()], COFFRETS) == []

    def test_les_sept_couches_controlees(self) -> None:
        assert set(COUCHES_CIBLES) == {
            "RPD_CoupeCircuitAFusibles_Reco",
            "RPD_JeuBarres_Reco",
            "RPD_ModuleRaccordement_Reco",
            "RPD_OuvrageCollectifBranchement_Reco",
            "RPD_PointDeComptage_Reco",
            "RPD_SupportModules_Reco",
            "RPD_Terre_Reco",
        }

    def test_toutes_les_couches_cibles_signalees(self) -> None:
        """Les sept appartiennent au reseau electrique, sans exception d'entite."""
        for couche in COUCHES_CIBLES:
            assert _types(detecter_anomalies_couche(couche, [_noeud()], COFFRETS)) == [TYPE_NOEUD_ELECTRIQUE]

    def test_perimetres_complementaires_avec_e0604(self) -> None:
        """E-6108 signale les couches hors liste, E-6114 celles de la liste.

        Les deux perimetres sont exactement complementaires : aucun lien ne peut
        relever des deux controles, et aucune couche admise dans un coffret
        n'echappe aux deux.
        """
        from recostar.controle.conteneur.e6108 import COUCHES_NOEUDS_AUTORISEES

        assert set(COUCHES_CIBLES) == set(COUCHES_NOEUDS_AUTORISEES)

    def test_reference_vers_un_autre_conteneur_ignoree(self) -> None:
        """Un conteneur hors perimetre ne releve pas de cette regle."""
        assert detecter_anomalies_couche(COUCHE_ELECTRIQUE, [_noeud(conteneur_href="k9")], COFFRETS) == []

    def test_noeud_sans_conteneur_ignore(self) -> None:
        assert detecter_anomalies_couche(COUCHE_ELECTRIQUE, [_noeud(conteneur_href=None)], COFFRETS) == []

    def test_une_anomalie_par_lien_fautif(self) -> None:
        noeuds = [_noeud("n1"), _noeud("n2"), _noeud("n3")]
        assert len(detecter_anomalies_couche(COUCHE_ELECTRIQUE, noeuds, COFFRETS)) == 3

    def test_geometrie_de_repli_sur_le_coffret(self) -> None:
        """Un noeud sans geometrie propre reste localisable par son conteneur."""
        anomalies = detecter_anomalies_couche(COUCHE_ELECTRIQUE, [_noeud(geometrie=None)], COFFRETS)
        assert anomalies[0]["geometrie"] == GEOM_COFFRET

    def test_couche_vide(self) -> None:
        assert detecter_anomalies_couche(COUCHE_ELECTRIQUE, [], COFFRETS) == []


class TestComptages:
    """Tests des comptages du rapport."""

    def test_liens_controles_comptes(self) -> None:
        assert compter_liens_couche([_noeud("n1"), _noeud("n2")], COFFRETS) == 2

    def test_liens_hors_perimetre_non_comptes(self) -> None:
        assert compter_liens_couche([_noeud(conteneur_href="k9")], COFFRETS) == 0

    def test_coffrets_non_conformes_dedoublonnes(self) -> None:
        anomalies = [{"id_coffret": "k1"}, {"id_coffret": "k1"}, {"id_coffret": "k2"}]
        assert compter_coffrets_non_conformes(anomalies) == 2

    def test_liste_vide(self) -> None:
        assert compter_coffrets_non_conformes([]) == 0


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    @staticmethod
    def _anomalie() -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_NOEUD_ELECTRIQUE,
            "id_coffret": "k1",
            "id_noeud": "n1",
            "couche_noeud": COUCHE_ELECTRIQUE,
            "geometrie": GEOM_NOEUD,
        }

    def test_proprietes_du_socle(self) -> None:
        proprietes = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6114"
        assert proprietes["priorite"] == PRIORITE_FORTE
        assert proprietes["couche_noeud"] == COUCHE_ELECTRIQUE

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

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_repertoire_vide_non_bloquant(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["fichier_coffret_absent"] is True

    def test_noeud_electrique_signale(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud()])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_NOEUD_ELECTRIQUE: 1}
        assert resultat["nombre_coffrets_controles"] == 1
        assert resultat["nombre_coffrets_non_conformes"] == 1
        assert resultat["nombre_liens_controles"] == 1

    def test_jonction_ignoree(self, tmp_path: Any) -> None:
        """Le coffret Telecom heberge une jonction : E-6108 s'en charge, pas E-6114."""
        _ecrire_jeu(tmp_path, [_noeud("j1")], couche=COUCHE_JONCTION)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_liens_controles"] == 0

    def test_coffret_non_telecom_hors_perimetre(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud()], coffrets=[_coffret(type_coffret="RMBT300")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_coffrets_controles"] == 0

    def test_fichier_ecarts_ecrit(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud()])
        chemin = executer_controle_cli(str(tmp_path))["sortie"]
        assert chemin is not None
        assert chemin.endswith(FICHIER_SORTIE)
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6114"
        assert proprietes["id_coffret"] == "k1"

    def test_aucun_fichier_si_conforme(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(conteneur_href="k9")])
        assert executer_controle_cli(str(tmp_path))["sortie"] is None

    def test_couches_absentes_remontees(self, tmp_path: Any) -> None:
        """Un jeu ne contient pas necessairement les sept types de noeuds."""
        _ecrire_jeu(tmp_path, [_noeud()])
        resultat = executer_controle_cli(str(tmp_path))
        assert set(resultat["couches_absentes"]) == set(COUCHES_CIBLES) - {COUCHE_ELECTRIQUE}

    def test_crs_propage_depuis_le_coffret(self, tmp_path: Any) -> None:
        """Le crs vient du fichier coffret : ce sont les entites controlees."""
        ecrire_collection(str(tmp_path / f"{COUCHE_ELECTRIQUE}{EXTENSION_COUCHE}"), [_noeud()])
        ecrire_collection_avec_crs(str(tmp_path / FICHIER_COFFRET), [_coffret()], "EPSG:2154")
        chemin = executer_controle_cli(str(tmp_path))["sortie"]
        assert chemin is not None
        with open(chemin, encoding="utf-8") as flux:
            crs = json.load(flux)["crs"]
        assert crs["properties"]["name"] == "urn:ogc:def:crs:EPSG::2154"

    def test_execution_idempotente(self, tmp_path: Any) -> None:
        """Une seconde execution ne doit pas analyser ses propres ecarts."""
        _ecrire_jeu(tmp_path, [_noeud()])
        executer_controle_cli(str(tmp_path))
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 1
