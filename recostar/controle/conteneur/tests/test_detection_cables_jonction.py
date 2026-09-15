"""
Tests du moteur de raccordement des jonctions et des deux controles qu'il sert.

Le moteur `detection_cables_jonction` rend la cardinalite (nombre de cables
raccordes a
une jonction) et E-9502 (la jonction n'est pas posee sur une extremite du
cable). Les deux reposent sur la meme coincidence geometrique, evaluee une seule
fois et a une seule tolerance : c'est l'objet de leur reunion.

Couvre :
  - les regles par type de jonction et le filtre de perimetre du compte
  - la regle propre au type Telecom (cable de telecommunication requis)
  - l'extraction des references cables_href et du point de la jonction
  - l'indexation des trois couches de cable et de leurs sous-ensembles
  - la coincidence geometrique et sa tolerance d'un millimetre
  - la confrontation attributaire / geographique
  - le classement (compte insuffisant, excessif, incoherence)
  - les liens hors extremite et leur perimetre propre
  - la repartition des types entre les deux controles
  - la construction des deux formes de GeoJSON d'ecarts
  - l'execution CLI de chacun des deux controles
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from recostar.controle.cable.e9502 import FICHIER_SORTIE as FICHIER_SORTIE_9502
from recostar.controle.cable.e9502 import PROFIL_ECARTS as PROFIL_ECARTS_9502
from recostar.controle.cable.e9502 import TYPES_RETENUS as TYPES_RETENUS_9502
from recostar.controle.conteneur.detection_cables_jonction import (
    COUCHES_CABLE,
    REGLES_PAR_TYPE,
    STATUT_CONTROLE,
    TOLERANCE_SUPERPOSITION,
    TYPE_CABLE_TELECOM_ABSENT,
    TYPE_DERIVATION_INSUFFISANTE,
    TYPE_EXTREMITE_CABLES_MULTIPLES,
    TYPE_EXTREMITE_SANS_CABLE,
    TYPE_JONCTION_HORS_EXTREMITE,
    TYPE_JONCTION_INSUFFISANTE,
    TYPE_RACCORDEMENT_INCOHERENT,
    BilanRaccordement,
    IndexCables,
    RegleJonction,
    classifier_bilan,
    coincide,
    compter_jonctions_a_controler,
    compter_jonctions_non_conformes,
    construire_bilan,
    construire_geojson_ecarts,
    detecter_anomalies,
    detecter_coincidences_non_declarees,
    distance_extremite_plus_proche,
    extraire_references,
    indexer_cables,
    liens_hors_extremite,
    regle_applicable,
)
from recostar.controle.conteneur.e6116 import TYPES_RETENUS as TYPES_RETENUS_6116
from recostar.controle.conteneur.e6201 import TYPES_RETENUS as TYPES_RETENUS_6201
from recostar.controle.conteneur.e6202 import FICHIER_SORTIE
from recostar.controle.conteneur.e6202 import PROFIL_ECARTS as PROFIL_ECARTS_6202
from recostar.controle.conteneur.e6202 import TYPES_RETENUS as TYPES_RETENUS_6202
from recostar.controle.conteneur.e6203 import TYPES_RETENUS as TYPES_RETENUS_6203
from recostar.controle.conteneur.e9609 import TYPES_RETENUS as TYPES_RETENUS_9609
from recostar.controle.conteneur.tests.utils_tests import ecrire_collection, ecrire_collection_avec_crs
from recostar.controle.fonctions_communes.geojson import PRIORITE_MOYENNE
from recostar.controle.fonctions_communes.geometrie import extraire_point_xy
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CABLES_HREF,
    CHAMP_STATUT,
    CHAMP_TYPE_JONCTION,
    COUCHE_CABLE_ELECTRIQUE,
    COUCHE_CABLE_TELECOM,
    EXTENSION_COUCHE,
    FICHIER_JONCTION,
    STATUT_MISE_EN_SERVICE,
)

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


def _cable(
    identifiant: str,
    depart: tuple[float, float],
    arrivee: tuple[float, float],
    statut: str = STATUT_MISE_EN_SERVICE,
) -> dict[str, Any]:
    """Feature GeoJSON LineString representant un cable.

    Le Statut n'entre que dans le perimetre d'E-9502, qui ne juge la coincidence
    que sur les cables electriques en cours de mise en service.
    """
    return {
        "type": "Feature",
        "properties": {"id": identifiant, CHAMP_STATUT: statut},
        "geometry": {"type": "LineString", "coordinates": [list(depart), list(arrivee)]},
    }


def _extremites(*identifiants: str, coincidents: bool = True) -> dict[str, frozenset[tuple[float, float]]]:
    """Index {id_cable: extremites} dont les cables touchent, ou non, POINT."""
    bout = POINT if coincidents else AILLEURS
    return {i: frozenset({bout, (float(n), 0.0)}) for n, i in enumerate(identifiants, start=1)}


def _index(
    extremites: dict[str, frozenset[tuple[float, float]]],
    telecom: frozenset[str] = frozenset(),
    electriques: frozenset[str] | None = None,
) -> IndexCables:
    """IndexCables de test : tous les cables sont electriques et controles.

    C'est le cas courant des jeux d'essai ; `electriques` permet de restreindre
    le perimetre d'E-9502 quand c'est lui que le test met en cause.
    """
    return IndexCables(
        extremites,
        telecom,
        frozenset(extremites) - telecom if electriques is None else electriques,
        (),
    )


def _decale(ecart: float) -> tuple[float, float]:
    """Point ecarte de POINT d'une distance donnee, sur l'axe des X."""
    return (POINT[0] + ecart, POINT[1])


def _ecrire_jeu(tmp_path: Any, jonctions: list[dict[str, Any]], cables: list[dict[str, Any]]) -> None:
    ecrire_collection(str(tmp_path / FICHIER_JONCTION), jonctions)
    ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION_COUCHE}"), cables)


# --------------------------------------------------------------------------- #
# Regles de cardinalite et perimetre
# --------------------------------------------------------------------------- #


class TestReglesPartType:
    """Les seuils refletent la regle metier : c'est le contrat du controle."""

    def test_les_quatre_types_controles(self) -> None:
        assert set(REGLES_PAR_TYPE) == {"Derivation", "Jonction", "ExtremiteReseau", "Telecom"}

    def test_derivation_au_moins_trois(self) -> None:
        assert REGLES_PAR_TYPE["Derivation"] == RegleJonction(3, None, TYPE_DERIVATION_INSUFFISANTE)

    def test_jonction_au_moins_deux(self) -> None:
        assert REGLES_PAR_TYPE["Jonction"] == RegleJonction(2, None, TYPE_JONCTION_INSUFFISANTE)

    def test_extremite_exactement_un(self) -> None:
        assert REGLES_PAR_TYPE["ExtremiteReseau"] == RegleJonction(
            1, 1, TYPE_EXTREMITE_SANS_CABLE, TYPE_EXTREMITE_CABLES_MULTIPLES
        )

    def test_telecom_exige_un_cable_telecom_sans_compte(self) -> None:
        """La contrainte porte sur la nature d'un cable, non sur leur nombre."""
        assert REGLES_PAR_TYPE["Telecom"] == RegleJonction(0, None, cable_telecom_requis=True)

    def test_seul_telecom_exige_un_cable_telecom(self) -> None:
        exigeants = {t for t, r in REGLES_PAR_TYPE.items() if r.cable_telecom_requis}
        assert exigeants == {"Telecom"}


