"""
Tests du controle E608 : type de jonction et nombre de cables raccordes.

Couvre :
  - les regles par type de jonction et le filtre de perimetre
  - la regle propre au type Telecom (cable de telecommunication requis)
  - l'extraction des references cables_href et du point de la jonction
  - l'indexation des extremites des trois couches de cable
  - la coincidence geometrique et sa tolerance d'un millimetre
  - la confrontation attributaire / geographique
  - le classement (compte insuffisant, excessif, incoherence)
  - la construction du GeoJSON d'ecarts
  - l'execution CLI
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from controle_e608 import (
    CHAMP_CABLES_HREF,
    CHAMP_STATUT,
    CHAMP_TYPE_JONCTION,
    COUCHE_CABLE_TELECOM,
    COUCHES_CABLE,
    EXTENSION,
    FICHIER_JONCTION,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    REGLES_PAR_TYPE,
    STATUT_CONTROLE,
    TOLERANCE_SUPERPOSITION,
    TYPE_CABLE_TELECOM_ABSENT,
    TYPE_CABLES_EXCESSIFS,
    TYPE_CABLES_INSUFFISANTS,
    TYPE_RACCORDEMENT_INCOHERENT,
    BilanRaccordement,
    RegleJonction,
    classifier_bilan,
    coincide,
    compter_jonctions_a_controler,
    compter_jonctions_non_conformes,
    construire_bilan,
    construire_geojson_ecarts,
    detecter_anomalies,
    detecter_coincidences_non_declarees,
    extraire_point,
    extraire_references,
    indexer_extremites_cables,
    regle_applicable,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

POINT: tuple[float, float] = (10.0, 20.0)
AILLEURS: tuple[float, float] = (99.0, 99.0)


def _jonction(
    identifiant: str = "j1",
    type_jonction: str = "Jonction",
    cables_href: Any = None,
    statut: str = STATUT_CONTROLE,
    coordonnees: list[float] | None = None,
) -> dict[str, Any]:
    """Feature GeoJSON Point representant une jonction."""
    return {
        "type": "Feature",
        "properties": {
            "id": identifiant,
            CHAMP_STATUT: statut,
            CHAMP_TYPE_JONCTION: type_jonction,
            CHAMP_CABLES_HREF: cables_href,
        },
        "geometry": {"type": "Point", "coordinates": list(coordonnees or [*POINT, 30.0])},
    }


def _cable(identifiant: str, depart: tuple[float, float], arrivee: tuple[float, float]) -> dict[str, Any]:
    """Feature GeoJSON LineString representant un cable."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "LineString", "coordinates": [list(depart), list(arrivee)]},
    }


def _extremites(*identifiants: str, coincidents: bool = True) -> dict[str, frozenset[tuple[float, float]]]:
    """Index {id_cable: extremites} dont les cables touchent, ou non, POINT."""
    bout = POINT if coincidents else AILLEURS
    return {i: frozenset({bout, (float(n), 0.0)}) for n, i in enumerate(identifiants, start=1)}


def _decale(ecart: float) -> tuple[float, float]:
    """Point ecarte de POINT d'une distance donnee, sur l'axe des X."""
    return (POINT[0] + ecart, POINT[1])


def _ecrire_jeu(tmp_path: Any, jonctions: list[dict[str, Any]], cables: list[dict[str, Any]]) -> None:
    ecrire_collection(str(tmp_path / FICHIER_JONCTION), jonctions)
    ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION}"), cables)


# --------------------------------------------------------------------------- #
# Regles de cardinalite et perimetre
# --------------------------------------------------------------------------- #


