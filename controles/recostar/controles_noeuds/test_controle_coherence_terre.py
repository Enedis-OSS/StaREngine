"""
Tests unitaires du controle de coherence terre.

Couvre les cas nominaux et les cas limites :
- aucun cable, aucun noeud : pas d'anomalie
- cable avec noeudreseau_href valide : pas d'anomalie
- cable avec noeudreseau_href null : anomalie
- cable avec noeudreseau_href vers un id inexistant : anomalie
- cable sans identifiant : anomalie
- construction du rapport JSON
- construction du GeoJSON d'ecarts avec le champ priorite
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_coherence_terre import (
    construire_geojson_ecarts,
    construire_rapport_json,
    controler_coherence_terre,
    executer_controle_cli,
    extraire_ids_noeuds_terre,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #


def _construire_cable_terre(
    identifiant: str | None,
    noeudreseau_href: str | None = None,
) -> dict[str, Any]:
    """Construit une feature cable terre minimale pour les tests."""
    props: dict[str, Any] = {}
    if identifiant is not None:
        props["id"] = identifiant
    if noeudreseau_href is not None:
        props["noeudreseau_href"] = noeudreseau_href
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
    }


def _construire_noeud_terre(identifiant: str) -> dict[str, Any]:
    """Construit une feature noeud terre minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "Point", "coordinates": [0, 0, 0]},
    }


# --------------------------------------------------------------------------- #
# Tests de extraire_ids_noeuds_terre
# --------------------------------------------------------------------------- #


class TestExtraireIdsNoeuds:
    """Verifie l'extraction des identifiants des noeuds terre."""

    def test_extraction_ids(self) -> None:
        """Les identifiants sont correctement extraits."""
        noeuds = [_construire_noeud_terre("N1"), _construire_noeud_terre("N2")]
        ids = extraire_ids_noeuds_terre(noeuds)
        assert ids == frozenset({"N1", "N2"})

    def test_extraction_vide(self) -> None:
        """Une liste vide retourne un ensemble vide."""
        ids = extraire_ids_noeuds_terre([])
        assert ids == frozenset()

    def test_noeud_sans_id_ignore(self) -> None:
        """Un noeud sans propriete id est ignore."""
        noeud_sans_id: dict[str, Any] = {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Point", "coordinates": [0, 0]},
        }
        ids = extraire_ids_noeuds_terre([noeud_sans_id])
        assert ids == frozenset()


# --------------------------------------------------------------------------- #
# Tests de la logique metier
# --------------------------------------------------------------------------- #


class TestControlerCoherenceTerre:
    """Verifie la detection des anomalies de coherence terre."""

    def test_aucune_anomalie_si_vide(self) -> None:
        """Aucune anomalie quand il n'y a ni cable ni noeud."""
        anomalies = controler_coherence_terre([], frozenset())
        assert anomalies == []

    def test_cable_avec_noeud_valide(self) -> None:
        """Un cable referencant un noeud existant ne genere pas d'anomalie."""
        cable = _construire_cable_terre("C1", noeudreseau_href="N1")
        anomalies = controler_coherence_terre([cable], frozenset({"N1"}))
        assert anomalies == []

    def test_cable_sans_noeudreseau_href(self) -> None:
        """Un cable sans noeudreseau_href genere une anomalie."""
        cable = _construire_cable_terre("C1")
        anomalies = controler_coherence_terre([cable], frozenset({"N1"}))
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "cable_terre_sans_noeud_terre"
        assert anomalies[0]["id_cable"] == "C1"

    def test_cable_avec_href_inexistant(self) -> None:
        """Un cable referencant un noeud inexistant genere une anomalie."""
        cable = _construire_cable_terre("C1", noeudreseau_href="N999")
        anomalies = controler_coherence_terre([cable], frozenset({"N1"}))
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "cable_terre_sans_noeud_terre"
        assert anomalies[0]["noeudreseau_href"] == "N999"

    def test_cable_sans_identifiant(self) -> None:
        """Un cable sans id genere une anomalie specifique."""
        cable = _construire_cable_terre(None)
        anomalies = controler_coherence_terre([cable], frozenset({"N1"}))
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "cable_terre_sans_identifiant"

    def test_melange_conforme_et_non_conforme(self) -> None:
        """Seul le cable non conforme genere une anomalie."""
        cable_ok = _construire_cable_terre("C1", noeudreseau_href="N1")
        cable_ko = _construire_cable_terre("C2")
        anomalies = controler_coherence_terre([cable_ok, cable_ko], frozenset({"N1"}))
        assert len(anomalies) == 1
        assert anomalies[0]["id_cable"] == "C2"

    def test_plusieurs_cables_non_conformes(self) -> None:
        """Chaque cable non conforme produit sa propre anomalie."""
        cable1 = _construire_cable_terre("C1")
        cable2 = _construire_cable_terre("C2", noeudreseau_href="NXXX")
        anomalies = controler_coherence_terre([cable1, cable2], frozenset({"N1"}))
        assert len(anomalies) == 2


# --------------------------------------------------------------------------- #
# Tests du rapport JSON
# --------------------------------------------------------------------------- #


