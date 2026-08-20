"""
Tests du controle E609 : rattachement des noeuds du reseau a un cable existant.

Couvre :
  - le decoupage et la qualification des references de cables_href
  - la detection des formes XLink non resolues et des valeurs non textuelles
  - l'indexation des entites de toutes les couches du repertoire
  - le filtre de perimetre par couche et par statut
  - le classement des cinq types d'anomalie et leur cumul
  - la construction du GeoJSON d'ecarts
  - l'execution CLI
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from controle_e609 import (
    CHAMP_CABLES_HREF,
    CHAMP_STATUT,
    COUCHES_CABLE,
    COUCHES_CIBLES,
    EXTENSION,
    FICHIER_SORTIE,
    JETON_NON_TEXTUEL,
    PRIORITE_ANOMALIE,
    TYPE_CABLE_INTROUVABLE,
    TYPE_HORS_COUCHE_CABLE,
    TYPE_HREF_ABSENT,
    TYPE_HREF_VIDE,
    TYPE_REFERENCE_MALFORMEE,
    _decouper,
    classifier_rattachement,
    compter_noeuds_a_controler,
    compter_noeuds_non_conformes,
    construire_geojson_ecarts,
    detecter_anomalies_couche,
    est_a_controler,
    est_cable,
    est_reference_malformee,
    executer_controle_cli,
    extraire_references,
    indexer_entites,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

COUCHE_CIBLE: str = "RPD_PointDeComptage_Reco"
AUTRE_COUCHE_CIBLE: str = "RPD_Terre_Reco"
COUCHE_CABLE: str = "RPD_CableElectrique_Reco"
COUCHE_NON_CABLE: str = "RPD_Coffret_Reco"

GEOM_NOEUD: dict[str, Any] = {"type": "Point", "coordinates": [10.0, 20.0, 30.0]}

# Index minimal : un cable et une entite d'une autre nature
INDEX: dict[str, str] = {"idcable1": COUCHE_CABLE, "idcoffret1": COUCHE_NON_CABLE}


def _feature(identifiant: str, proprietes: dict[str, Any], geometrie: Any = GEOM_NOEUD) -> dict[str, Any]:
    props: dict[str, Any] = {"id": identifiant}
    props.update(proprietes)
    return {"type": "Feature", "properties": props, "geometry": geometrie}


def _noeud(
    identifiant: str = "n1",
    cables_href: Any = "idcable1",
    statut: str = "UnderCommissionning",
    proprietes: dict[str, Any] | None = None,
    avec_href: bool = True,
) -> dict[str, Any]:
    """Noeud du reseau, rattache par defaut a un cable existant."""
    props: dict[str, Any] = {CHAMP_STATUT: statut}
    if avec_href:
        props[CHAMP_CABLES_HREF] = cables_href
    props.update(proprietes or {})
    return _feature(identifiant, props)


def _ecrire_jeu(
    tmp_path: Any,
    noeuds: list[dict[str, Any]] | None = None,
    couche: str = COUCHE_CIBLE,
    cables: list[dict[str, Any]] | None = None,
) -> None:
    """Ecrit un jeu complet : une couche de noeuds, une couche de cable."""
    ecrire_collection(str(tmp_path / f"{couche}{EXTENSION}"), noeuds if noeuds is not None else [_noeud()])
    ecrire_collection(
        str(tmp_path / f"{COUCHE_CABLE}{EXTENSION}"),
        cables if cables is not None else [_feature("idcable1", {}, None)],
    )


def _types(anomalies: list[dict[str, Any]]) -> list[str]:
    return [anomalie["type_anomalie"] for anomalie in anomalies]


# --------------------------------------------------------------------------- #
# Decoupage des references
# --------------------------------------------------------------------------- #


class TestDecouper:
    """Tests de _decouper."""

    def test_reference_unique(self) -> None:
        assert _decouper("idcable1") == ["idcable1"]

    def test_separateur_virgule(self) -> None:
        assert _decouper("idcable1,idcable2") == ["idcable1", "idcable2"]

    def test_separateur_espace(self) -> None:
        assert _decouper("idcable1 idcable2") == ["idcable1", "idcable2"]

    def test_separateurs_melanges_et_espaces_superflus(self) -> None:
        assert _decouper(" idcable1 , idcable2 ") == ["idcable1", "idcable2"]

    def test_liste(self) -> None:
        assert _decouper(["idcable1", "idcable2"]) == ["idcable1", "idcable2"]

    def test_liste_avec_element_nul(self) -> None:
        assert _decouper(["idcable1", None]) == ["idcable1"]

    def test_valeur_nulle(self) -> None:
        """L'absence de valeur n'est pas une reference mal formee."""
        assert _decouper(None) == []

    def test_chaine_vide(self) -> None:
        assert _decouper("") == []

    def test_chaine_blanche(self) -> None:
        assert _decouper("   ") == []

    def test_liste_vide(self) -> None:
        assert _decouper([]) == []

    def test_entier_accepte_comme_identifiant(self) -> None:
        """obtenir_id_feature accepte un identifiant numerique : _decouper aussi."""
        assert _decouper(12) == ["12"]

    def test_booleen_non_textuel(self) -> None:
        """bool est un sous-type de int : il doit rester une valeur non textuelle."""
        assert _decouper(True) == [JETON_NON_TEXTUEL]

    def test_objet_non_textuel(self) -> None:
        assert _decouper({"href": "idcable1"}) == [JETON_NON_TEXTUEL]


# --------------------------------------------------------------------------- #
# Qualification des references
# --------------------------------------------------------------------------- #


class TestReferenceMalformee:
    """Tests de est_reference_malformee."""

    def test_identifiant_simple(self) -> None:
        assert est_reference_malformee("idcable1") is False

    def test_identifiant_inconnu_reste_bien_forme(self) -> None:
        """Un jeton sans correspondance n'est pas mal forme : il est introuvable."""
        assert est_reference_malformee("idinexistant") is False

    def test_fragment_xlink(self) -> None:
        assert est_reference_malformee("#idcable1") is True

    def test_urn(self) -> None:
        assert est_reference_malformee("urn:ogc:def:idcable1") is True

    def test_urn_casse_indifferente(self) -> None:
        assert est_reference_malformee("URN:ogc:def:idcable1") is True

    def test_url_absolue(self) -> None:
        assert est_reference_malformee("https://exemple.fr/idcable1") is True

    def test_valeur_non_textuelle(self) -> None:
        assert est_reference_malformee(JETON_NON_TEXTUEL) is True


