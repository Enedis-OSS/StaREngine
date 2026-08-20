"""
Tests du controle E610 : nomenclature de composition des coffrets.

Couvre :
  - la resolution du TypeCoffret depuis TypeCoffret_href (code seul ou fragment)
  - le filtre de perimetre par statut et par TypeCoffret
  - le comptage des noeuds rattaches, toutes couches confondues
  - les huit nomenclatures et leurs bornes
  - les trois types d'anomalie et leur cumul
  - la redaction du detail explicite
  - la construction du GeoJSON d'ecarts
  - l'execution CLI
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from controle_e610 import (
    AU_PLUS_UN,
    CHAMP_STATUT,
    CHAMP_TYPE_COFFRET_HREF,
    COUPE_CIRCUIT,
    EXACTEMENT_UN,
    FICHIER_COFFRET,
    FICHIER_SORTIE,
    JEU_BARRES,
    MODULE_RACCORDEMENT,
    NOMENCLATURES,
    OUVRAGE_COLLECTIF,
    POINT_DE_COMPTAGE,
    PRIORITE_ANOMALIE,
    SANS_PLAFOND,
    SUPPORT_MODULES,
    TERRE,
    TYPE_NOEUD_NON_AUTORISE,
    TYPE_NOEUDS_EXCESSIFS,
    TYPE_NOEUDS_INSUFFISANTS,
    Coffret,
    RegleNoeud,
    charger_coffrets_a_controler,
    classifier_composition,
    compter_coffrets_non_conformes,
    compter_noeuds_par_coffret,
    compter_par_type_coffret,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
    formuler_detail,
    nomenclature_applicable,
    resoudre_type_coffret,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

EXTENSION: str = ".geojson"
ID_COFFRET: str = "cof1"
GEOM_COFFRET: dict[str, Any] = {"type": "Point", "coordinates": [10.0, 20.0, 30.0]}
COUCHE_INTERDITE: str = "RPD_Jonction_Reco"


def _coffret(
    identifiant: str = ID_COFFRET,
    type_coffret: Any = "RMBT300",
    statut: str = "UnderCommissionning",
    proprietes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Feature GeoJSON representant un coffret."""
    props: dict[str, Any] = {"id": identifiant, CHAMP_STATUT: statut}
    if type_coffret is not None:
        props[CHAMP_TYPE_COFFRET_HREF] = type_coffret
    props.update(proprietes or {})
    return {"type": "Feature", "properties": props, "geometry": GEOM_COFFRET}


def _noeud(identifiant: str, conteneur_href: Any = ID_COFFRET) -> dict[str, Any]:
    """Feature GeoJSON representant un noeud rattache a un coffret."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "conteneur_href": conteneur_href},
        "geometry": None,
    }


def _ecrire_jeu(tmp_path: Any, coffrets: list[dict[str, Any]], noeuds: dict[str, list[dict[str, Any]]]) -> None:
    """Ecrit le fichier des coffrets et une couche par type de noeud fourni."""
    ecrire_collection(str(tmp_path / FICHIER_COFFRET), coffrets)
    for couche, features in noeuds.items():
        ecrire_collection(str(tmp_path / f"{couche}{EXTENSION}"), features)


def _index(type_coffret: str = "RMBT300") -> dict[str, Coffret]:
    return {ID_COFFRET: Coffret(type_coffret, GEOM_COFFRET)}


def _types(anomalies: list[dict[str, Any]]) -> list[str]:
    return [anomalie["type_anomalie"] for anomalie in anomalies]


def _composition_valide(type_coffret: str) -> dict[str, int]:
    """Composition satisfaisant la nomenclature : le minimum de chaque regle."""
    return {couche: regle.minimum for couche, regle in NOMENCLATURES[type_coffret].items() if regle.minimum}


# --------------------------------------------------------------------------- #
# Resolution du TypeCoffret
# --------------------------------------------------------------------------- #


class TestResoudreTypeCoffret:
    """Tests de resoudre_type_coffret."""

    def test_code_seul(self) -> None:
        assert resoudre_type_coffret({CHAMP_TYPE_COFFRET_HREF: "RMBT300"}) == "RMBT300"

    def test_reference_fragmentee(self) -> None:
        """Forme « ...#RMBT300 » : le code est le fragment final."""
        valeur = "http://exemple.fr/codelists/TypeCoffret.xml#RMBT300"
        assert resoudre_type_coffret({CHAMP_TYPE_COFFRET_HREF: valeur}) == "RMBT300"

    def test_fragment_seul(self) -> None:
        assert resoudre_type_coffret({CHAMP_TYPE_COFFRET_HREF: "#CIBE"}) == "CIBE"

    def test_espaces_superflus(self) -> None:
        assert resoudre_type_coffret({CHAMP_TYPE_COFFRET_HREF: "  CGV  "}) == "CGV"

    def test_champ_absent(self) -> None:
        assert resoudre_type_coffret({}) is None

    def test_valeur_nulle(self) -> None:
        assert resoudre_type_coffret({CHAMP_TYPE_COFFRET_HREF: None}) is None

    def test_valeur_vide(self) -> None:
        assert resoudre_type_coffret({CHAMP_TYPE_COFFRET_HREF: ""}) is None

    def test_fragment_vide(self) -> None:
        assert resoudre_type_coffret({CHAMP_TYPE_COFFRET_HREF: "codelist.xml#"}) is None