class TestReglesPartType:
    """Les seuils refletent la regle metier : c'est le contrat du controle."""

    def test_les_quatre_types_controles(self) -> None:
        assert set(REGLES_PAR_TYPE) == {"Derivation", "Jonction", "ExtremiteReseau", "Telecom"}

    def test_derivation_au_moins_trois(self) -> None:
        assert REGLES_PAR_TYPE["Derivation"] == RegleJonction(3, None)

    def test_jonction_au_moins_deux(self) -> None:
        assert REGLES_PAR_TYPE["Jonction"] == RegleJonction(2, None)

    def test_extremite_exactement_un(self) -> None:
        assert REGLES_PAR_TYPE["ExtremiteReseau"] == RegleJonction(1, 1)

    def test_telecom_exige_un_cable_telecom_sans_compte(self) -> None:
        """La contrainte porte sur la nature d'un cable, non sur leur nombre."""
        assert REGLES_PAR_TYPE["Telecom"] == RegleJonction(0, None, cable_telecom_requis=True)

    def test_seul_telecom_exige_un_cable_telecom(self) -> None:
        exigeants = {t for t, r in REGLES_PAR_TYPE.items() if r.cable_telecom_requis}
        assert exigeants == {"Telecom"}


class TestRegleApplicable:
    """Tests du filtre de perimetre."""

    def test_type_controle(self) -> None:
        assert regle_applicable(_jonction()["properties"]) == RegleJonction(2, None)

    def test_type_telecom_controle(self) -> None:
        regle = regle_applicable(_jonction(type_jonction="Telecom")["properties"])
        assert regle is not None and regle.cable_telecom_requis is True

    def test_autre_statut_ignore(self) -> None:
        assert regle_applicable(_jonction(statut="Functional")["properties"]) is None

    def test_remontee_aero_souterraine_ignoree(self) -> None:
        """Seuls les trois types declares sont controles."""
        assert regle_applicable(_jonction(type_jonction="RemonteeAeroSouterraine")["properties"]) is None

    def test_type_absent_ignore(self) -> None:
        assert regle_applicable({CHAMP_STATUT: STATUT_CONTROLE}) is None

    def test_type_non_textuel_ignore(self) -> None:
        assert regle_applicable({CHAMP_STATUT: STATUT_CONTROLE, CHAMP_TYPE_JONCTION: 3}) is None


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


class TestExtraireReferences:
    """Tests de extraire_references."""

    def test_separateur_virgule(self) -> None:
        assert extraire_references({CHAMP_CABLES_HREF: "c1,c2,c3"}) == frozenset({"c1", "c2", "c3"})

    def test_separateur_espace(self) -> None:
        assert extraire_references({CHAMP_CABLES_HREF: "c1 c2"}) == frozenset({"c1", "c2"})

    def test_reference_unique(self) -> None:
        assert extraire_references({CHAMP_CABLES_HREF: "c1"}) == frozenset({"c1"})

    def test_champ_absent(self) -> None:
        assert extraire_references({}) == frozenset()

    def test_champ_nul(self) -> None:
        assert extraire_references({CHAMP_CABLES_HREF: None}) == frozenset()

    def test_champ_vide(self) -> None:
        assert extraire_references({CHAMP_CABLES_HREF: "  ,  "}) == frozenset()

    def test_doublons_dedupliques(self) -> None:
        assert extraire_references({CHAMP_CABLES_HREF: "c1,c1"}) == frozenset({"c1"})


