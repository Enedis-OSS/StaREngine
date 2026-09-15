"""
Tests du controle E-3110 : conteneur sans geometrie supplementaire.

Couvre :
  - le perimetre commun aux deux versions, et son extension au support en V1.1
  - la detection automatique de version, et la version imposee
  - les trois ruptures de la chaine et leur exclusivite
  - la geometrie de l'ecart, celle du conteneur en cause
  - l'execution CLI et les champs du rapport
"""

import json
import os
from typing import Any

from recostar.controle.conteneur.e3110 import (
    COUCHES_COMMUNES,
    COUCHES_V1_1,
    FICHIER_SORTIE,
    TYPES_RETENUS,
    construire_geojson_ecarts,
    couches_controlees,
    detecter_anomalies,
    executer_controle_cli,
)
from recostar.controle.conteneur.tests.utils_tests import ecrire_collection
from recostar.controle.fonctions_communes.localisation_conteneur import (
    TYPE_GEOMSUPP_ABSENTE,
    TYPE_GEOMSUPP_INTROUVABLE,
    TYPE_GEOMSUPP_INVALIDE,
    Conteneur,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_GEOMSUPP_HREF,
    CHAMP_TYPE_LEVE,
    COUCHE_BATIMENT,
    COUCHE_COFFRET,
    COUCHE_ENCEINTE_CLOTUREE,
    COUCHE_GEOM_SUPP,
    COUCHE_SUPPORT,
    EXTENSION_COUCHE,
    FICHIER_POINT_LEVE,
)

POINT: dict[str, Any] = {"type": "Point", "coordinates": [10.0, 20.0, 30.0]}
EMPRISE: dict[str, Any] = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}


def _conteneur(identifiant: str, href: str | None, geometrie: Any = POINT) -> dict[str, Any]:
    """Feature GeoJSON d'un conteneur, avec ou sans reference d'emprise."""
    proprietes: dict[str, Any] = {"id": identifiant}
    if href is not None:
        proprietes[CHAMP_GEOMSUPP_HREF] = href
    return {"type": "Feature", "id": identifiant, "properties": proprietes, "geometry": geometrie}


def _geom_supp(identifiant: str, geometrie: Any = EMPRISE) -> dict[str, Any]:
    return {"type": "Feature", "id": identifiant, "properties": {"id": identifiant}, "geometry": geometrie}


def _ecrire(tmp_path: Any, couche: str, features: list[dict[str, Any]]) -> None:
    ecrire_collection(str(tmp_path / f"{couche}{EXTENSION_COUCHE}"), features)


def _marquer_v1_0(tmp_path: Any) -> None:
    """Un point leve portant TypeLeve suffit a conclure a la V1.0."""
    feature = {
        "type": "Feature",
        "id": "p1",
        "properties": {"id": "p1", CHAMP_TYPE_LEVE: "AltitudeGeneratrice"},
        "geometry": POINT,
    }
    ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), [feature])


class TestPerimetre:
    """Le perimetre suit la version : la V1.1 y ajoute le support."""

    def test_trois_couches_communes(self) -> None:
        assert set(COUCHES_COMMUNES) == {COUCHE_COFFRET, COUCHE_BATIMENT, COUCHE_ENCEINTE_CLOTUREE}

    def test_support_propre_a_la_v1_1(self) -> None:
        assert COUCHES_V1_1 == (COUCHE_SUPPORT,)

    def test_perimetre_v1_0(self) -> None:
        assert couches_controlees("1.0") == COUCHES_COMMUNES

    def test_perimetre_v1_1(self) -> None:
        assert set(couches_controlees("1.1")) == set(COUCHES_COMMUNES) | {COUCHE_SUPPORT}

    def test_support_absent_du_perimetre_v1_0(self) -> None:
        assert COUCHE_SUPPORT not in couches_controlees("1.0")