# --------------------------------------------------------------------------- #
# Perimetre
# --------------------------------------------------------------------------- #


class TestPerimetre:
    """Tests de nomenclature_applicable."""

    def test_statut_under_commissionning(self) -> None:
        proprietes = {CHAMP_STATUT: "UnderCommissionning", CHAMP_TYPE_COFFRET_HREF: "RMBT300"}
        assert nomenclature_applicable(proprietes) is NOMENCLATURES["RMBT300"]

    def test_statut_functional(self) -> None:
        proprietes = {CHAMP_STATUT: "Functional", CHAMP_TYPE_COFFRET_HREF: "CIBE"}
        assert nomenclature_applicable(proprietes) is NOMENCLATURES["CIBE"]

    def test_statut_hors_perimetre(self) -> None:
        proprietes = {CHAMP_STATUT: "Abandoned", CHAMP_TYPE_COFFRET_HREF: "RMBT300"}
        assert nomenclature_applicable(proprietes) is None

    def test_statut_absent(self) -> None:
        assert nomenclature_applicable({CHAMP_TYPE_COFFRET_HREF: "RMBT300"}) is None

    def test_type_sans_nomenclature(self) -> None:
        """Telecom et Autre appartiennent a la code-list mais n'ont pas de regle."""
        proprietes = {CHAMP_STATUT: "Functional", CHAMP_TYPE_COFFRET_HREF: "Telecom"}
        assert nomenclature_applicable(proprietes) is None

    def test_type_absent(self) -> None:
        assert nomenclature_applicable({CHAMP_STATUT: "Functional"}) is None

    def test_libelle_avec_espace_non_reconnu(self) -> None:
        """Le code normatif est « ArmoireComptage », sans espace (PDF §10.3.2)."""
        proprietes = {CHAMP_STATUT: "Functional", CHAMP_TYPE_COFFRET_HREF: "Armoire comptage"}
        assert nomenclature_applicable(proprietes) is None
        assert "ArmoireComptage" in NOMENCLATURES


# --------------------------------------------------------------------------- #
# Table des nomenclatures
# --------------------------------------------------------------------------- #


