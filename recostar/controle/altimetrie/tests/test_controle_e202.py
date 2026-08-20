"""
Tests unitaires du controle altimetrique des sommets (controle_e202).

Couvre les cas nominaux et les cas limites :
- calcul de l'ecart residuel entre sommets centraux
- logique de la fenetre glissante et exclusion des 3 premiers/derniers sommets
- exclusion des cables references par un cheminement aerien
- filtrage des entites par Statut (« UnderCommissionning »)
- selection des couches selon la version RecoStaR (1.0 vs 1.1)
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from controle_e202 import (
    CHAMP_STATUT,
    FICHIER_AERIEN,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_CABLE_TELECOM,
    FICHIER_CABLE_TERRE,
    FICHIER_SORTIE,
    FICHIERS_CABLES_PAR_VERSION,
    NB_SOMMETS_IGNORES,
    PRIORITE_ANOMALIE,
    SEUIL_ECART_ALTI,
    TAILLE_FENETRE,
    VALEUR_STATUT_CONTROLE,
    _analyser_sommets_cable,
    _ecart_residuel_centraux,
    _indices_centraux_valides,
    collecter_ids_cables_aeriens,
    construire_geojson_ecarts,
    controler_altimetrie_sommets,
    controler_couches_cables,
    executer_controle_cli,
    filtrer_cables_a_controler,
    resoudre_fichiers_cables,
)
from controle_e204 import FICHIER_DETECTION_VERSION

# --------------------------------------------------------------------------- #
# Helpers specifiques a ce module de test
# --------------------------------------------------------------------------- #


def _construire_cable(
    identifiant: str,
    coordonnees: list[list[float]],
    statut: str = VALEUR_STATUT_CONTROLE,
) -> dict[str, Any]:
    """Construit une feature cable minimale avec un Statut pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, CHAMP_STATUT: statut},
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


def _construire_cable_multi(
    identifiant: str,
    parties: list[list[list[float]]],
    statut: str = VALEUR_STATUT_CONTROLE,
) -> dict[str, Any]:
    """Construit une feature cable MultiLineString (plusieurs parties) pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, CHAMP_STATUT: statut},
        "geometry": {"type": "MultiLineString", "coordinates": parties},
    }


def _construire_aerien(identifiant: str, cables_href: Any) -> dict[str, Any]:
    """Construit une feature aerienne minimale referencant un ou plusieurs cables."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "cables_href": cables_href},
        "geometry": {"type": "LineString", "coordinates": [[0, 0, 0], [1, 1, 0]]},
    }


def _ligne_plate(nb_sommets: int) -> list[list[float]]:
    """Genere une ligne horizontale strictement plate en altimetrie."""
    return [[float(i), 0.0, 10.0] for i in range(nb_sommets)]