class TestConstruireRapportJson:
    """Verifie la structure du rapport JSON."""

    def test_rapport_bloquant_avec_anomalies(self) -> None:
        """Le rapport est bloquant des qu'il y a au moins une anomalie."""
        rapport = construire_rapport_json([{"type": "test"}], 1, 0)
        assert rapport["bloquant"] is True
        assert rapport["nombre_anomalies"] == 1

    def test_rapport_non_bloquant_sans_anomalie(self) -> None:
        """Le rapport n'est pas bloquant sans anomalie."""
        rapport = construire_rapport_json([], 1, 1)
        assert rapport["bloquant"] is False
        assert rapport["nombre_anomalies"] == 0

    def test_rapport_contient_compteurs(self) -> None:
        """Le rapport contient les compteurs de cables et noeuds."""
        rapport = construire_rapport_json([], 3, 2)
        assert rapport["nombre_cables_terre"] == 3
        assert rapport["nombre_noeuds_terre"] == 2

    def test_rapport_identifiant_controle(self) -> None:
        """Le rapport contient l'identifiant du controle."""
        rapport = construire_rapport_json([], 0, 0)
        assert rapport["controle"] == "coherence_terre"


# --------------------------------------------------------------------------- #
# Tests du GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Verifie la construction du GeoJSON des ecarts."""

    def test_priorite_bloquant_si_anomalie(self) -> None:
        """L'anomalie doit avoir la priorite bloquant."""
        anomalies = [
            {
                "id_cable": "C1",
                "type": "cable_terre_sans_noeud_terre",
                "message": "Le cable terre C1 n'est lie a aucun noeud terre",
                "noeudreseau_href": None,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        features = geojson["features"]

        assert len(features) == 1
        assert features[0]["properties"]["priorite"] == "bloquant"
        assert features[0]["properties"]["id_cable"] == "C1"
        assert features[0]["geometry"] is None

    def test_aucune_feature_si_aucune_anomalie(self) -> None:
        """Aucune feature si aucune anomalie."""
        geojson = construire_geojson_ecarts([])
        assert geojson["features"] == []

    def test_crs_propage_si_present(self) -> None:
        """Le CRS est propage dans le FeatureCollection de sortie."""
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        """Aucun champ crs si non fourni."""
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson


# --------------------------------------------------------------------------- #
# Tests CLI bout en bout
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Verifie l'execution CLI avec ecriture des fichiers de sortie."""

    def _ecrire_geojson(self, chemin: str, features: list[dict[str, Any]]) -> None:
        """Ecrit un fichier GeoJSON FeatureCollection."""
        collection = {"type": "FeatureCollection", "features": features}
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(collection, f)

    def test_cli_cable_sans_noeud_genere_anomalie(self, tmp_path: Any) -> None:
        """Un cable sans noeudreseau_href produit un ecart bloquant."""
        cable = _construire_cable_terre("C1")
        noeud = _construire_noeud_terre("N1")
        self._ecrire_geojson(
            os.path.join(str(tmp_path), "RPD_CableTerre_Reco.geojson"), [cable]
        )
        self._ecrire_geojson(
            os.path.join(str(tmp_path), "RPD_Terre_Reco.geojson"), [noeud]
        )

        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        with open(resultat["rapport"], "r", encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["bloquant"] is True
        assert rapport["nombre_anomalies"] == 1

        with open(resultat["ecarts"], "r", encoding="utf-8") as f:
            geojson = json.load(f)
        assert len(geojson["features"]) == 1
        assert geojson["features"][0]["properties"]["priorite"] == "bloquant"

    def test_cli_cable_avec_noeud_valide(self, tmp_path: Any) -> None:
        """Un cable referencant un noeud existant ne genere pas d'anomalie."""
        cable = _construire_cable_terre("C1", noeudreseau_href="N1")
        noeud = _construire_noeud_terre("N1")
        self._ecrire_geojson(
            os.path.join(str(tmp_path), "RPD_CableTerre_Reco.geojson"), [cable]
        )
        self._ecrire_geojson(
            os.path.join(str(tmp_path), "RPD_Terre_Reco.geojson"), [noeud]
        )

        resultat = executer_controle_cli(str(tmp_path))
        with open(resultat["rapport"], "r", encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["bloquant"] is False
        assert rapport["nombre_anomalies"] == 0

    def test_cli_aucun_fichier_pas_d_anomalie(self, tmp_path: Any) -> None:
        """Sans fichier GeoJSON, le controle passe sans anomalie."""
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        with open(resultat["rapport"], "r", encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["bloquant"] is False

    def test_cli_sortie_separee(self, tmp_path: Any) -> None:
        """Les fichiers sont generes dans le repertoire de sortie specifie."""
        entree = os.path.join(str(tmp_path), "entree")
        sortie = os.path.join(str(tmp_path), "sortie")
        os.makedirs(entree)

        self._ecrire_geojson(os.path.join(entree, "RPD_CableTerre_Reco.geojson"), [])

        resultat = executer_controle_cli(entree, sortie)
        assert resultat["succes"] is True
        assert os.path.isdir(sortie)
        assert os.path.isfile(resultat["rapport"])
        assert os.path.isfile(resultat["ecarts"])