class TestDetecterAnomalies:
    """Les trois ruptures, exclusives, et le conforme."""

    def _detecter(self, conteneur: Conteneur, geoms: dict[str, Any]) -> list[dict[str, Any]]:
        return detecter_anomalies({"k1": conteneur}, frozenset({"k1"}), geoms)

    def test_conforme(self) -> None:
        assert self._detecter(Conteneur(POINT, "g1", COUCHE_COFFRET), {"g1": EMPRISE}) == []

    def test_reference_absente(self) -> None:
        anomalies = self._detecter(Conteneur(POINT, None, COUCHE_COFFRET), {"g1": EMPRISE})
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_GEOMSUPP_ABSENTE]

    def test_reference_introuvable(self) -> None:
        anomalies = self._detecter(Conteneur(POINT, "g9", COUCHE_COFFRET), {"g1": EMPRISE})
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_GEOMSUPP_INTROUVABLE]

    def test_geometrie_invalide(self) -> None:
        anomalies = self._detecter(Conteneur(POINT, "g1", COUCHE_COFFRET), {"g1": None})
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_GEOMSUPP_INVALIDE]

    def test_une_anomalie_au_plus(self) -> None:
        """La classification s'arrête à la première rupture."""
        for href, geoms in ((None, {}), ("g9", {}), ("g1", {"g1": None})):
            assert len(self._detecter(Conteneur(POINT, href, COUCHE_COFFRET), geoms)) == 1

    def test_hors_perimetre_ignore(self) -> None:
        """Un conteneur indexé mais hors périmètre n'est pas jugé."""
        conteneurs = {"k1": Conteneur(POINT, None, COUCHE_SUPPORT)}
        assert detecter_anomalies(conteneurs, frozenset(), {}) == []

    def test_anomalie_documentee(self) -> None:
        anomalie = self._detecter(Conteneur(POINT, "g9", COUCHE_BATIMENT), {})[0]
        assert anomalie["id_conteneur"] == "k1"
        assert anomalie["couche_conteneur"] == COUCHE_BATIMENT
        assert anomalie["geometriesupplementaire_href"] == "g9"
        assert anomalie["geometrie"] == POINT

    def test_ordre_deterministe(self) -> None:
        conteneurs = {nom: Conteneur(POINT, None, COUCHE_COFFRET) for nom in ("k3", "k1", "k2")}
        anomalies = detecter_anomalies(conteneurs, frozenset(conteneurs), {})
        assert [a["id_conteneur"] for a in anomalies] == ["k1", "k2", "k3"]


class TestGeojsonEcarts:
    """L'écart porte le conteneur en cause et sa couche."""

    def _props(self, conteneur: Conteneur) -> dict[str, Any]:
        anomalies = detecter_anomalies({"k1": conteneur}, frozenset({"k1"}), {})
        return construire_geojson_ecarts(anomalies)["features"][0]["properties"]

    def test_socle_commun(self) -> None:
        props = self._props(Conteneur(POINT, None, COUCHE_COFFRET))
        assert props["code_controle"] == "E-3110"
        assert props["code_erreur"] == "E-3110"
        assert props["id_entite"] == "k1"
        assert props["priorite"] == "forte"

    def test_couche_nommee(self) -> None:
        """Quatre couches partagent le fichier d'écarts : sans elle, l'information serait perdue."""
        props = self._props(Conteneur(POINT, None, COUCHE_ENCEINTE_CLOTUREE))
        assert props["couche"] == COUCHE_ENCEINTE_CLOTUREE
        assert props["fichier_source"] == f"{COUCHE_ENCEINTE_CLOTUREE}{EXTENSION_COUCHE}"

    def test_les_trois_types_decrits(self) -> None:
        assert TYPES_RETENUS == {TYPE_GEOMSUPP_ABSENTE, TYPE_GEOMSUPP_INTROUVABLE, TYPE_GEOMSUPP_INVALIDE}

    def test_description_par_type(self) -> None:
        for type_anomalie in TYPES_RETENUS:
            anomalie = {
                "type_anomalie": type_anomalie,
                "id_conteneur": "k1",
                "couche_conteneur": COUCHE_COFFRET,
                "geometriesupplementaire_href": None,
                "geometrie": POINT,
            }
            props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
            assert props["description"] != type_anomalie, type_anomalie

    def test_geometrie_du_conteneur_conservee(self) -> None:
        anomalies = detecter_anomalies({"k1": Conteneur(POINT, None, COUCHE_COFFRET)}, frozenset({"k1"}), {})
        assert construire_geojson_ecarts(anomalies)["features"][0]["geometry"] == POINT

    def test_conteneur_sans_geometrie_propre(self) -> None:
        """Cumul de deux défauts : l'écart reste lisible, sans géométrie."""
        anomalies = detecter_anomalies({"k1": Conteneur(None, None, COUCHE_COFFRET)}, frozenset({"k1"}), {})
        assert construire_geojson_ecarts(anomalies)["features"][0]["geometry"] is None

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