class TestRegleApplicable:
    """Tests du filtre de perimetre."""

    def test_type_controle(self) -> None:
        assert regle_applicable(_jonction()["properties"]) == RegleJonction(2, None, TYPE_JONCTION_INSUFFISANTE)

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
        assert extraire_point_xy({"type": "Point", "coordinates": [1.0, 2.0, 3.0]}) == (1.0, 2.0)

    def test_point_2d(self) -> None:
        assert extraire_point_xy({"type": "Point", "coordinates": [1.0, 2.0]}) == (1.0, 2.0)

    def test_geometrie_nulle(self) -> None:
        assert extraire_point_xy(None) is None

    def test_autre_type(self) -> None:
        assert extraire_point_xy({"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}) is None

    def test_coordonnees_insuffisantes(self) -> None:
        assert extraire_point_xy({"type": "Point", "coordinates": [1.0]}) is None


class TestIndexerCables:
    """Tests de indexer_cables."""

    def test_index_multi_couches(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION_COUCHE}"), [_cable("c1", POINT, (0.0, 0.0))])
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[1]}{EXTENSION_COUCHE}"), [_cable("c2", POINT, (1.0, 1.0))])
        index = indexer_cables(str(tmp_path))
        assert set(index.extremites) == {"c1", "c2"}
        assert POINT in index.extremites["c1"]
        assert index.telecom == frozenset()
        assert index.couches_absentes == (COUCHES_CABLE[2],)

    def test_cables_telecom_isoles(self, tmp_path: Any) -> None:
        """La regle du type Telecom porte sur la nature, que l'index ne garde pas."""
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION_COUCHE}"), [_cable("c1", POINT, (0.0, 0.0))])
        ecrire_collection(
            str(tmp_path / f"{COUCHE_CABLE_TELECOM}{EXTENSION_COUCHE}"), [_cable("t1", POINT, (1.0, 1.0))]
        )
        index = indexer_cables(str(tmp_path))
        assert set(index.extremites) == {"c1", "t1"}
        assert index.telecom == frozenset({"t1"})

    def test_cables_electriques_controles_isoles(self, tmp_path: Any) -> None:
        """Perimetre d'E-9502 : couche electrique et statut de mise en service."""
        ecrire_collection(
            str(tmp_path / f"{COUCHE_CABLE_ELECTRIQUE}{EXTENSION_COUCHE}"),
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0), statut="Projected")],
        )
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[1]}{EXTENSION_COUCHE}"), [_cable("t1", POINT, (2.0, 2.0))])
        index = indexer_cables(str(tmp_path))
        assert index.electriques_controles == frozenset({"c1"})

    def test_cable_sans_identifiant_ecarte(self, tmp_path: Any) -> None:
        cable = _cable("c1", POINT, (0.0, 0.0))
        cable["properties"].pop("id")
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION_COUCHE}"), [cable])
        assert indexer_cables(str(tmp_path)).extremites == {}

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
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION_COUCHE}"), [cable])
        assert indexer_cables(str(tmp_path)).extremites["c1"] == frozenset()

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        index = indexer_cables(str(tmp_path))
        assert index.extremites == {}
        assert index.telecom == frozenset()
        assert index.electriques_controles == frozenset()
        assert index.couches_absentes == COUCHES_CABLE


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
        """La valeur n'est pas propre a ce moteur : les controles d'altimetrie
        l'appliquent aussi."""
        from recostar.controle.fonctions_communes.geometrie import TOLERANCE_SUPERPOSITION as TOLERANCE_COMMUNE

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
        assert classifier_bilan(REGLES_PAR_TYPE["Derivation"], _bilan(2)) == [TYPE_DERIVATION_INSUFFISANTE]

    def test_derivation_sans_plafond(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Derivation"], _bilan(9)) == []

    def test_jonction_conforme(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Jonction"], _bilan(2)) == []

    def test_jonction_insuffisante(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["Jonction"], _bilan(1)) == [TYPE_JONCTION_INSUFFISANTE]

    def test_extremite_conforme(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["ExtremiteReseau"], _bilan(1)) == []

    def test_extremite_sans_cable(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["ExtremiteReseau"], _bilan(0)) == [TYPE_EXTREMITE_SANS_CABLE]

    def test_extremite_excessive(self) -> None:
        assert classifier_bilan(REGLES_PAR_TYPE["ExtremiteReseau"], _bilan(2)) == [TYPE_EXTREMITE_CABLES_MULTIPLES]

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
        assert codes == [TYPE_JONCTION_INSUFFISANTE, TYPE_RACCORDEMENT_INCOHERENT]


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_jonction_conforme(self) -> None:
        jonction = _jonction(cables_href="c1,c2")
        assert detecter_anomalies([jonction], _index(_extremites("c1", "c2"))) == []

    def test_hors_perimetre_du_compte_ignore(self) -> None:
        """Sans cables_href, aucune des deux regles n'a de prise."""
        jonctions = [
            _jonction("j1", statut="Projected"),
            _jonction("j2", type_jonction="RemonteeAeroSouterraine"),
        ]
        assert detecter_anomalies(jonctions, _index(_extremites("c1"))) == []

    def test_anomalie_documentee(self) -> None:
        jonction = _jonction(cables_href="c1")
        anomalies = detecter_anomalies([jonction], _index(_extremites("c1")))
        assert len(anomalies) == 1
        anomalie = anomalies[0]
        assert anomalie["type_anomalie"] == TYPE_JONCTION_INSUFFISANTE
        assert anomalie["type_jonction"] == "Jonction"
        assert anomalie["nombre_minimum"] == 2
        assert anomalie["nombre_maximum"] is None
        assert anomalie["nombre_cables_raccordes"] == 1
        assert anomalie["geometrie"]["type"] == "Point"

    def test_coincidence_non_declaree_signalee(self) -> None:
        """Un cable geographiquement raccorde mais non declare est une incoherence."""
        jonction = _jonction(cables_href="c1,c2")
        index = {**_extremites("c1", "c2"), **{"c3": frozenset({POINT})}}
        anomalies = detecter_anomalies([jonction], _index(index))
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_RACCORDEMENT_INCOHERENT]
        assert anomalies[0]["nombre_coincidences_non_declarees"] == 1

    def test_plusieurs_anomalies_pour_une_jonction(self) -> None:
        """Un cable declare sans coincidence tient les trois constats a la fois.

        Le lien fautif (E-9502), le compte qu'il fait manquer et l'incoherence
        entre declaration et geometrie (E-9609) sont trois lectures d'un meme
        defaut : le moteur les emet ensemble, chaque controle ne retenant que
        les siens.
        """
        jonction = _jonction(cables_href="c1")
        anomalies = detecter_anomalies([jonction], _index(_extremites("c1", coincidents=False)))
        assert [a["type_anomalie"] for a in anomalies] == [
            TYPE_JONCTION_HORS_EXTREMITE,
            TYPE_JONCTION_INSUFFISANTE,
            TYPE_RACCORDEMENT_INCOHERENT,
        ]

    def test_comptes_du_diagnostic(self) -> None:
        jonction = _jonction(type_jonction="Derivation", cables_href="c1,c2,c9")
        index = {"c1": frozenset({POINT, (1.0, 0.0)}), "c2": frozenset()}
        anomalie = detecter_anomalies([jonction], _index(index))[0]
        assert anomalie["nombre_references"] == 2
        assert anomalie["nombre_references_non_resolues"] == 1
        assert anomalie["nombre_cables_sans_extremite"] == 1
        assert anomalie["nombre_cables_raccordes"] == 1

    def test_plusieurs_jonctions(self) -> None:
        jonctions = [_jonction("j1", cables_href="c1,c2"), _jonction("j2", cables_href="c1")]
        anomalies = detecter_anomalies(jonctions, _index(_extremites("c1", "c2")))
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
            "type_anomalie": TYPE_JONCTION_INSUFFISANTE,
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
        props = construire_geojson_ecarts([self._anomalie()], PROFIL_ECARTS_6202)["features"][0]["properties"]
        assert props["code_controle"] == "E-6202"
        assert props["code_erreur"] == "E-6202"
        assert props["id_entite"] == "j1"
        assert props["type_anomalie"] == TYPE_JONCTION_INSUFFISANTE
        assert props["description"]

    def test_comptes_des_deux_sources_exposes(self) -> None:
        """C'est leur confrontation qui explique l'ecart."""
        props = construire_geojson_ecarts([self._anomalie()], PROFIL_ECARTS_6202)["features"][0]["properties"]
        assert props["nombre_references"] == 3
        assert props["nombre_geographiques"] == 2
        assert props["nombre_cables_raccordes"] == 2
        assert props["nombre_references_sans_coincidence"] == 1

    def test_seuils_exposes(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()], PROFIL_ECARTS_6202)["features"][0]["properties"]
        assert props["nombre_minimum"] == 3
        assert props["nombre_maximum"] is None

    def test_description_par_type(self) -> None:
        """Chaque type est decrit par le controle qui le rend, non par le moteur."""
        for type_anomalie in TYPES_RETENUS_6202:
            anomalie = {**self._anomalie(), "type_anomalie": type_anomalie}
            props = construire_geojson_ecarts([anomalie], PROFIL_ECARTS_6202)["features"][0]["properties"]
            assert props["description"] != type_anomalie, type_anomalie

    def test_geometrie_conservee(self) -> None:
        geom = construire_geojson_ecarts([self._anomalie()], PROFIL_ECARTS_6202)["features"][0]["geometry"]
        assert geom == {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], PROFIL_ECARTS_6202, crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([], PROFIL_ECARTS_6202)["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


def _executer_tous(repertoire: str) -> dict[str, int]:
    """Execute les six controles du moteur et reunit leurs decomptes par type.

    Aucun ne voit tout : c'est leur reunion qui doit rendre ce que le moteur
    detecte. Passer par eux plutot que par `detecter_anomalies` verifie du meme
    coup que le filtrage par type ne perd ni ne duplique rien.
    """
    from recostar.controle.cable.e9502 import executer_controle_cli as executer_9502
    from recostar.controle.conteneur.e6116 import executer_controle_cli as executer_6116
    from recostar.controle.conteneur.e6201 import executer_controle_cli as executer_6201
    from recostar.controle.conteneur.e6202 import executer_controle_cli as executer_6202
    from recostar.controle.conteneur.e6203 import executer_controle_cli as executer_6203
    from recostar.controle.conteneur.e9609 import executer_controle_cli as executer_9609

    decompte: dict[str, int] = {}
    for executer in (executer_6201, executer_6202, executer_6203, executer_6116, executer_9609, executer_9502):
        decompte.update(executer(repertoire)["anomalies_par_type"])
    return decompte


class TestCli:
    """Tests de l'execution des controles issus du moteur."""

    def test_repertoire_inexistant(self) -> None:
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichiers_absents_non_bloquants(self, tmp_path: Any) -> None:
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_jonction_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_nominal_conforme(self, tmp_path: Any) -> None:
        from recostar.controle.conteneur.e6202 import executer_controle_cli

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

    def test_derivation_insuffisante(self, tmp_path: Any) -> None:

        _ecrire_jeu(
            tmp_path,
            [_jonction(type_jonction="Derivation", cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))],
        )
        assert _executer_tous(str(tmp_path)) == {TYPE_DERIVATION_INSUFFISANTE: 1}

    def test_extremite_excessive(self, tmp_path: Any) -> None:

        _ecrire_jeu(
            tmp_path,
            [_jonction(type_jonction="ExtremiteReseau", cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))],
        )
        assert _executer_tous(str(tmp_path)) == {TYPE_EXTREMITE_CABLES_MULTIPLES: 1}

    def test_reference_sans_coincidence_geographique(self, tmp_path: Any) -> None:
        """Une declaration cables_href sans réalité géométrique ne compte pas."""

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", AILLEURS, (1.0, 1.0))],
        )
        assert _executer_tous(str(tmp_path)) == {
            TYPE_JONCTION_INSUFFISANTE: 1,
            TYPE_RACCORDEMENT_INCOHERENT: 1,
            # Le cable declare mais non touche est aussi un lien fautif, qu'E-9502
            # nomme : les deux constats portent sur le meme defaut, a deux mailles.
            TYPE_JONCTION_HORS_EXTREMITE: 1,
        }

    def test_coincidence_non_declaree(self, tmp_path: Any) -> None:
        """Un cable geographiquement raccorde mais absent de cables_href."""

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [
                _cable("c1", POINT, (0.0, 0.0)),
                _cable("c2", POINT, (1.0, 1.0)),
                _cable("c3", POINT, (2.0, 2.0)),
            ],
        )
        assert _executer_tous(str(tmp_path)) == {TYPE_RACCORDEMENT_INCOHERENT: 1}

    def test_cable_decale_dans_la_tolerance_conforme(self, tmp_path: Any) -> None:
        """Deux cables a moins d'un millimetre suffisent a une Jonction."""
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", _decale(0.0006), (0.0, 0.0)), _cable("c2", _decale(0.0009), (1.0, 1.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0

    def test_cable_decale_hors_tolerance_signale(self, tmp_path: Any) -> None:

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", _decale(0.02), (1.0, 1.0))],
        )
        assert _executer_tous(str(tmp_path)) == {
            TYPE_JONCTION_INSUFFISANTE: 1,
            TYPE_RACCORDEMENT_INCOHERENT: 1,
            # Le cable declare mais non touche est aussi un lien fautif, qu'E-9502
            # nomme : les deux constats portent sur le meme defaut, a deux mailles.
            TYPE_JONCTION_HORS_EXTREMITE: 1,
        }

    def test_telecom_conforme(self, tmp_path: Any) -> None:
        """Une jonction Telecom declarant un cable de telecommunication."""
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        ecrire_collection(str(tmp_path / FICHIER_JONCTION), [_jonction(type_jonction="Telecom", cables_href="t1")])
        ecrire_collection(
            str(tmp_path / f"{COUCHE_CABLE_TELECOM}{EXTENSION_COUCHE}"), [_cable("t1", POINT, (0.0, 0.0))]
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_telecommunication"] == 1

    def test_telecom_sans_cable_telecom_signalee(self, tmp_path: Any) -> None:
        """Un cable electrique ne satisfait pas la regle du type Telecom."""

        _ecrire_jeu(
            tmp_path,
            [_jonction(type_jonction="Telecom", cables_href="c1")],
            [_cable("c1", POINT, (0.0, 0.0))],
        )
        assert _executer_tous(str(tmp_path)) == {TYPE_CABLE_TELECOM_ABSENT: 1}

    def test_telecom_sans_cables_href_signalee(self, tmp_path: Any) -> None:

        _ecrire_jeu(tmp_path, [_jonction(type_jonction="Telecom", cables_href=None)], [])
        assert _executer_tous(str(tmp_path)) == {TYPE_CABLE_TELECOM_ABSENT: 1}

    def test_tolerance_reportee_au_rapport(self, tmp_path: Any) -> None:
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", POINT, (0.0, 0.0))])
        assert executer_controle_cli(str(tmp_path))["tolerance_coincidence_m"] == TOLERANCE_SUPERPOSITION

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", POINT, (0.0, 0.0))])
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_crs_propage(self, tmp_path: Any) -> None:
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        ecrire_collection_avec_crs(str(tmp_path / FICHIER_JONCTION), [_jonction(cables_href="c1")], "EPSG:2154")
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[0]}{EXTENSION_COUCHE}"), [_cable("c1", POINT, (0.0, 0.0))])
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert "2154" in ecarts["crs"]["properties"]["name"]

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", POINT, (0.0, 0.0))])
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
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
        from recostar.controle.conteneur.e6202 import executer_controle_cli

        jonction = _jonction(cables_href="c1,c2")
        jonction["properties"]["Commentaire"] = "note"
        _ecrire_jeu(tmp_path, [jonction], [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0


# --------------------------------------------------------------------------- #
# Liens hors extremite (E-9502)
# --------------------------------------------------------------------------- #


class TestLiensHorsExtremite:
    """Tests de liens_hors_extremite : le perimetre propre a E-9502."""

    def _bilan(self, references: frozenset[str], index: dict[str, frozenset[tuple[float, float]]]) -> Any:
        return construire_bilan(POINT, references, index)

    def test_cable_declare_sans_coincidence(self) -> None:
        bilan = self._bilan(frozenset({"c1"}), _extremites("c1", coincidents=False))
        assert liens_hors_extremite(bilan, frozenset({"c1"})) == frozenset({"c1"})

    def test_cable_coincidant_ecarte(self) -> None:
        bilan = self._bilan(frozenset({"c1"}), _extremites("c1"))
        assert liens_hors_extremite(bilan, frozenset({"c1"})) == frozenset()

    def test_cable_sans_extremite_ecarte(self) -> None:
        """La cause tient a la geometrie du cable, non a la position de la jonction."""
        bilan = self._bilan(frozenset({"c1"}), {"c1": frozenset()})
        assert liens_hors_extremite(bilan, frozenset({"c1"})) == frozenset()

    def test_cable_hors_perimetre_electrique_ecarte(self) -> None:
        """Un cable de terre ou de telecommunication ne fait pas foi ici."""
        bilan = self._bilan(frozenset({"t1"}), _extremites("t1", coincidents=False))
        assert liens_hors_extremite(bilan, frozenset()) == frozenset()

    def test_reference_non_resolue_ecartee(self) -> None:
        """Une reference qui n'aboutit pas releve d'E-9400, non de ce controle."""
        bilan = self._bilan(frozenset({"c9"}), _extremites("c1"))
        assert liens_hors_extremite(bilan, frozenset({"c1"})) == frozenset()


class TestDetecterLiens:
    """Le moteur emet une anomalie par lien (jonction, cable) fautif."""

    def test_une_anomalie_par_lien(self) -> None:
        jonction = _jonction(type_jonction="RemonteeAeroSouterraine", cables_href="c1,c2")
        anomalies = detecter_anomalies([jonction], _index(_extremites("c1", "c2", coincidents=False)))
        assert [a["id_cable"] for a in anomalies] == ["c1", "c2"]
        assert {a["type_anomalie"] for a in anomalies} == {TYPE_JONCTION_HORS_EXTREMITE}

    def test_type_jonction_libre(self) -> None:
        """E-9502 ne filtre aucun TypeJonction : le compte seul a un perimetre.

        Une remontee aero-souterraine mal posee reste une anomalie, alors
        que le compte l'ignore faute de regle.
        """
        jonction = _jonction(type_jonction="RemonteeAeroSouterraine", cables_href="c1")
        anomalies = detecter_anomalies([jonction], _index(_extremites("c1", coincidents=False)))
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_JONCTION_HORS_EXTREMITE]

    def test_statut_de_jonction_libre(self) -> None:
        jonction = _jonction(statut="Projected", cables_href="c1")
        anomalies = detecter_anomalies([jonction], _index(_extremites("c1", coincidents=False)))
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_JONCTION_HORS_EXTREMITE]

    def test_jonction_sans_point_ecartee(self) -> None:
        jonction = _jonction(cables_href="c1")
        jonction["geometry"] = {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}
        anomalies = detecter_anomalies([jonction], _index(_extremites("c1", coincidents=False)))
        assert TYPE_JONCTION_HORS_EXTREMITE not in {a["type_anomalie"] for a in anomalies}

    def test_distance_reportee(self) -> None:
        """L'ampleur du decalage oriente la correction."""
        jonction = _jonction(type_jonction="RemonteeAeroSouterraine", cables_href="c1")
        index = _index({"c1": frozenset({_decale(0.25)})})
        anomalie = detecter_anomalies([jonction], index)[0]
        assert anomalie["distance_extremite"] == 0.25

    def test_ordre_deterministe(self) -> None:
        """Un frozenset ne garantit aucun ordre : les liens sont tries."""
        jonction = _jonction(type_jonction="RemonteeAeroSouterraine", cables_href="c3,c1,c2")
        anomalies = detecter_anomalies([jonction], _index(_extremites("c1", "c2", "c3", coincidents=False)))
        assert [a["id_cable"] for a in anomalies] == ["c1", "c2", "c3"]