class TestNomenclatures:
    """La table doit transcrire fidelement la specification metier."""

    def test_huit_types(self) -> None:
        assert set(NOMENCLATURES) == {
            "RMBT300",
            "RMBT450",
            "RMBT600",
            "CIBE",
            "CGV",
            "ECP2D",
            "ECP3D",
            "ArmoireComptage",
        }

    def test_rmbt300(self) -> None:
        assert NOMENCLATURES["RMBT300"] == {
            MODULE_RACCORDEMENT: EXACTEMENT_UN,
            POINT_DE_COMPTAGE: SANS_PLAFOND,
            SUPPORT_MODULES: SANS_PLAFOND,
            TERRE: AU_PLUS_UN,
        }

    def test_rmbt450_et_600_identiques(self) -> None:
        assert NOMENCLATURES["RMBT450"] == NOMENCLATURES["RMBT600"]

    def test_rmbt450_admet_ouvrage_collectif(self) -> None:
        """Seule difference avec RMBT300 : l'OuvrageCollectifBranchement."""
        assert OUVRAGE_COLLECTIF in NOMENCLATURES["RMBT450"]
        assert OUVRAGE_COLLECTIF not in NOMENCLATURES["RMBT300"]

    def test_cibe(self) -> None:
        assert NOMENCLATURES["CIBE"] == {
            COUPE_CIRCUIT: EXACTEMENT_UN,
            JEU_BARRES: AU_PLUS_UN,
            POINT_DE_COMPTAGE: SANS_PLAFOND,
            TERRE: AU_PLUS_UN,
        }

    def test_cgv_sans_obligation_de_presence(self) -> None:
        assert all(regle.minimum == 0 for regle in NOMENCLATURES["CGV"].values())

    def test_ecp2d_exige_un_coupe_circuit(self) -> None:
        assert NOMENCLATURES["ECP2D"][COUPE_CIRCUIT] == EXACTEMENT_UN

    def test_ecp3d_admet_deux_coupe_circuit(self) -> None:
        assert NOMENCLATURES["ECP3D"][COUPE_CIRCUIT] == RegleNoeud(0, 2)

    def test_armoire_comptage(self) -> None:
        assert NOMENCLATURES["ArmoireComptage"] == {
            COUPE_CIRCUIT: AU_PLUS_UN,
            POINT_DE_COMPTAGE: SANS_PLAFOND,
            TERRE: AU_PLUS_UN,
        }

    def test_terre_au_plus_un_partout(self) -> None:
        for type_coffret, nomenclature in NOMENCLATURES.items():
            assert nomenclature[TERRE] == AU_PLUS_UN, type_coffret

    def test_point_de_comptage_sans_plafond_partout(self) -> None:
        for type_coffret, nomenclature in NOMENCLATURES.items():
            assert nomenclature[POINT_DE_COMPTAGE] == SANS_PLAFOND, type_coffret

    def test_seules_obligations_les_exactement_un(self) -> None:
        """« plusieurs » vaut 0 ou plusieurs : aucun minimum au-dela des « 1 »."""
        obligations = {
            (type_coffret, couche)
            for type_coffret, nomenclature in NOMENCLATURES.items()
            for couche, regle in nomenclature.items()
            if regle.minimum
        }
        assert obligations == {
            ("RMBT300", MODULE_RACCORDEMENT),
            ("RMBT450", MODULE_RACCORDEMENT),
            ("RMBT600", MODULE_RACCORDEMENT),
            ("CIBE", COUPE_CIRCUIT),
            ("ECP2D", COUPE_CIRCUIT),
        }


# --------------------------------------------------------------------------- #
# Chargement et comptage
# --------------------------------------------------------------------------- #


class TestChargerCoffrets:
    """Tests de charger_coffrets_a_controler."""

    def test_coffret_du_perimetre(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_coffret()], {})
        coffrets, _, absent = charger_coffrets_a_controler(str(tmp_path))
        assert absent is False
        assert coffrets == {ID_COFFRET: Coffret("RMBT300", GEOM_COFFRET)}

    def test_statut_hors_perimetre_ecarte(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_coffret(statut="Abandoned")], {})
        coffrets, _, _ = charger_coffrets_a_controler(str(tmp_path))
        assert coffrets == {}

    def test_type_sans_nomenclature_ecarte(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_coffret(type_coffret="Autre")], {})
        coffrets, _, _ = charger_coffrets_a_controler(str(tmp_path))
        assert coffrets == {}

    def test_coffret_sans_identifiant_ignore(self, tmp_path: Any) -> None:
        feature = {
            "type": "Feature",
            "properties": {CHAMP_STATUT: "Functional", CHAMP_TYPE_COFFRET_HREF: "CGV"},
            "geometry": None,
        }
        _ecrire_jeu(tmp_path, [feature], {})
        coffrets, _, _ = charger_coffrets_a_controler(str(tmp_path))
        assert coffrets == {}

    def test_fichier_absent(self, tmp_path: Any) -> None:
        coffrets, crs, absent = charger_coffrets_a_controler(str(tmp_path))
        assert (coffrets, crs, absent) == ({}, None, True)