class TestCli:
    """Exécution du contrôle, et effet de la version sur le périmètre."""

    def test_repertoire_introuvable(self) -> None:
        assert executer_controle_cli("/chemin/inexistant")["succes"] is False

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["fichier_geometrie_supplementaire_absent"] is True

    def test_jeu_conforme(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_COFFRET, [_conteneur("k1", "g1")])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [_geom_supp("g1")])
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_coffret_sans_emprise(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_COFFRET, [_conteneur("k1", None)])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_GEOMSUPP_ABSENTE: 1}

    def test_batiment_et_enceinte_controles(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_BATIMENT, [_conteneur("b1", None)])
        _ecrire(tmp_path, COUCHE_ENCEINTE_CLOTUREE, [_conteneur("e1", None)])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [])
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 2

    def test_support_controle_en_v1_1(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_SUPPORT, [_conteneur("s1", None)])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [])
        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat["version_controlee"] == "1.1"
        assert resultat["nombre_anomalies"] == 1

    def test_support_ignore_en_v1_0(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_SUPPORT, [_conteneur("s1", None)])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [])
        resultat = executer_controle_cli(str(tmp_path), version="1.0")
        assert resultat["version_controlee"] == "1.0"
        assert resultat["nombre_anomalies"] == 0

    def test_detection_automatique_v1_0(self, tmp_path: Any) -> None:
        """Un point levé portant TypeLeve fait conclure à la V1.0 : le support sort du périmètre."""
        _marquer_v1_0(tmp_path)
        _ecrire(tmp_path, COUCHE_SUPPORT, [_conteneur("s1", None)])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["version_controlee"] == "1.0"
        assert resultat["nombre_anomalies"] == 0

    def test_detection_automatique_repli_v1_1(self, tmp_path: Any) -> None:
        """Sans indice, le repli est la version courante : le support est contrôlé."""
        _ecrire(tmp_path, COUCHE_SUPPORT, [_conteneur("s1", None)])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["version_controlee"] == "1.1"
        assert resultat["nombre_anomalies"] == 1

    def test_couches_controlees_reportees(self, tmp_path: Any) -> None:
        """Un périmètre qui dépend d'une détection doit dire sur quoi il s'est arrêté."""
        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert COUCHE_SUPPORT in resultat["couches_controlees"]
        assert executer_controle_cli(str(tmp_path), version="1.0")["couches_controlees"] == list(COUCHES_COMMUNES)

    def test_reference_introuvable(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_COFFRET, [_conteneur("k1", "g9")])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [_geom_supp("g1")])
        assert executer_controle_cli(str(tmp_path))["anomalies_par_type"] == {TYPE_GEOMSUPP_INTROUVABLE: 1}

    def test_geometrie_supplementaire_vide(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_COFFRET, [_conteneur("k1", "g1")])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [_geom_supp("g1", None)])
        assert executer_controle_cli(str(tmp_path))["anomalies_par_type"] == {TYPE_GEOMSUPP_INVALIDE: 1}

    def test_comptes_du_rapport(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_COFFRET, [_conteneur("k1", "g1"), _conteneur("k2", None)])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [_geom_supp("g1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_conteneurs_controles"] == 2
        assert resultat["nombre_geometries_supplementaires"] == 1
        assert resultat["fichier_geometrie_supplementaire_absent"] is False

    def test_fichier_sortie_ecrit(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_COFFRET, [_conteneur("k1", None)])
        chemin = executer_controle_cli(str(tmp_path))["sortie"]
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))
        with open(chemin, encoding="utf-8") as fichier:
            props = json.load(fichier)["features"][0]["properties"]
        assert props["code_erreur"] == "E-3110"

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_COFFRET, [_conteneur("k1", "g1")])
        _ecrire(tmp_path, COUCHE_GEOM_SUPP, [_geom_supp("g1")])
        executer_controle_cli(str(tmp_path))
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        source = tmp_path / "src"
        source.mkdir()
        destination = tmp_path / "dst"
        _ecrire(source, COUCHE_COFFRET, [_conteneur("k1", None)])
        executer_controle_cli(str(source), str(destination))
        assert os.path.isfile(str(destination / FICHIER_SORTIE))