def _ecrire_couche(
    repertoire: Any,
    fichier: str,
    features: list[dict[str, Any]],
) -> None:
    """Ecrit une couche GeoJSON minimale dans le repertoire de test."""
    collection = {"type": "FeatureCollection", "features": features}
    (repertoire / fichier).write_text(json.dumps(collection), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Tests des fonctions unitaires (coeur geometrique inchange)
# --------------------------------------------------------------------------- #


class TestEcartResiduel:
    """Tests unitaires du calcul de l'ecart residuel sur une fenetre de 4 sommets."""

    def test_ligne_parfaitement_plate_retourne_zero(self) -> None:
        fenetre = [[0, 0, 10], [1, 0, 10], [2, 0, 10], [3, 0, 10]]
        assert _ecart_residuel_centraux(fenetre) == pytest.approx(0.0)

    def test_pente_reguliere_retourne_zero(self) -> None:
        fenetre = [[0, 0, 10], [1, 0, 11], [2, 0, 12], [3, 0, 13]]
        assert _ecart_residuel_centraux(fenetre) == pytest.approx(0.0)

    def test_pic_altimetrique_detecte(self) -> None:
        fenetre = [[0, 0, 10], [1, 0, 10], [2, 0, 11], [3, 0, 10]]
        assert _ecart_residuel_centraux(fenetre) == pytest.approx(1.0)

    def test_fenetre_degeneree_utilise_ecart_brut(self) -> None:
        fenetre = [[5, 5, 10], [5, 5, 10.5], [5, 5, 11.0], [5, 5, 10]]
        assert _ecart_residuel_centraux(fenetre) == pytest.approx(0.5)


class TestIndicesCentraux:
    """Tests de la plage des indices de fenetres analysables."""

    def test_cable_trop_court_ne_produit_aucune_fenetre(self) -> None:
        for nb in range(0, 8):
            assert len(list(_indices_centraux_valides(nb))) == 0

    def test_cable_de_huit_sommets_produit_une_seule_fenetre(self) -> None:
        indices = list(_indices_centraux_valides(8))
        assert indices == [2]

    def test_cable_de_dix_sommets_produit_trois_fenetres(self) -> None:
        indices = list(_indices_centraux_valides(10))
        assert indices == [2, 3, 4]


class TestAnalyseSommets:
    """Tests de l'analyse altimetrique d'un cable complet."""

    def test_cable_plat_sans_anomalie(self) -> None:
        coordonnees = _ligne_plate(12)
        assert _analyser_sommets_cable(coordonnees) == {}

    def test_anomalie_au_centre_detectee(self) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 11.0
        anomalies = _analyser_sommets_cable(coordonnees)
        assert 6 in anomalies
        assert anomalies[6] > SEUIL_ECART_ALTI

    def test_sommets_ignores_ne_sont_jamais_signales(self) -> None:
        coordonnees = _ligne_plate(12)
        for indice_ignore in (0, 1, 2, 9, 10, 11):
            coordonnees_test = [list(point) for point in coordonnees]
            coordonnees_test[indice_ignore][2] = 15.0
            anomalies = _analyser_sommets_cable(coordonnees_test)
            indices_ignores = set(range(NB_SOMMETS_IGNORES)) | set(
                range(len(coordonnees_test) - NB_SOMMETS_IGNORES, len(coordonnees_test))
            )
            assert indices_ignores.isdisjoint(anomalies.keys())

    def test_ecart_sous_seuil_ignore(self) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 10.10
        assert _analyser_sommets_cable(coordonnees) == {}


class TestCollecteIdsAeriens:
    """Tests de la normalisation du champ cables_href."""

    def test_reference_simple_sous_forme_chaine(self) -> None:
        features = [_construire_aerien("a1", "cable-1")]
        assert collecter_ids_cables_aeriens(features) == {"cable-1"}

    def test_reference_liste_multiple(self) -> None:
        features = [_construire_aerien("a1", ["cable-1", "cable-2"])]
        assert collecter_ids_cables_aeriens(features) == {"cable-1", "cable-2"}

    def test_references_multiples_dans_une_chaine(self) -> None:
        features = [_construire_aerien("a1", "cable-1 cable-2")]
        assert collecter_ids_cables_aeriens(features) == {"cable-1", "cable-2"}

    def test_aucune_reference(self) -> None:
        assert collecter_ids_cables_aeriens([]) == set()


class TestControleAltimetrie:
    """Tests d'integration du controle altimetrique sur une collection de cables."""

    def test_cable_aerien_est_exclu(self) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        cables = [_construire_cable("cable-aerien", coordonnees)]
        anomalies = controler_altimetrie_sommets(cables, {"cable-aerien"})
        assert anomalies == []

    def test_cable_avec_anomalie_produit_un_resultat(self) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        cables = [_construire_cable("cable-sol", coordonnees)]
        anomalies = controler_altimetrie_sommets(cables, set())
        assert len(anomalies) >= 1
        assert all(a["id_cable"] == "cable-sol" for a in anomalies)
        assert all(a["ecart_residuel"] > SEUIL_ECART_ALTI for a in anomalies)

    def test_cable_sans_coordonnees_z_est_ignore(self) -> None:
        coordonnees = [[float(i), 0.0] for i in range(12)]
        cables = [_construire_cable("cable-2d", coordonnees)]
        assert controler_altimetrie_sommets(cables, set()) == []

    def test_cable_trop_court_est_ignore(self) -> None:
        cables = [_construire_cable("cable-court", _ligne_plate(TAILLE_FENETRE - 1))]
        assert controler_altimetrie_sommets(cables, set()) == []


def _decouper_en_troncons(
    ligne: list[list[float]],
    coupure: int,
) -> list[list[list[float]]]:
    """Decoupe une ligne en 2 troncons partageant le sommet frontiere (indice coupure).

    Chaque troncon est copie en profondeur pour eviter tout aliasing entre parties.
    Le recollage (linemerge) doit reconstituer exactement la ligne d'origine.
    """
    premier = [list(sommet) for sommet in ligne[: coupure + 1]]
    second = [list(sommet) for sommet in ligne[coupure:]]
    return [premier, second]


class TestMultiLineStringRecolle:
    """Les cables MultiLineString connexes sont recolles et controles dans leur ensemble."""

    def test_multilinestring_connexe_controle_dans_son_ensemble(self) -> None:
        # Ligne plate de 13 sommets avec un pic central au sommet 6, decoupee en
        # 2 troncons partageant le sommet 6 : apres recollage, le pic est detecte.
        ligne = _ligne_plate(13)
        ligne[6][2] = 15.0
        cable = _construire_cable_multi("cm", _decouper_en_troncons(ligne, 6))
        anomalies = controler_altimetrie_sommets([cable], set())
        assert any(a["indice_sommet"] == 6 and a["id_cable"] == "cm" for a in anomalies)

    def test_troncons_en_desordre_sont_recolles(self) -> None:
        # Meme cable mais troncons stockes dans le desordre (cas des donnees reelles) :
        # linemerge les reordonne ; le pic central reste detecte.
        ligne = _ligne_plate(13)
        ligne[6][2] = 15.0
        troncons = _decouper_en_troncons(ligne, 6)
        cable = _construire_cable_multi("cm", [troncons[1], troncons[0]])
        anomalies = controler_altimetrie_sommets([cable], set())
        assert any(a["indice_sommet"] == 6 for a in anomalies)

    def test_multilinestring_disjoint_est_ecarte(self) -> None:
        # Deux troncons eloignes sans noeud partage : linemerge ne produit pas un
        # LineString unique, le cable n'est pas controle malgre un pic.
        troncon_a = [[float(i), 0.0, 10.0] for i in range(6)]
        troncon_b = [[float(i), 0.0, 10.0] for i in range(100, 106)]
        troncon_b[2][2] = 50.0
        cable = _construire_cable_multi("cm", [troncon_a, troncon_b])
        assert controler_altimetrie_sommets([cable], set()) == []

    def test_multilinestring_2d_ignore(self) -> None:
        ligne_2d = [[float(i), 0.0] for i in range(13)]
        cable = _construire_cable_multi("cm", _decouper_en_troncons(ligne_2d, 6))
        assert controler_altimetrie_sommets([cable], set()) == []

    def test_multilinestring_aerien_est_exclu(self) -> None:
        ligne = _ligne_plate(13)
        ligne[6][2] = 15.0
        cable = _construire_cable_multi("cm-aerien", _decouper_en_troncons(ligne, 6))
        assert controler_altimetrie_sommets([cable], {"cm-aerien"}) == []

    def test_linestring_analyse_sur_integralite_du_cable(self) -> None:
        # Controle : un LineString est bien traite comme une entite unique,
        # l'anomalie centrale est detectee a son indice sequentiel global.
        coords = _ligne_plate(12)
        coords[6][2] = 15.0
        cable = _construire_cable("cl", coords)
        anomalies = controler_altimetrie_sommets([cable], set())
        assert any(a["indice_sommet"] == 6 and a["id_cable"] == "cl" for a in anomalies)


# --------------------------------------------------------------------------- #
# Tests du filtrage par Statut et de la selection des couches par version
# --------------------------------------------------------------------------- #


class TestFiltrageStatut:
    """Tests du filtrage des entites sur le Statut « UnderCommissionning »."""

    def test_conserve_uniquement_under_commissionning(self) -> None:
        features = [
            _construire_cable("c1", _ligne_plate(12), VALEUR_STATUT_CONTROLE),
            _construire_cable("c2", _ligne_plate(12), "Functional"),
            _construire_cable("c3", _ligne_plate(12), "Projected"),
        ]
        retenus = filtrer_cables_a_controler(features)
        assert [f["properties"]["id"] for f in retenus] == ["c1"]

    def test_statut_absent_est_ecarte(self) -> None:
        feature = {
            "type": "Feature",
            "properties": {"id": "c1"},
            "geometry": {"type": "LineString", "coordinates": _ligne_plate(12)},
        }
        assert filtrer_cables_a_controler([feature]) == []

    def test_collection_vide(self) -> None:
        assert filtrer_cables_a_controler([]) == []


class TestResolutionCouches:
    """Tests de la selection des couches de cables selon la version."""

    def test_version_1_0_uniquement_electrique_et_terre(self) -> None:
        # Exigence v1.0 : controle restreint aux seules couches electrique et terre.
        fichiers = resoudre_fichiers_cables("1.0")
        assert set(fichiers) == {FICHIER_CABLE_ELECTRIQUE, FICHIER_CABLE_TERRE}
        assert FICHIER_CABLE_TELECOM not in fichiers

    def test_version_1_1_ajoute_la_telecom(self) -> None:
        fichiers = resoudre_fichiers_cables("1.1")
        assert FICHIER_CABLE_TELECOM in fichiers
        assert set(fichiers) == set(FICHIERS_CABLES_PAR_VERSION["1.1"])

    def test_version_inconnue_repli_sur_defaut(self) -> None:
        assert resoudre_fichiers_cables("inconnue") == FICHIERS_CABLES_PAR_VERSION["1.1"]


class TestControlerCouchesCables:
    """Tests de l'orchestration multi-couches avec filtrage par Statut."""

    def test_couche_absente_est_ignoree(self, tmp_path: Any) -> None:
        # Seule la couche electrique existe ; les autres sont absentes.
        _ecrire_couche(
            tmp_path,
            FICHIER_CABLE_ELECTRIQUE,
            [_construire_cable("c1", _ligne_plate(12))],
        )
        fichiers = (
            FICHIER_CABLE_ELECTRIQUE,
            FICHIER_CABLE_TERRE,
            FICHIER_CABLE_TELECOM,
        )
        _, _, couches = controler_couches_cables(str(tmp_path), fichiers, set())
        assert couches == ["RPD_CableElectrique_Reco"]

    def test_anomalies_annotees_de_leur_couche(self, tmp_path: Any) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        _ecrire_couche(tmp_path, FICHIER_CABLE_TERRE, [_construire_cable("ct", coordonnees)])
        anomalies, _, couches = controler_couches_cables(str(tmp_path), (FICHIER_CABLE_TERRE,), set())
        assert couches == ["RPD_CableTerre_Reco"]
        assert anomalies
        assert all(a["couche"] == "RPD_CableTerre_Reco" for a in anomalies)

    def test_entites_hors_statut_non_controlees(self, tmp_path: Any) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        # L'entite porte un Statut non controle : aucune anomalie attendue.
        _ecrire_couche(
            tmp_path,
            FICHIER_CABLE_ELECTRIQUE,
            [_construire_cable("c1", coordonnees, "Functional")],
        )
        anomalies, _, _ = controler_couches_cables(str(tmp_path), (FICHIER_CABLE_ELECTRIQUE,), set())
        assert anomalies == []

    def test_agregation_multi_couches(self, tmp_path: Any) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        _ecrire_couche(tmp_path, FICHIER_CABLE_ELECTRIQUE, [_construire_cable("ce", coordonnees)])
        _ecrire_couche(tmp_path, FICHIER_CABLE_TERRE, [_construire_cable("ct", coordonnees)])
        anomalies, _, couches = controler_couches_cables(
            str(tmp_path), (FICHIER_CABLE_ELECTRIQUE, FICHIER_CABLE_TERRE), set()
        )
        couches_anomalies = {a["couche"] for a in anomalies}
        assert couches_anomalies == {"RPD_CableElectrique_Reco", "RPD_CableTerre_Reco"}
        assert couches == ["RPD_CableElectrique_Reco", "RPD_CableTerre_Reco"]


class TestGeojsonSortie:
    """Tests de la serialisation des anomalies en FeatureCollection."""

    def test_structure_geojson_conforme(self) -> None:
        anomalies = [
            {
                "id_cable": "c1",
                "couche": "RPD_CableTerre_Reco",
                "indice_sommet": 5,
                "coordonnees": [1.0, 2.0, 3.0],
                "ecart_residuel": 0.42,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1
        feature = geojson["features"][0]
        assert feature["geometry"] == {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        assert feature["properties"]["id_cable"] == "c1"
        assert feature["properties"]["couche"] == "RPD_CableTerre_Reco"
        assert feature["properties"]["indice_sommet"] == 5
        assert feature["properties"]["ecart_residuel_m"] == pytest.approx(0.42)
        assert feature["properties"]["priorite"] == PRIORITE_ANOMALIE

    def test_couche_absente_serialisee_a_none(self) -> None:
        anomalies = [
            {
                "id_cable": "c1",
                "indice_sommet": 5,
                "coordonnees": [1.0, 2.0, 3.0],
                "ecart_residuel": 0.42,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["features"][0]["properties"]["couche"] is None

    def test_feature_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson


# --------------------------------------------------------------------------- #
# Tests CLI bout en bout
# --------------------------------------------------------------------------- #


def _ecrire_detection_version(repertoire: Any, version: str) -> None:
    """Ecrit RPD_PointLeveOuvrageReseau_Reco pour piloter la detection auto.

    Le champ TypeLeve est present pour la v1.0, absent pour la v1.1.
    """
    proprietes: dict[str, Any] = {"id": "pl1"}
    if version == "1.0":
        proprietes["TypeLeve"] = "Z"
    feature = {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
    }
    _ecrire_couche(repertoire, FICHIER_DETECTION_VERSION, [feature])


@pytest.fixture
def repertoire_test(tmp_path: Any) -> str:
    """Prepare un repertoire avec cables electriques et donnees aerien."""
    coordonnees_anomalie = _ligne_plate(12)
    coordonnees_anomalie[6][2] = 15.0

    _ecrire_couche(
        tmp_path,
        FICHIER_CABLE_ELECTRIQUE,
        [
            _construire_cable("cable-sol", coordonnees_anomalie),
            _construire_cable("cable-aerien-ref", _ligne_plate(12)),
        ],
    )
    _ecrire_couche(tmp_path, FICHIER_AERIEN, [_construire_aerien("aerien-1", "cable-aerien-ref")])
    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_execution_ecrit_fichier_sortie(self, repertoire_test: str) -> None:
        resultat = executer_controle_cli(repertoire_test, version="1.0")
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] >= 1
        assert resultat["cables_exclus"] == 1
        assert resultat["version_detectee"] == "1.0"
        assert "RPD_CableElectrique_Reco" in resultat["couches_controlees"]
        chemin_sortie = os.path.join(repertoire_test, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)
        with open(chemin_sortie, encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) >= 1

    def test_cable_multilinestring_recolle_controle(self, tmp_path: Any) -> None:
        # Une couche MultiLineString connexe est recollee puis controlee dans son
        # ensemble : le pic central produit une anomalie.
        ligne = _ligne_plate(13)
        ligne[6][2] = 15.0
        cable = _construire_cable_multi("cm", _decouper_en_troncons(ligne, 6))
        _ecrire_couche(tmp_path, FICHIER_CABLE_ELECTRIQUE, [cable])
        resultat = executer_controle_cli(str(tmp_path), version="1.0")
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] >= 1

    def test_repertoire_sortie_distinct(self, repertoire_test: str, tmp_path: Any) -> None:
        dossier_sortie = tmp_path / "sortie"
        resultat = executer_controle_cli(repertoire_test, str(dossier_sortie), version="1.0")
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(str(dossier_sortie), FICHIER_SORTIE))

    def test_aucune_couche_retourne_erreur(self, tmp_path: Any) -> None:
        # Repertoire sans aucune couche de cables.
        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_telecom_controlee_en_v1_1_seulement(self, tmp_path: Any) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        _ecrire_couche(tmp_path, FICHIER_CABLE_TELECOM, [_construire_cable("ctel", coordonnees)])

        resultat_v10 = executer_controle_cli(str(tmp_path), version="1.0")
        # La couche telecom est seule presente : en v1.0 elle n'est pas controlee.
        assert resultat_v10["succes"] is False

        resultat_v11 = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat_v11["succes"] is True
        assert "RPD_CableTelecommunication_Reco" in resultat_v11["couches_controlees"]
        assert resultat_v11["nombre_anomalies"] >= 1

    def test_filtrage_statut_en_v1_0(self, tmp_path: Any) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        _ecrire_couche(
            tmp_path,
            FICHIER_CABLE_ELECTRIQUE,
            [
                _construire_cable("controle", coordonnees),
                _construire_cable("ignore", coordonnees, "Functional"),
            ],
        )
        resultat = executer_controle_cli(str(tmp_path), version="1.0")
        assert resultat["succes"] is True
        chemin_sortie = os.path.join(str(tmp_path), FICHIER_SORTIE)
        with open(chemin_sortie, encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        ids_signales = {f["properties"]["id_cable"] for f in contenu["features"]}
        assert ids_signales == {"controle"}

    def test_detection_auto_v1_0_depuis_pointleve(self, tmp_path: Any) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        _ecrire_couche(tmp_path, FICHIER_CABLE_ELECTRIQUE, [_construire_cable("ce", coordonnees)])
        _ecrire_couche(tmp_path, FICHIER_CABLE_TELECOM, [_construire_cable("ctel", coordonnees)])
        _ecrire_detection_version(tmp_path, "1.0")

        resultat = executer_controle_cli(str(tmp_path))  # version auto
        assert resultat["version_detectee"] == "1.0"
        # En v1.0 detectee, la telecom n'est pas dans les couches controlees.
        assert "RPD_CableTelecommunication_Reco" not in resultat["couches_controlees"]

    def test_detection_auto_repli_v1_1_si_pointleve_absent(self, tmp_path: Any) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        _ecrire_couche(tmp_path, FICHIER_CABLE_ELECTRIQUE, [_construire_cable("ce", coordonnees)])
        _ecrire_couche(tmp_path, FICHIER_CABLE_TELECOM, [_construire_cable("ctel", coordonnees)])

        resultat = executer_controle_cli(str(tmp_path))  # version auto, sans detection
        assert resultat["version_detectee"] == "1.1"
        assert "RPD_CableTelecommunication_Reco" in resultat["couches_controlees"]