class TestCompterNoeudsParCoffret:
    """Tests de compter_noeuds_par_coffret."""

    def test_comptage_par_couche(self, tmp_path: Any) -> None:
        _ecrire_jeu(
            tmp_path,
            [_coffret()],
            {
                MODULE_RACCORDEMENT: [_noeud("m1")],
                POINT_DE_COMPTAGE: [_noeud("p1"), _noeud("p2")],
            },
        )
        comptes, _, liens = compter_noeuds_par_coffret(str(tmp_path), _index())
        assert dict(comptes[ID_COFFRET]) == {MODULE_RACCORDEMENT: 1, POINT_DE_COMPTAGE: 2}
        assert liens == 3

    def test_couche_interdite_comptee(self, tmp_path: Any) -> None:
        """Toutes les couches sont parcourues : sinon un type interdit echapperait."""
        _ecrire_jeu(tmp_path, [_coffret()], {COUCHE_INTERDITE: [_noeud("j1")]})
        comptes, _, _ = compter_noeuds_par_coffret(str(tmp_path), _index())
        assert dict(comptes[ID_COFFRET]) == {COUCHE_INTERDITE: 1}

    def test_reference_vers_autre_conteneur_ignoree(self, tmp_path: Any) -> None:
        """Les conteneur_href visant un support ne relevent pas de cette regle."""
        _ecrire_jeu(tmp_path, [_coffret()], {TERRE: [_noeud("t1", conteneur_href="support9")]})
        comptes, _, liens = compter_noeuds_par_coffret(str(tmp_path), _index())
        assert comptes == {}
        assert liens == 0

    def test_noeud_sans_reference_ignore(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_coffret()], {TERRE: [_noeud("t1", conteneur_href=None)]})
        comptes, _, liens = compter_noeuds_par_coffret(str(tmp_path), _index())
        assert (comptes, liens) == ({}, 0)

    def test_fichier_ecarts_exclu(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_coffret()], {})
        ecrire_collection(str(tmp_path / f"ecarts_precedent{EXTENSION}"), [_noeud("x1")])
        comptes, _, liens = compter_noeuds_par_coffret(str(tmp_path), _index())
        assert (comptes, liens) == ({}, 0)


# --------------------------------------------------------------------------- #
# Classement de la composition
# --------------------------------------------------------------------------- #