class TestExtrairePoint:
    """Tests de extraire_point."""

    def test_point_3d(self) -> None:
        assert extraire_point({"type": "Point", "coordinates": [1.0, 2.0, 3.0]}) == (1.0, 2.0)

    def test_point_2d(self) -> None:
        assert extraire_point({"type": "Point", "coordinates": [1.0, 2.0]}) == (1.0, 2.0)

    def test_geometrie_nulle(self) -> None:
        assert extraire_point(None) is None

    def test_autre_type(self) -> None:
        assert extraire_point({"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}) is None

    def test_coordonnees_insuffisantes(self) -> None:
        assert extraire_point({"type": "Point", "coordinates": [1.0]}) is None


class TestIndexerExtremitesCables:
    """Tests de indexer_extremites_cables."""

    def test_index_multi_couches(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION}"), [_cable("c1", POINT, (0.0, 0.0))])
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[1]}{EXTENSION}"), [_cable("c2", POINT, (1.0, 1.0))])
        index, telecom, absentes = indexer_extremites_cables(str(tmp_path))
        assert set(index) == {"c1", "c2"}
        assert POINT in index["c1"]
        assert telecom == frozenset()
        assert absentes == [COUCHES_CABLE[2]]

    def test_cables_telecom_isoles(self, tmp_path: Any) -> None:
        """La regle du type Telecom porte sur la nature, que l'index ne garde pas."""
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION}"), [_cable("c1", POINT, (0.0, 0.0))])
        ecrire_collection(str(tmp_path / f"{COUCHE_CABLE_TELECOM}{EXTENSION}"), [_cable("t1", POINT, (1.0, 1.0))])
        index, telecom, _ = indexer_extremites_cables(str(tmp_path))
        assert set(index) == {"c1", "t1"}
        assert telecom == frozenset({"t1"})

    def test_cable_sans_identifiant_ecarte(self, tmp_path: Any) -> None:
        cable = _cable("c1", POINT, (0.0, 0.0))
        cable["properties"].pop("id")
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION}"), [cable])
        index, _, _ = indexer_extremites_cables(str(tmp_path))
        assert index == {}

    def test_multilinestring_duplique_sans_extremite(self, tmp_path: Any) -> None:
        """Cas reel Echantillon2 : deux parties identiques neutralisent les bouts."""
        cable = {
            "type": "Feature",
            "properties": {"id": "c1"},
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [[[0.0, 0.0], [1.0, 0.0]], [[0.0, 0.0], [1.0, 0.0]]],
            },
        }
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION}"), [cable])
        index, _, _ = indexer_extremites_cables(str(tmp_path))
        assert index["c1"] == frozenset()

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        index, telecom, absentes = indexer_extremites_cables(str(tmp_path))
        assert index == {}
        assert telecom == frozenset()
        assert absentes == list(COUCHES_CABLE)


# --------------------------------------------------------------------------- #
# Confrontation attributaire / geographique
# --------------------------------------------------------------------------- #


class TestCoincide:
    """Tests de coincide : coincidence planimetrique a la tolerance pres."""

    def test_coincidence_exacte(self) -> None:
        assert coincide(POINT, frozenset({POINT})) is True

    def test_ecart_inferieur_a_la_tolerance(self) -> None:
        """Un demi-millimetre reste un contact : les coordonnees sont arrondies au mm."""
        assert coincide(POINT, frozenset({_decale(0.0005)})) is True

    def test_ecart_egal_a_la_tolerance(self) -> None:
        """Le seuil est inclusif : un ecart d'exactement 1 mm est un contact."""
        assert coincide(POINT, frozenset({_decale(TOLERANCE_SUPERPOSITION)})) is True

    def test_ecart_superieur_a_la_tolerance(self) -> None:
        assert coincide(POINT, frozenset({_decale(0.002)})) is False

    def test_ecart_centimetrique_detecte(self) -> None:
        """La tolerance reste tres en deca de toute precision de leve."""
        assert coincide(POINT, frozenset({_decale(0.01)})) is False

    def test_plusieurs_extremites_une_seule_proche(self) -> None:
        assert coincide(POINT, frozenset({AILLEURS, _decale(0.0008)})) is True

    def test_sans_extremite(self) -> None:
        assert coincide(POINT, frozenset()) is False

    def test_tolerance_partagee_avec_le_module_commun(self) -> None:
        """La valeur n'est pas propre a E608 : E205, E208 et E209 l'appliquent aussi."""
        from utils_geometrie_commun import TOLERANCE_SUPERPOSITION as TOLERANCE_COMMUNE

        assert TOLERANCE_SUPERPOSITION is TOLERANCE_COMMUNE
        assert TOLERANCE_SUPERPOSITION == 0.001