class TestToleranceCommune:
    """La tolerance est desormais unique : c'etait l'objet de la reunion.

    Le compte et E-9502 lisent la meme coincidence : un ecart
    submillimetrique etait conforme pour l'un, fautif pour l'autre.
    """

    def test_ecart_submillimetrique_conforme_pour_les_deux(self) -> None:
        jonction = _jonction(cables_href="c1,c2")
        index = _index({"c1": frozenset({_decale(0.0005)}), "c2": frozenset({_decale(0.0009)})})
        assert detecter_anomalies([jonction], index) == []

    def test_ecart_centimetrique_fautif_pour_les_deux(self) -> None:
        jonction = _jonction(cables_href="c1,c2")
        index = _index({"c1": frozenset({_decale(0.01)}), "c2": frozenset({_decale(0.01)})})
        types = {a["type_anomalie"] for a in detecter_anomalies([jonction], index)}
        assert TYPE_JONCTION_HORS_EXTREMITE in types
        assert TYPE_JONCTION_INSUFFISANTE in types

    def test_seuil_inclusif(self) -> None:
        """Un ecart d'exactement 1 mm compte comme un contact."""
        jonction = _jonction(cables_href="c1,c2")
        index = _index({"c1": frozenset({_decale(TOLERANCE_SUPERPOSITION)}), "c2": frozenset({POINT})})
        assert detecter_anomalies([jonction], index) == []