class TestExtraireReferences:
    """Tests de extraire_references."""

    def test_reference_exploitable(self) -> None:
        exploitables, malformees = extraire_references("idcable1")
        assert exploitables == frozenset({"idcable1"})
        assert malformees == frozenset()

    def test_separation_des_deux_categories(self) -> None:
        exploitables, malformees = extraire_references("idcable1,#idcable2")
        assert exploitables == frozenset({"idcable1"})
        assert malformees == frozenset({"#idcable2"})

    def test_doublons_replies(self) -> None:
        """Une reference declaree deux fois designe un seul rattachement."""
        exploitables, _ = extraire_references("idcable1,idcable1")
        assert exploitables == frozenset({"idcable1"})

    def test_valeur_vide(self) -> None:
        assert extraire_references("") == (frozenset(), frozenset())

    def test_valeur_nulle(self) -> None:
        """None ne produit aucun jeton : l'absence est qualifiee en amont."""
        assert extraire_references(None) == (frozenset(), frozenset())


# --------------------------------------------------------------------------- #
# Couches de cable
# --------------------------------------------------------------------------- #


class TestEstCable:
    """Tests de est_cable."""

    def test_cable_electrique(self) -> None:
        assert est_cable("RPD_CableElectrique_Reco") is True

    def test_cable_terre(self) -> None:
        assert est_cable("RPD_CableTerre_Reco") is True

    def test_cable_telecommunication(self) -> None:
        assert est_cable("RPD_CableTelecommunication_Reco") is True

    def test_coffret(self) -> None:
        assert est_cable(COUCHE_NON_CABLE) is False

    def test_couches_cable_attendues(self) -> None:
        assert COUCHES_CABLE == frozenset(
            {
                "RPD_CableElectrique_Reco",
                "RPD_CableTerre_Reco",
                "RPD_CableTelecommunication_Reco",
            }
        )