class TestConstruireBilan:
    """Tests de construire_bilan."""

    def test_raccordement_confirme_des_deux_cotes(self) -> None:
        bilan = construire_bilan(POINT, frozenset({"c1", "c2"}), _extremites("c1", "c2"))
        assert bilan.raccordes == frozenset({"c1", "c2"})
        assert bilan.est_coherent is True

    def test_reference_sans_coincidence(self) -> None:
        """Un cable declare mais geographiquement ailleurs n'est pas raccorde."""
        bilan = construire_bilan(POINT, frozenset({"c1"}), _extremites("c1", coincidents=False))
        assert bilan.raccordes == frozenset()
        assert bilan.references_sans_coincidence == frozenset({"c1"})
        assert bilan.est_coherent is False

    def test_extremite_dans_la_tolerance_raccordee(self) -> None:
        """Un ecart submillimetrique d'arrondi ne rompt pas le raccordement."""
        bilan = construire_bilan(POINT, frozenset({"c1"}), {"c1": frozenset({_decale(0.0004)})})
        assert bilan.raccordes == frozenset({"c1"})

    def test_extremite_hors_tolerance_non_raccordee(self) -> None:
        bilan = construire_bilan(POINT, frozenset({"c1"}), {"c1": frozenset({_decale(0.05)})})
        assert bilan.raccordes == frozenset()

    def test_reference_non_resolue(self) -> None:
        bilan = construire_bilan(POINT, frozenset({"c9"}), _extremites("c1"))
        assert bilan.references_non_resolues == frozenset({"c9"})
        assert bilan.raccordes == frozenset()

    def test_cable_sans_extremite_non_raccorde(self) -> None:
        """Un cable dont les extremites sont indeterminables n'est pas confirmable."""
        bilan = construire_bilan(POINT, frozenset({"c1"}), {"c1": frozenset()})
        assert bilan.sans_extremite == frozenset({"c1"})
        assert bilan.raccordes == frozenset()

    def test_jonction_sans_point(self) -> None:
        bilan = construire_bilan(None, frozenset({"c1"}), _extremites("c1"))
        assert bilan.geographiques == frozenset()
        assert bilan.raccordes == frozenset()

    def test_aucune_reference(self) -> None:
        bilan = construire_bilan(POINT, frozenset(), _extremites("c1"))
        assert bilan.raccordes == frozenset()
        assert bilan.est_coherent is True

    def test_references_telecom_isolees(self) -> None:
        bilan = construire_bilan(POINT, frozenset({"c1", "t1"}), _extremites("c1", "t1"), frozenset({"t1"}))
        assert bilan.references_telecom == frozenset({"t1"})

    def test_reference_telecom_non_declaree_absente_du_bilan(self) -> None:
        bilan = construire_bilan(POINT, frozenset({"c1"}), _extremites("c1", "t1"), frozenset({"t1"}))
        assert bilan.references_telecom == frozenset()


class TestDetecterCoincidencesNonDeclarees:
    """Tests de detecter_coincidences_non_declarees."""

    def test_cable_coincidant_non_declare(self) -> None:
        trouves = detecter_coincidences_non_declarees(POINT, frozenset({"c1"}), _extremites("c1", "c2"))
        assert trouves == frozenset({"c2"})

    def test_aucun_cable_non_declare(self) -> None:
        assert detecter_coincidences_non_declarees(POINT, frozenset({"c1"}), _extremites("c1")) == frozenset()

    def test_cable_eloigne_ignore(self) -> None:
        index = {**_extremites("c1"), **{"c2": frozenset({AILLEURS})}}
        assert detecter_coincidences_non_declarees(POINT, frozenset({"c1"}), index) == frozenset()

    def test_tolerance_appliquee(self) -> None:
        index = {"c1": frozenset({POINT}), "c2": frozenset({_decale(0.0007)})}
        assert detecter_coincidences_non_declarees(POINT, frozenset({"c1"}), index) == frozenset({"c2"})

    def test_jonction_sans_point(self) -> None:
        assert detecter_coincidences_non_declarees(None, frozenset(), _extremites("c1")) == frozenset()


# --------------------------------------------------------------------------- #
# Classement
# --------------------------------------------------------------------------- #


def _bilan(nb_raccordes: int, coherent: bool = True, telecom: bool = False) -> BilanRaccordement:
    """Bilan synthetique portant `nb_raccordes` cables confirmes."""
    raccordes = frozenset(f"c{n}" for n in range(nb_raccordes))
    sans_coincidence = frozenset() if coherent else frozenset({"cx"})
    return BilanRaccordement(
        references=raccordes | sans_coincidence,
        geographiques=raccordes,
        raccordes=raccordes,
        references_non_resolues=frozenset(),
        sans_extremite=frozenset(),
        references_telecom=frozenset({"t1"}) if telecom else frozenset(),
    )