class TestDistanceExtremitePlusProche:
    """Tests de distance_extremite_plus_proche."""

    def test_extremite_la_plus_proche_retenue(self) -> None:
        assert distance_extremite_plus_proche(POINT, frozenset({_decale(5.0), _decale(0.5)})) == 0.5

    def test_distance_nulle(self) -> None:
        assert distance_extremite_plus_proche(POINT, frozenset({POINT})) == 0.0


# --------------------------------------------------------------------------- #
# Repartition des types entre les deux controles
# --------------------------------------------------------------------------- #


class TestRepartitionDesTypes:
    """Chaque type d'anomalie du moteur revient a un controle, et a un seul.

    Six controles se partagent ce moteur : le compte
    de cables porte un code par TypeJonction, et les deux constats qui ne sont
    pas des comptes ont chacun le leur.
    """

    def _tous(self) -> list[frozenset[str]]:
        return [
            TYPES_RETENUS_6201,
            TYPES_RETENUS_6202,
            TYPES_RETENUS_6203,
            TYPES_RETENUS_6116,
            TYPES_RETENUS_9609,
            TYPES_RETENUS_9502,
        ]

    def test_types_deux_a_deux_disjoints(self) -> None:
        retenus = self._tous()
        for indice, types in enumerate(retenus):
            for autres in retenus[indice + 1 :]:
                assert types & autres == frozenset(), types & autres

    def test_tous_les_types_du_moteur_sont_retenus(self) -> None:
        """Aucune anomalie detectee ne doit rester sans controle pour la rendre."""
        union: frozenset[str] = frozenset().union(*self._tous())
        assert union == {
            TYPE_DERIVATION_INSUFFISANTE,
            TYPE_JONCTION_INSUFFISANTE,
            TYPE_EXTREMITE_SANS_CABLE,
            TYPE_EXTREMITE_CABLES_MULTIPLES,
            TYPE_RACCORDEMENT_INCOHERENT,
            TYPE_CABLE_TELECOM_ABSENT,
            TYPE_JONCTION_HORS_EXTREMITE,
        }

    def test_e6203_porte_les_deux_sens(self) -> None:
        """La fiche E-6203 enonce « un cable et un seul » : zero et plusieurs."""
        assert TYPES_RETENUS_6203 == {TYPE_EXTREMITE_SANS_CABLE, TYPE_EXTREMITE_CABLES_MULTIPLES}

    def test_e9502_ne_retient_que_le_lien(self) -> None:
        assert TYPES_RETENUS_9502 == frozenset({TYPE_JONCTION_HORS_EXTREMITE})

    def test_chaque_regle_de_compte_nomme_son_type(self) -> None:
        """Le seuil et le code voyagent ensemble : c'est la table qui le garantit."""
        assert REGLES_PAR_TYPE["Derivation"].type_insuffisant == TYPE_DERIVATION_INSUFFISANTE
        assert REGLES_PAR_TYPE["Jonction"].type_insuffisant == TYPE_JONCTION_INSUFFISANTE
        assert REGLES_PAR_TYPE["ExtremiteReseau"].type_insuffisant == TYPE_EXTREMITE_SANS_CABLE
        assert REGLES_PAR_TYPE["ExtremiteReseau"].type_excessif == TYPE_EXTREMITE_CABLES_MULTIPLES

    def test_seule_extremite_reseau_est_plafonnee(self) -> None:
        """Un type sans plafond ne peut pas etre excessif : aucun code ne l'attend."""
        plafonnes = {nom for nom, regle in REGLES_PAR_TYPE.items() if regle.type_excessif is not None}
        assert plafonnes == {"ExtremiteReseau"}

    def test_telecom_ne_porte_aucun_type_de_compte(self) -> None:
        """Sa contrainte est de nature, non de compte : minimum 0, sans plafond."""
        regle = REGLES_PAR_TYPE["Telecom"]
        assert regle.type_insuffisant is None and regle.type_excessif is None
        assert regle.cable_telecom_requis is True