class TestClassifierComposition:
    """Tests de classifier_composition."""

    def test_composition_conforme(self) -> None:
        comptes = {MODULE_RACCORDEMENT: 1, POINT_DE_COMPTAGE: 5, TERRE: 1}
        assert classifier_composition(NOMENCLATURES["RMBT300"], comptes) == []

    def test_obligation_de_presence_non_satisfaite(self) -> None:
        anomalies = classifier_composition(NOMENCLATURES["RMBT300"], {})
        assert anomalies == [(TYPE_NOEUDS_INSUFFISANTS, MODULE_RACCORDEMENT, 0, 1, 1)]

    def test_maximum_depasse(self) -> None:
        comptes = {MODULE_RACCORDEMENT: 1, TERRE: 2}
        anomalies = classifier_composition(NOMENCLATURES["RMBT300"], comptes)
        assert anomalies == [(TYPE_NOEUDS_EXCESSIFS, TERRE, 2, 0, 1)]

    def test_exactement_un_depasse(self) -> None:
        comptes = {MODULE_RACCORDEMENT: 2}
        anomalies = classifier_composition(NOMENCLATURES["RMBT300"], comptes)
        assert anomalies == [(TYPE_NOEUDS_EXCESSIFS, MODULE_RACCORDEMENT, 2, 1, 1)]

    def test_sans_plafond_jamais_excessif(self) -> None:
        comptes = {MODULE_RACCORDEMENT: 1, POINT_DE_COMPTAGE: 999}
        assert classifier_composition(NOMENCLATURES["RMBT300"], comptes) == []

    def test_type_non_autorise(self) -> None:
        comptes = {MODULE_RACCORDEMENT: 1, JEU_BARRES: 1}
        anomalies = classifier_composition(NOMENCLATURES["RMBT300"], comptes)
        assert anomalies == [(TYPE_NOEUD_NON_AUTORISE, JEU_BARRES, 1, 0, 0)]

    def test_cumul_compte_et_interdiction(self) -> None:
        comptes = {TERRE: 2, COUCHE_INTERDITE: 1}
        codes = _types_tuples(classifier_composition(NOMENCLATURES["RMBT300"], comptes))
        assert codes == [TYPE_NOEUDS_INSUFFISANTS, TYPE_NOEUDS_EXCESSIFS, TYPE_NOEUD_NON_AUTORISE]

    def test_ordre_deterministe(self) -> None:
        comptes = {MODULE_RACCORDEMENT: 1, "RPD_Zebre_Reco": 1, COUCHE_INTERDITE: 1}
        couches = [couche for _, couche, _, _, _ in classifier_composition(NOMENCLATURES["RMBT300"], comptes)]
        assert couches == [COUCHE_INTERDITE, "RPD_Zebre_Reco"]

    def test_ecp3d_deux_coupe_circuit_admis(self) -> None:
        assert classifier_composition(NOMENCLATURES["ECP3D"], {COUPE_CIRCUIT: 2}) == []

    def test_ecp3d_trois_coupe_circuit_excessif(self) -> None:
        anomalies = classifier_composition(NOMENCLATURES["ECP3D"], {COUPE_CIRCUIT: 3})
        assert anomalies == [(TYPE_NOEUDS_EXCESSIFS, COUPE_CIRCUIT, 3, 0, 2)]

    def test_coffret_vide_conforme_si_aucune_obligation(self) -> None:
        """Un CGV n'impose la presence d'aucun noeud."""
        assert classifier_composition(NOMENCLATURES["CGV"], {}) == []

    def test_chaque_nomenclature_admet_sa_composition_minimale(self) -> None:
        for type_coffret, nomenclature in NOMENCLATURES.items():
            comptes = _composition_valide(type_coffret)
            assert classifier_composition(nomenclature, comptes) == [], type_coffret


def _types_tuples(anomalies: list[tuple[str, str, int, int, int | None]]) -> list[str]:
    return [type_anomalie for type_anomalie, _, _, _, _ in anomalies]


# --------------------------------------------------------------------------- #
# Redaction du detail
# --------------------------------------------------------------------------- #