class TestClassifierBilan:
    """Tests de classifier_bilan (fonction pure)."""

    def test_derivation_conforme(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Derivation"], _bilan(3)) == []

    def test_derivation_insuffisante(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Derivation"], _bilan(2)) == [TYPE_CABLES_INSUFFISANTS]

    def test_derivation_sans_plafond(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Derivation"], _bilan(9)) == []

    def test_jonction_conforme(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Jonction"], _bilan(2)) == []

    def test_jonction_insuffisante(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Jonction"], _bilan(1)) == [TYPE_CABLES_INSUFFISANTS]

    def test_extremite_conforme(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["ExtremiteReseau"], _bilan(1)) == []

    def test_extremite_sans_cable(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["ExtremiteReseau"], _bilan(0)) == [TYPE_CABLES_INSUFFISANTS]

    def test_extremite_excessive(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["ExtremiteReseau"], _bilan(2)) == [TYPE_CABLES_EXCESSIFS]

    def test_telecom_avec_cable_telecom(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Telecom"], _bilan(1, telecom=True)) == []

    def test_telecom_sans_cable_telecom(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Telecom"], _bilan(2)) == [TYPE_CABLE_TELECOM_ABSENT]

    def test_telecom_sans_aucun_cable(self) -> None:
        """Aucun compte n'est impose : seule la nature manque."""
        assert classifier_bilan(REGLES_PAR_TYPE["Telecom"], _bilan(0)) == [TYPE_CABLE_TELECOM_ABSENT]

    def test_autres_types_n_exigent_pas_de_telecom(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Jonction"], _bilan(2)) == []

    def test_telecom_et_incoherence_cumulent(self) -> None:
        codes = classifier_bilan(REGLES_PAR_TYPE["Telecom"], _bilan(1, coherent=False))
        assert codes == [TYPE_CABLE_TELECOM_ABSENT, TYPE_RACCORDEMENT_INCOHERENT]

    def test_incoherence_seule(self) -> None:
        """Le bon nombre de raccordements n'excuse pas une declaration fautive."""
        assert classifier_bilan(REGLES_PAR_TYPE["Jonction"], _bilan(2, coherent=False)) == [
            TYPE_RACCORDEMENT_INCOHERENT
        ]

    def test_compte_et_incoherence_cumulent(self) -> None:
        codes = classifier_bilan(REGLES_PAR_TYPE["Jonction"], _bilan(1, coherent=False))
        assert codes == [TYPE_CABLES_INSUFFISANTS, TYPE_RACCORDEMENT_INCOHERENT]


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_jonction_conforme(self) -> None:
        jonction = _jonction(cables_href="c1,c2")
        assert detecter_anomalies([jonction], _extremites("c1", "c2")) == []

    def test_hors_perimetre_ignore(self) -> None:
        jonctions = [
            _jonction("j1", statut="Projected"),
            _jonction("j2", type_jonction="RemonteeAeroSouterraine"),
        ]
        assert detecter_anomalies(jonctions, _extremites("c1")) == []

    def test_anomalie_documentee(self) -> None:
        jonction = _jonction(cables_href="c1")
        anomalies = detecter_anomalies([jonction], _extremites("c1"))
        assert len(anomalies) == 1
        anomalie = anomalies[0]
        assert anomalie["type_anomalie"] == TYPE_CABLES_INSUFFISANTS
        assert anomalie["type_jonction"] == "Jonction"
        assert anomalie["nombre_minimum"] == 2
        assert anomalie["nombre_maximum"] is None
        assert anomalie["nombre_cables_raccordes"] == 1
        assert anomalie["geometrie"]["type"] == "Point"

    def test_coincidence_non_declaree_signalee(self) -> None:
        """Un cable geographiquement raccorde mais non declare est une incoherence."""
        jonction = _jonction(cables_href="c1,c2")
        index = {**_extremites("c1", "c2"), **{"c3": frozenset({POINT})}}
        anomalies = detecter_anomalies([jonction], index)
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_RACCORDEMENT_INCOHERENT]
        assert anomalies[0]["nombre_coincidences_non_declarees"] == 1

    def test_deux_anomalies_pour_une_jonction(self) -> None:
        jonction = _jonction(cables_href="c1")
        anomalies = detecter_anomalies([jonction], _extremites("c1", coincidents=False))
        assert [a["type_anomalie"] for a in anomalies] == [
            TYPE_CABLES_INSUFFISANTS,
            TYPE_RACCORDEMENT_INCOHERENT,
        ]

    def test_comptes_du_diagnostic(self) -> None:
        jonction = _jonction(type_jonction="Derivation", cables_href="c1,c2,c9")
        index = {"c1": frozenset({POINT, (1.0, 0.0)}), "c2": frozenset()}
        anomalie = detecter_anomalies([jonction], index)[0]
        assert anomalie["nombre_references"] == 2
        assert anomalie["nombre_references_non_resolues"] == 1
        assert anomalie["nombre_cables_sans_extremite"] == 1
        assert anomalie["nombre_cables_raccordes"] == 1

    def test_plusieurs_jonctions(self) -> None:
        jonctions = [_jonction("j1", cables_href="c1,c2"), _jonction("j2", cables_href="c1")]
        anomalies = detecter_anomalies(jonctions, _extremites("c1", "c2"))
        assert {a["id_jonction"] for a in anomalies} == {"j2"}


class TestComptages:
    """Tests des comptages du rapport."""

    def test_jonctions_a_controler(self) -> None:
        jonctions = [
            _jonction("j1", type_jonction="Derivation"),
            _jonction("j2", type_jonction="ExtremiteReseau"),
            _jonction("j3", type_jonction="RemonteeAeroSouterraine"),
            _jonction("j4", statut="Projected"),
        ]
        assert compter_jonctions_a_controler(jonctions) == 2

    def test_jonctions_a_controler_liste_vide(self) -> None:
        assert compter_jonctions_a_controler([]) == 0

    def test_jonctions_non_conformes_dedoublonnees(self) -> None:
        anomalies = [{"id_jonction": "j1"}, {"id_jonction": "j1"}, {"id_jonction": "j2"}]
        assert compter_jonctions_non_conformes(anomalies) == 2

    def test_jonctions_non_conformes_liste_vide(self) -> None:
        assert compter_jonctions_non_conformes([]) == 0


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_CABLES_INSUFFISANTS,
            "id_jonction": "j1",
            "type_jonction": "Derivation",
            "nombre_minimum": 3,
            "nombre_maximum": None,
            "nombre_cables_raccordes": 2,
            "nombre_references": 3,
            "nombre_geographiques": 2,
            "nombre_references_sans_coincidence": 1,
            "nombre_coincidences_non_declarees": 0,
            "nombre_references_non_resolues": 0,
            "nombre_cables_sans_extremite": 0,
            "nombre_cables_telecommunication": 0,
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }

    def test_socle_commun(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["code_controle"] == "E608"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_entite"] == "j1"
        assert props["type_anomalie"] == TYPE_CABLES_INSUFFISANTS
        assert props["description"]

    def test_comptes_des_deux_sources_exposes(self) -> None:
        """C'est leur confrontation qui explique l'ecart."""
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["nombre_references"] == 3
        assert props["nombre_geographiques"] == 2
        assert props["nombre_cables_raccordes"] == 2
        assert props["nombre_references_sans_coincidence"] == 1

    def test_seuils_exposes(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["nombre_minimum"] == 3
        assert props["nombre_maximum"] is None

    def test_description_par_type(self) -> None:
        for type_anomalie in (
            TYPE_CABLES_INSUFFISANTS,
            TYPE_CABLES_EXCESSIFS,
            TYPE_RACCORDEMENT_INCOHERENT,
            TYPE_CABLE_TELECOM_ABSENT,
        ):
            anomalie = {**self._anomalie(), "type_anomalie": type_anomalie}
            props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
            assert props["description"] != type_anomalie, type_anomalie

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

    def test_repertoire_inexistant(self) -> None:
        from controle_e608 import executer_controle_cli

        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichiers_absents_non_bloquants(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_jonction_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_nominal_conforme(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_jonctions_controlees"] == 1
        assert resultat["nombre_cables_indexes"] == 2
        assert resultat["priorite"] == "majeur"

    def test_derivation_insuffisante(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(type_jonction="Derivation", cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_CABLES_INSUFFISANTS: 1}

    def test_extremite_excessive(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(type_jonction="ExtremiteReseau", cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_CABLES_EXCESSIFS: 1}

    def test_reference_sans_coincidence_geographique(self, tmp_path: Any) -> None:
        """Une declaration cables_href sans réalité géométrique ne compte pas."""
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", AILLEURS, (1.0, 1.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {
            TYPE_CABLES_INSUFFISANTS: 1,
            TYPE_RACCORDEMENT_INCOHERENT: 1,
        }

    def test_coincidence_non_declaree(self, tmp_path: Any) -> None:
        """Un cable geographiquement raccorde mais absent de cables_href."""
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [
                _cable("c1", POINT, (0.0, 0.0)),
                _cable("c2", POINT, (1.0, 1.0)),
                _cable("c3", POINT, (2.0, 2.0)),
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_RACCORDEMENT_INCOHERENT: 1}

    def test_cable_decale_dans_la_tolerance_conforme(self, tmp_path: Any) -> None:
        """Deux cables a moins d'un millimetre suffisent a une Jonction."""
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", _decale(0.0006), (0.0, 0.0)), _cable("c2", _decale(0.0009), (1.0, 1.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0

    def test_cable_decale_hors_tolerance_signale(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", _decale(0.02), (1.0, 1.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {
            TYPE_CABLES_INSUFFISANTS: 1,
            TYPE_RACCORDEMENT_INCOHERENT: 1,
        }

    def test_telecom_conforme(self, tmp_path: Any) -> None:
        """Une jonction Telecom declarant un cable de telecommunication."""
        from controle_e608 import executer_controle_cli

        ecrire_collection(str(tmp_path / FICHIER_JONCTION), [_jonction(type_jonction="Telecom", cables_href="t1")])
        ecrire_collection(str(tmp_path / f"{COUCHE_CABLE_TELECOM}{EXTENSION}"), [_cable("t1", POINT, (0.0, 0.0))])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_telecommunication"] == 1

    def test_telecom_sans_cable_telecom_signalee(self, tmp_path: Any) -> None:
        """Un cable electrique ne satisfait pas la regle du type Telecom."""
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(type_jonction="Telecom", cables_href="c1")],
            [_cable("c1", POINT, (0.0, 0.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_CABLE_TELECOM_ABSENT: 1}

    def test_telecom_sans_cables_href_signalee(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(tmp_path, [_jonction(type_jonction="Telecom", cables_href=None)], [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_CABLE_TELECOM_ABSENT: 1}

    def test_tolerance_reportee_au_rapport(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", POINT, (0.0, 0.0))])
        assert executer_controle_cli(str(tmp_path))["tolerance_coincidence_m"] == TOLERANCE_SUPERPOSITION

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", POINT, (0.0, 0.0))])
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_crs_propage(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        ecrire_collection_avec_crs(str(tmp_path / FICHIER_JONCTION), [_jonction(cables_href="c1")], "EPSG:2154")
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION}"), [_cable("c1", POINT, (0.0, 0.0))])
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert "2154" in ecarts["crs"]["properties"]["name"]

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", POINT, (0.0, 0.0))])
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "anomalies_par_type",
            "nombre_jonctions_analysees",
            "nombre_jonctions_controlees",
            "nombre_jonctions_non_conformes",
            "nombre_cables_indexes",
            "nombre_cables_sans_extremite",
            "nombre_cables_telecommunication",
            "tolerance_coincidence_m",
            "fichier_jonction_absent",
            "couches_cable_absentes",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Le raccordement est controle identiquement en V1.0 et V1.1."""

    def test_v11_champs_extra_sans_effet(self, tmp_path: Any) -> None:
        from controle_e608 import executer_controle_cli

        jonction = _jonction(cables_href="c1,c2")
        jonction["properties"]["Commentaire"] = "note"
        _ecrire_jeu(tmp_path, [jonction], [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