class TestPrioriteResolue:
    """Plus aucun type de ce moteur n'attend son code : aucun repli n'est remonte."""

    def test_aucun_repli_dans_le_rapport(self) -> None:
        import tempfile

        from recostar.controle.conteneur.e6202 import executer_controle_cli

        with tempfile.TemporaryDirectory() as repertoire:
            assert "priorite" not in executer_controle_cli(repertoire)

    def test_priorite_deduite_du_code(self) -> None:
        """E-6202 est `moyenne` au referentiel : l'ecart le reprend."""
        anomalie = {
            "type_anomalie": TYPE_JONCTION_INSUFFISANTE,
            "id_jonction": "j1",
            "type_jonction": "Jonction",
            "nombre_minimum": 2,
            "nombre_maximum": None,
            "nombre_cables_raccordes": 1,
            "nombre_references": 1,
            "nombre_geographiques": 1,
            "nombre_references_sans_coincidence": 0,
            "nombre_coincidences_non_declarees": 0,
            "nombre_references_non_resolues": 0,
            "nombre_cables_sans_extremite": 0,
            "nombre_cables_telecommunication": 0,
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }
        props = construire_geojson_ecarts([anomalie], PROFIL_ECARTS_6202)["features"][0]["properties"]
        assert props["priorite"] == PRIORITE_MOYENNE