class TestFormulerDetail:
    """Tests de formuler_detail."""

    def test_exactement(self) -> None:
        detail = formuler_detail(ID_COFFRET, "RMBT300", MODULE_RACCORDEMENT, 0, 1, 1)
        assert detail == (
            f"Coffret {ID_COFFRET} de type RMBT300 : {MODULE_RACCORDEMENT} attendu exactement 1, trouvé 0."
        )

    def test_au_maximum(self) -> None:
        detail = formuler_detail(ID_COFFRET, "CIBE", TERRE, 3, 0, 1)
        assert "attendu au maximum 1, trouvé 3." in detail

    def test_au_minimum(self) -> None:
        detail = formuler_detail(ID_COFFRET, "CGV", POINT_DE_COMPTAGE, 0, 2, None)
        assert "attendu au minimum 2, trouvé 0." in detail

    def test_intervalle(self) -> None:
        detail = formuler_detail(ID_COFFRET, "ECP3D", COUPE_CIRCUIT, 5, 1, 2)
        assert "attendu entre 1 et 2, trouvé 5." in detail

    def test_type_non_autorise(self) -> None:
        detail = formuler_detail(ID_COFFRET, "RMBT300", JEU_BARRES, 2, 0, 0, autorise=False)
        assert detail == (
            f"Coffret {ID_COFFRET} de type RMBT300 : {JEU_BARRES} "
            "n'est pas autorisé par la nomenclature (attendu 0, trouvé 2)."
        )

    def test_detail_identifie_les_cinq_elements_attendus(self) -> None:
        """Coffret, TypeCoffret, type de noeud, nombre attendu, nombre trouve."""
        detail = formuler_detail(ID_COFFRET, "CIBE", TERRE, 3, 0, 1)
        for element in (ID_COFFRET, "CIBE", TERRE, "1", "3"):
            assert element in detail


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_coffret_conforme(self) -> None:
        comptes = {ID_COFFRET: {MODULE_RACCORDEMENT: 1}}
        assert detecter_anomalies(_index(), comptes) == []

    def test_coffret_sans_aucun_noeud_evalue(self) -> None:
        """Un coffret absent des comptes doit tout de meme etre evalue."""
        anomalies = detecter_anomalies(_index(), {})
        assert _types(anomalies) == [TYPE_NOEUDS_INSUFFISANTS]
        assert anomalies[0]["nombre_trouve"] == 0

    def test_champs_de_l_anomalie(self) -> None:
        comptes = {ID_COFFRET: {MODULE_RACCORDEMENT: 1, TERRE: 4}}
        anomalie = detecter_anomalies(_index(), comptes)[0]
        assert anomalie["id_coffret"] == ID_COFFRET
        assert anomalie["type_coffret"] == "RMBT300"
        assert anomalie["couche_noeud"] == TERRE
        assert anomalie["nombre_trouve"] == 4
        assert anomalie["nombre_maximum"] == 1
        assert anomalie["geometrie"] == GEOM_COFFRET
        assert "trouvé 4" in anomalie["detail"]

    def test_plusieurs_anomalies_par_coffret(self) -> None:
        comptes = {ID_COFFRET: {TERRE: 2, COUCHE_INTERDITE: 1}}
        anomalies = detecter_anomalies(_index(), comptes)
        assert len(anomalies) == 3
        assert compter_coffrets_non_conformes(anomalies) == 1

    def test_plusieurs_coffrets(self) -> None:
        coffrets = {
            "cof1": Coffret("RMBT300", GEOM_COFFRET),
            "cof2": Coffret("CGV", None),
        }
        anomalies = detecter_anomalies(coffrets, {"cof2": {JEU_BARRES: 1}})
        assert _types(anomalies) == [TYPE_NOEUDS_INSUFFISANTS, TYPE_NOEUD_NON_AUTORISE]
        assert compter_coffrets_non_conformes(anomalies) == 2

    def test_ventilation_par_type_coffret(self) -> None:
        coffrets = {
            "cof1": Coffret("RMBT300", None),
            "cof2": Coffret("CGV", None),
            "cof3": Coffret("RMBT300", None),
        }
        assert compter_par_type_coffret(coffrets) == {"RMBT300": 2, "CGV": 1}


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def test_collection_vide(self) -> None:
        assert construire_geojson_ecarts([]) == {"type": "FeatureCollection", "features": []}

    def test_socle_commun(self) -> None:
        anomalies = detecter_anomalies(_index(), {})
        proprietes = construire_geojson_ecarts(anomalies)["features"][0]["properties"]
        assert list(proprietes)[:5] == [
            "code_controle",
            "priorite",
            "id_entite",
            "type_anomalie",
            "description",
        ]
        assert proprietes["code_controle"] == "E610"
        assert proprietes["priorite"] == PRIORITE_ANOMALIE
        assert proprietes["id_entite"] == ID_COFFRET

    def test_proprietes_metier(self) -> None:
        comptes = {ID_COFFRET: {MODULE_RACCORDEMENT: 1, TERRE: 2}}
        proprietes = construire_geojson_ecarts(detecter_anomalies(_index(), comptes))["features"][0]["properties"]
        assert proprietes["fichier_source"] == FICHIER_COFFRET
        assert proprietes["type_coffret"] == "RMBT300"
        assert proprietes["couche_noeud"] == TERRE
        assert proprietes["nombre_trouve"] == 2
        assert proprietes["nombre_minimum"] == 0
        assert proprietes["nombre_maximum"] == 1
        assert "trouvé 2" in proprietes["detail"]

    def test_geometrie_du_coffret(self) -> None:
        anomalies = detecter_anomalies(_index(), {})
        assert construire_geojson_ecarts(anomalies)["features"][0]["geometry"] == GEOM_COFFRET

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
        _ecrire_jeu(tmp_path, [_coffret()], {MODULE_RACCORDEMENT: [_noeud("m1")]})
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_obligation_de_presence(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_coffret()], {})
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_NOEUDS_INSUFFISANTS: 1}
        assert resultat["priorite"] == "majeur"
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_maximum_depasse(self, tmp_path: Any) -> None:
        noeuds = {MODULE_RACCORDEMENT: [_noeud("m1")], TERRE: [_noeud("t1"), _noeud("t2")]}
        _ecrire_jeu(tmp_path, [_coffret()], noeuds)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_NOEUDS_EXCESSIFS: 1}

    def test_type_non_autorise(self, tmp_path: Any) -> None:
        noeuds = {MODULE_RACCORDEMENT: [_noeud("m1")], JEU_BARRES: [_noeud("b1")]}
        _ecrire_jeu(tmp_path, [_coffret()], noeuds)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_NOEUD_NON_AUTORISE: 1}

    def test_type_coffret_fragmente(self, tmp_path: Any) -> None:
        coffret = _coffret(type_coffret="http://exemple.fr/codelists.xml#CIBE")
        _ecrire_jeu(tmp_path, [coffret], {COUPE_CIRCUIT: [_noeud("c1")]})
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["coffrets_par_type"] == {"CIBE": 1}
        assert resultat["nombre_anomalies"] == 0

    def test_comptages_du_rapport(self, tmp_path: Any) -> None:
        coffrets = [_coffret(), _coffret("cof2", type_coffret="Telecom")]
        _ecrire_jeu(tmp_path, coffrets, {MODULE_RACCORDEMENT: [_noeud("m1")]})
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_coffrets_controles"] == 1
        assert resultat["nombre_coffrets_non_conformes"] == 0
        assert resultat["nombre_noeuds_rattaches"] == 1
        assert resultat["nombre_couches_analysees"] == 2
        assert resultat["fichier_coffret_absent"] is False

    def test_fichier_coffret_absent(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_coffret_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_crs_propage_au_fichier(self, tmp_path: Any) -> None:
        ecrire_collection_avec_crs(str(tmp_path / FICHIER_COFFRET), [_coffret()], "EPSG:2154")
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert ecarts["crs"]["properties"]["name"].endswith("2154")

    def test_repertoire_de_sortie_distinct(self, tmp_path: Any) -> None:
        sortie = tmp_path / "controle" / "conteneur"
        _ecrire_jeu(tmp_path, [_coffret()], {})
        resultat = executer_controle_cli(str(tmp_path), str(sortie))
        assert resultat["sortie"] == str((sortie / FICHIER_SORTIE).resolve())
        assert os.path.isfile(str(sortie / FICHIER_SORTIE))

    def test_fichier_precedent_supprime(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / FICHIER_SORTIE)
        ecrire_collection(chemin, [_noeud("ancien")])
        _ecrire_jeu(tmp_path, [_coffret()], {MODULE_RACCORDEMENT: [_noeud("m1")]})
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(chemin)


# --------------------------------------------------------------------------- #
# Versions RecoStaR
# --------------------------------------------------------------------------- #


class TestVersions:
    """Le controle est agnostique de version : V1.0 et V1.1 se comportent pareil."""

    def test_champs_supplementaires_v1_1_sans_effet(self, tmp_path: Any) -> None:
        coffrets = [
            _coffret("cof1"),
            _coffret("cof2", proprietes={"Commentaire": "ajout V1.1"}),
        ]
        _ecrire_jeu(tmp_path, coffrets, {})
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_NOEUDS_INSUFFISANTS: 2}