# --------------------------------------------------------------------------- #
# Indexation des entites
# --------------------------------------------------------------------------- #


class TestIndexerEntites:
    """Tests de indexer_entites."""

    def test_index_couvre_toutes_les_couches(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        ecrire_collection(str(tmp_path / f"{COUCHE_NON_CABLE}{EXTENSION}"), [_feature("idcoffret1", {}, None)])
        index, nombre_cables, _ = indexer_entites(str(tmp_path))
        assert index["idcable1"] == COUCHE_CABLE
        assert index["idcoffret1"] == COUCHE_NON_CABLE
        assert nombre_cables == 1

    def test_noeuds_egalement_indexes(self, tmp_path: Any) -> None:
        """Toute entite est indexee : le noeud lui-meme n'est pas un cable."""
        _ecrire_jeu(tmp_path)
        index, _, _ = indexer_entites(str(tmp_path))
        assert index["n1"] == COUCHE_CIBLE

    def test_couches_cable_absentes(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        _, _, absentes = indexer_entites(str(tmp_path))
        assert absentes == ["RPD_CableTelecommunication_Reco", "RPD_CableTerre_Reco"]

    def test_feature_sans_identifiant_ignoree(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / f"{COUCHE_CABLE}{EXTENSION}"),
            [{"type": "Feature", "properties": {}, "geometry": None}],
        )
        index, nombre_cables, _ = indexer_entites(str(tmp_path))
        assert index == {}
        assert nombre_cables == 0

    def test_fichier_ecarts_exclu(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        ecrire_collection(str(tmp_path / f"ecarts_precedent{EXTENSION}"), [_feature("idecart1", {}, None)])
        index, _, _ = indexer_entites(str(tmp_path))
        assert "idecart1" not in index

    def test_repertoire_sans_geojson(self, tmp_path: Any) -> None:
        index, nombre_cables, absentes = indexer_entites(str(tmp_path))
        assert index == {}
        assert nombre_cables == 0
        assert len(absentes) == len(COUCHES_CABLE)


# --------------------------------------------------------------------------- #
# Perimetre
# --------------------------------------------------------------------------- #


class TestPerimetre:
    """Tests de est_a_controler."""

    def test_couche_cible_statut_under_commissionning(self) -> None:
        assert est_a_controler(COUCHE_CIBLE, {CHAMP_STATUT: "UnderCommissionning"}) is True

    def test_couche_cible_statut_functional(self) -> None:
        assert est_a_controler(COUCHE_CIBLE, {CHAMP_STATUT: "Functional"}) is True

    def test_statut_hors_perimetre(self) -> None:
        assert est_a_controler(COUCHE_CIBLE, {CHAMP_STATUT: "Abandoned"}) is False

    def test_statut_absent(self) -> None:
        assert est_a_controler(COUCHE_CIBLE, {}) is False

    def test_couche_hors_perimetre(self) -> None:
        assert est_a_controler(COUCHE_NON_CABLE, {CHAMP_STATUT: "Functional"}) is False

    def test_neuf_couches_cibles(self) -> None:
        assert set(COUCHES_CIBLES) == {
            "RPD_CoupeCircuitAFusibles_Reco",
            "RPD_ModuleRaccordement_Reco",
            "RPD_OuvrageCollectifBranchement_Reco",
            "RPD_PointDeComptage_Reco",
            "RPD_SupportModules_Reco",
            "RPD_Terre_Reco",
            "RPD_PosteElectrique_Reco",
            "RPD_JeuBarres_Reco",
            "RPD_Jonction_Reco",
        }


# --------------------------------------------------------------------------- #
# Classement des anomalies
# --------------------------------------------------------------------------- #


class TestClassifierRattachement:
    """Tests de classifier_rattachement."""

    def test_rattachement_valide(self) -> None:
        assert classifier_rattachement("idcable1", INDEX) == []

    def test_plusieurs_references_valides(self) -> None:
        index = dict(INDEX, idcable2="RPD_CableTerre_Reco")
        assert classifier_rattachement("idcable1,idcable2", index) == []

    def test_href_absent(self) -> None:
        assert classifier_rattachement(None, INDEX) == [(TYPE_HREF_ABSENT, None, None)]

    def test_href_vide(self) -> None:
        assert classifier_rattachement("", INDEX) == [(TYPE_HREF_VIDE, None, None)]

    def test_href_blanc(self) -> None:
        assert classifier_rattachement("   ", INDEX) == [(TYPE_HREF_VIDE, None, None)]

    def test_liste_vide(self) -> None:
        assert classifier_rattachement([], INDEX) == [(TYPE_HREF_VIDE, None, None)]

    def test_reference_malformee(self) -> None:
        assert classifier_rattachement("#idcable1", INDEX) == [(TYPE_REFERENCE_MALFORMEE, "#idcable1", None)]

    def test_cable_introuvable(self) -> None:
        assert classifier_rattachement("idinconnu", INDEX) == [(TYPE_CABLE_INTROUVABLE, "idinconnu", None)]

    def test_reference_hors_couche_cable(self) -> None:
        """L'entite existe : la couche resolue est reportee pour le diagnostic."""
        assert classifier_rattachement("idcoffret1", INDEX) == [
            (TYPE_HORS_COUCHE_CABLE, "idcoffret1", COUCHE_NON_CABLE)
        ]

    def test_une_anomalie_par_reference_fautive(self) -> None:
        codes = [code for code, _, _ in classifier_rattachement("idinconnu1,idinconnu2", INDEX)]
        assert codes == [TYPE_CABLE_INTROUVABLE, TYPE_CABLE_INTROUVABLE]

    def test_reference_valide_ne_repare_pas_une_reference_fautive(self) -> None:
        anomalies = classifier_rattachement("idcable1,idinconnu", INDEX)
        assert anomalies == [(TYPE_CABLE_INTROUVABLE, "idinconnu", None)]

    def test_cumul_des_types(self) -> None:
        """Les malformees d'abord, puis les references exploitables triees."""
        codes = [code for code, _, _ in classifier_rattachement("#idmal,idinconnu,idcoffret1", INDEX)]
        assert codes == [TYPE_REFERENCE_MALFORMEE, TYPE_HORS_COUCHE_CABLE, TYPE_CABLE_INTROUVABLE]

    def test_ordre_deterministe(self) -> None:
        premier = classifier_rattachement("idb,ida", INDEX)
        second = classifier_rattachement("ida,idb", INDEX)
        assert premier == second
        assert [reference for _, reference, _ in premier] == ["ida", "idb"]

    def test_valeur_non_textuelle(self) -> None:
        assert classifier_rattachement({"href": "idcable1"}, INDEX) == [
            (TYPE_REFERENCE_MALFORMEE, JETON_NON_TEXTUEL, None)
        ]


# --------------------------------------------------------------------------- #
# Detection sur une couche
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesCouche:
    """Tests de detecter_anomalies_couche."""

    def test_noeud_conforme(self) -> None:
        assert detecter_anomalies_couche(COUCHE_CIBLE, [_noeud()], INDEX) == []

    def test_noeud_sans_href(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [_noeud(avec_href=False)], INDEX)
        assert _types(anomalies) == [TYPE_HREF_ABSENT]
        assert anomalies[0]["id_noeud"] == "n1"
        assert anomalies[0]["couche_noeud"] == COUCHE_CIBLE

    def test_statut_hors_perimetre_ignore(self) -> None:
        noeuds = [_noeud(statut="Abandoned", avec_href=False)]
        assert detecter_anomalies_couche(COUCHE_CIBLE, noeuds, INDEX) == []

    def test_statut_functional_controle(self) -> None:
        noeuds = [_noeud(statut="Functional", avec_href=False)]
        assert _types(detecter_anomalies_couche(COUCHE_CIBLE, noeuds, INDEX)) == [TYPE_HREF_ABSENT]

    def test_couche_hors_perimetre_non_parcourue(self) -> None:
        noeuds = [_noeud(avec_href=False)]
        assert detecter_anomalies_couche(COUCHE_NON_CABLE, noeuds, INDEX) == []

    def test_geometrie_du_noeud_conservee(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [_noeud(avec_href=False)], INDEX)
        assert anomalies[0]["geometrie"] == GEOM_NOEUD

    def test_valeur_brute_conservee(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [_noeud(cables_href="idcable1,idinconnu")], INDEX)
        assert anomalies[0]["cables_href"] == "idcable1,idinconnu"
        assert anomalies[0]["reference"] == "idinconnu"

    def test_plusieurs_noeuds(self) -> None:
        noeuds = [_noeud("n1"), _noeud("n2", cables_href="idinconnu"), _noeud("n3", avec_href=False)]
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, noeuds, INDEX)
        assert _types(anomalies) == [TYPE_CABLE_INTROUVABLE, TYPE_HREF_ABSENT]

    def test_proprietes_nulles(self) -> None:
        feature: dict[str, Any] = {"type": "Feature", "properties": None, "geometry": None}
        assert detecter_anomalies_couche(COUCHE_CIBLE, [feature], INDEX) == []


# --------------------------------------------------------------------------- #
# Comptages
# --------------------------------------------------------------------------- #


class TestComptages:
    """Tests des fonctions de comptage du rapport."""

    def test_noeuds_a_controler(self) -> None:
        noeuds = [_noeud("n1"), _noeud("n2", statut="Functional"), _noeud("n3", statut="Abandoned")]
        assert compter_noeuds_a_controler(COUCHE_CIBLE, noeuds) == 2

    def test_noeuds_a_controler_couche_hors_perimetre(self) -> None:
        assert compter_noeuds_a_controler(COUCHE_NON_CABLE, [_noeud()]) == 0

    def test_noeuds_non_conformes_dedoublonnes(self) -> None:
        """Deux anomalies d'un meme noeud ne comptent qu'un noeud non conforme."""
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [_noeud(cables_href="idinconnu1,idinconnu2")], INDEX)
        assert len(anomalies) == 2
        assert compter_noeuds_non_conformes(anomalies) == 1

    def test_noeuds_homonymes_de_couches_differentes(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [_noeud("n1", avec_href=False)], INDEX)
        anomalies += detecter_anomalies_couche(AUTRE_COUCHE_CIBLE, [_noeud("n1", avec_href=False)], INDEX)
        assert compter_noeuds_non_conformes(anomalies) == 2


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def test_collection_vide(self) -> None:
        resultat = construire_geojson_ecarts([])
        assert resultat == {"type": "FeatureCollection", "features": []}

    def test_socle_commun(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [_noeud(cables_href="idcoffret1")], INDEX)
        proprietes = construire_geojson_ecarts(anomalies)["features"][0]["properties"]
        assert list(proprietes)[:5] == [
            "code_controle",
            "priorite",
            "id_entite",
            "type_anomalie",
            "description",
        ]
        assert proprietes["code_controle"] == "E609"
        assert proprietes["priorite"] == PRIORITE_ANOMALIE
        assert proprietes["id_entite"] == "n1"
        assert proprietes["description"]

    def test_proprietes_metier(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [_noeud(cables_href="idcoffret1")], INDEX)
        proprietes = construire_geojson_ecarts(anomalies)["features"][0]["properties"]
        assert proprietes["fichier_source"] == f"{COUCHE_CIBLE}{EXTENSION}"
        assert proprietes["couche_noeud"] == COUCHE_CIBLE
        assert proprietes["couche_reference"] == COUCHE_NON_CABLE
        assert proprietes["reference"] == "idcoffret1"
        assert proprietes["statut"] == "UnderCommissionning"

    def test_geometrie_propagee(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [_noeud(avec_href=False)], INDEX)
        assert construire_geojson_ecarts(anomalies)["features"][0]["geometry"] == GEOM_NOEUD

    def test_crs_propage(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], crs)["crs"] == crs


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_jeu_conforme_sans_fichier(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_anomalie_detectee(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(cables_href="idinconnu")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
        assert resultat["anomalies_par_type"] == {TYPE_CABLE_INTROUVABLE: 1}
        assert resultat["nombre_noeuds_non_conformes"] == 1
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_reference_vers_entite_non_cable(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(cables_href="idcoffret1")])
        ecrire_collection(str(tmp_path / f"{COUCHE_NON_CABLE}{EXTENSION}"), [_feature("idcoffret1", {}, None)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_HORS_COUCHE_CABLE: 1}

    def test_comptages_du_rapport(self, tmp_path: Any) -> None:
        noeuds = [_noeud("n1"), _noeud("n2", statut="Abandoned", avec_href=False)]
        _ecrire_jeu(tmp_path, noeuds)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_noeuds_analyses"] == 2
        assert resultat["nombre_noeuds_controles"] == 1
        assert resultat["nombre_cables_indexes"] == 1
        assert resultat["nombre_entites_indexees"] == 3
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_couches_absentes_signalees(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert COUCHE_CIBLE not in resultat["couches_absentes"]
        assert len(resultat["couches_absentes"]) == len(COUCHES_CIBLES) - 1
        assert "RPD_CableTerre_Reco" in resultat["couches_cable_absentes"]

    def test_plusieurs_couches_cibles(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud("n1", cables_href="idinconnu")])
        ecrire_collection(
            str(tmp_path / f"{AUTRE_COUCHE_CIBLE}{EXTENSION}"),
            [_noeud("n2", avec_href=False)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 2
        assert resultat["nombre_noeuds_non_conformes"] == 2

    def test_crs_propage_au_fichier(self, tmp_path: Any) -> None:
        ecrire_collection_avec_crs(
            str(tmp_path / f"{COUCHE_CIBLE}{EXTENSION}"),
            [_noeud(avec_href=False)],
            "EPSG:2154",
        )
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert ecarts["crs"]["properties"]["name"].endswith("2154")

    def test_repertoire_de_sortie_distinct(self, tmp_path: Any) -> None:
        sortie = tmp_path / "controle" / "conteneur"
        _ecrire_jeu(tmp_path, [_noeud(avec_href=False)])
        resultat = executer_controle_cli(str(tmp_path), str(sortie))
        assert resultat["sortie"] == str((sortie / FICHIER_SORTIE).resolve())
        assert os.path.isfile(str(sortie / FICHIER_SORTIE))

    def test_fichier_precedent_supprime(self, tmp_path: Any) -> None:
        """La presence du fichier reste un indicateur fiable d'ecarts."""
        chemin = str(tmp_path / FICHIER_SORTIE)
        ecrire_collection(chemin, [_feature("ancien", {}, None)])
        _ecrire_jeu(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(chemin)

    def test_fichier_ecarts_non_analyse(self, tmp_path: Any) -> None:
        """Le fichier d'ecarts precedent ne doit pas alimenter l'index."""
        _ecrire_jeu(tmp_path, [_noeud(cables_href="idancien")])
        ecrire_collection(str(tmp_path / "ecarts_autre.geojson"), [_feature("idancien", {}, None)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_CABLE_INTROUVABLE: 1}


# --------------------------------------------------------------------------- #
# Versions RecoStaR
# --------------------------------------------------------------------------- #


class TestVersions:
    """Le controle est agnostique de version : V1.0 et V1.1 se comportent pareil."""

    def test_champs_supplementaires_v1_1_sans_effet(self, tmp_path: Any) -> None:
        noeud_v1_0 = _noeud("n1", cables_href="idinconnu")
        noeud_v1_1 = _noeud("n2", cables_href="idinconnu", proprietes={"Commentaire": "ajout V1.1"})
        _ecrire_jeu(tmp_path, [noeud_v1_0, noeud_v1_1])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_CABLE_INTROUVABLE: 2}