class TestProprietesDuLien:
    """Le GeoJSON d'E-9502 decrit un lien, non une jonction."""

    def _anomalie_lien(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_JONCTION_HORS_EXTREMITE,
            "id_jonction": "j1",
            "type_jonction": "Jonction",
            "id_cable": "c1",
            "distance_extremite": 0.42,
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }

    def _props(self) -> dict[str, Any]:
        geojson = construire_geojson_ecarts([self._anomalie_lien()], PROFIL_ECARTS_9502)
        return geojson["features"][0]["properties"]

    def test_socle_commun(self) -> None:
        props = self._props()
        assert props["code_controle"] == "E-9502"
        assert props["code_erreur"] == "E-9502"
        assert props["id_entite"] == "j1"

    def test_cable_fautif_nomme(self) -> None:
        """Une jonction declare souvent plusieurs cables : l'ecart dit lequel."""
        assert self._props()["id_cable"] == "c1"

    def test_distance_exposee(self) -> None:
        assert self._props()["distance_extremite_m"] == 0.42

    def test_sans_colonne_de_compte(self) -> None:
        """Les comptes de cardinalite n'ont pas de sens pour un lien."""
        assert "nombre_cables_raccordes" not in self._props()

    def test_priorite_du_code(self) -> None:
        """E-9502 a un code : sa priorite en decoule, sans repli."""
        assert self._props()["priorite"] == "forte"


# --------------------------------------------------------------------------- #
# Execution CLI d'E-9502
# --------------------------------------------------------------------------- #


class TestExecuterControleCli9502:
    """Tests de l'execution du controle E-9502."""

    def _executer(self, repertoire: str, sortie: str | None = None) -> dict[str, Any]:
        from recostar.controle.cable.e9502 import executer_controle_cli

        return executer_controle_cli(repertoire, sortie)

    def test_repertoire_introuvable(self) -> None:
        assert self._executer("/chemin/inexistant")["succes"] is False

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        resultat = self._executer(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_jeu_conforme(self, tmp_path: Any) -> None:
        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))],
        )
        assert self._executer(str(tmp_path))["nombre_anomalies"] == 0

    def test_jonction_hors_extremite_detectee(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", AILLEURS, (0.0, 0.0))])
        resultat = self._executer(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_JONCTION_HORS_EXTREMITE: 1}

    def test_cable_hors_statut_non_controle(self, tmp_path: Any) -> None:
        """Le perimetre cable d'E-9502 : electrique et en cours de mise en service."""
        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", AILLEURS, (0.0, 0.0), statut="Projected")])
        assert self._executer(str(tmp_path))["nombre_anomalies"] == 0

    def test_cable_de_terre_non_controle(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_JONCTION), [_jonction(cables_href="t1")])
        ecrire_collection(str(tmp_path / f"{COUCHES_CABLE[1]}{EXTENSION_COUCHE}"), [_cable("t1", AILLEURS, (0.0, 0.0))])
        assert self._executer(str(tmp_path))["nombre_anomalies"] == 0

    def test_aucune_anomalie_de_compte(self, tmp_path: Any) -> None:
        """Le filtrage par type isole bien E-9502 du moteur partage."""
        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", POINT, (0.0, 0.0))])
        resultat = self._executer(str(tmp_path))
        assert TYPE_JONCTION_INSUFFISANTE not in resultat["anomalies_par_type"]

    def test_fichier_sortie_ecrit(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", AILLEURS, (0.0, 0.0))])
        self._executer(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE_9502))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1,c2")],
            [_cable("c1", POINT, (0.0, 0.0)), _cable("c2", POINT, (1.0, 1.0))],
        )
        self._executer(str(tmp_path))
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE_9502))

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        source = tmp_path / "src"
        source.mkdir()
        destination = tmp_path / "dst"
        _ecrire_jeu(source, [_jonction(cables_href="c1")], [_cable("c1", AILLEURS, (0.0, 0.0))])
        self._executer(str(source), str(destination))
        assert os.path.isfile(str(destination / FICHIER_SORTIE_9502))

    def test_ecart_porte_le_cable(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_jonction(cables_href="c1")], [_cable("c1", AILLEURS, (0.0, 0.0))])
        chemin = self._executer(str(tmp_path))["sortie"]
        with open(chemin, encoding="utf-8") as fichier:
            props = json.load(fichier)["features"][0]["properties"]
        assert props["id_cable"] == "c1"
        assert props["code_erreur"] == "E-9502"

    def test_cables_href_separe_par_espaces(self, tmp_path: Any) -> None:
        _ecrire_jeu(
            tmp_path,
            [_jonction(cables_href="c1 c2")],
            [_cable("c1", AILLEURS, (0.0, 0.0)), _cable("c2", AILLEURS, (1.0, 1.0))],
        )
        assert self._executer(str(tmp_path))["nombre_anomalies"] == 2

    def test_multilinestring_parties_desordonnees(self, tmp_path: Any) -> None:
        """Les parties d'un MultiLineString ne sont ni ordonnees ni orientees."""
        cable = {
            "type": "Feature",
            "properties": {"id": "c1", CHAMP_STATUT: STATUT_MISE_EN_SERVICE},
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [[[5.0, 5.0], list(POINT)], [[5.0, 5.0], [9.0, 9.0]]],
            },
        }
        ecrire_collection(str(tmp_path / FICHIER_JONCTION), [_jonction(cables_href="c1")])
        ecrire_collection(str(tmp_path / f"{COUCHE_CABLE_ELECTRIQUE}{EXTENSION_COUCHE}"), [cable])
        assert self._executer(str(tmp_path))["nombre_anomalies"] == 0

    def test_cable_boucle_non_signale(self, tmp_path: Any) -> None:
        """Une geometrie fermee ne livre aucune extremite : rien n'est tranche."""
        cable = {
            "type": "Feature",
            "properties": {"id": "c1", CHAMP_STATUT: STATUT_MISE_EN_SERVICE},
            "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]},
        }
        ecrire_collection(str(tmp_path / FICHIER_JONCTION), [_jonction(cables_href="c1")])
        ecrire_collection(str(tmp_path / f"{COUCHE_CABLE_ELECTRIQUE}{EXTENSION_COUCHE}"), [cable])
        resultat = self._executer(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_sans_extremite"] == 1
