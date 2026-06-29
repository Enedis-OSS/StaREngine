"""
Tests du controle E402 : coherence metier des relations cables de terre
et cheminements aeriens / de protection mecanique.

Couvre la regle unique du controle :
    Toute relation entre RPD_CableTerre_Reco et RPD_Aerien_Reco
    ou RPD_ProtectionMecanique_Reco est une anomalie.
"""

import json
import os
from typing import Any

from controle_e402 import (
    FICHIER_CABLE_TERRE,
    FICHIER_SORTIE,
    FICHIERS_CHEMINEMENT_INCOMPATIBLES,
    PRIORITE_ANOMALIE,
    TYPE_ANOMALIE,
    EntiteCheminement,
    _extraire_ids_cables_href,
    charger_cheminements_incompatibles,
    charger_ids_cables_terre,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# ---------------------------------------------------------------------------
# Helpers de construction des features de test
# ---------------------------------------------------------------------------


def _feature_cable_terre(identifiant: str) -> dict[str, Any]:
    """Feature GeoJSON minimale representant un cable de terre."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {
            "type": "LineString",
            "coordinates": [[0.0, 0.0], [1.0, 0.0]],
        },
    }


def _feature_cheminement(
    identifiant: str,
    cables_href: Any = None,
) -> dict[str, Any]:
    """Feature GeoJSON minimale representant un cheminement avec cables_href."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "cables_href": cables_href},
        "geometry": {
            "type": "LineString",
            "coordinates": [[0.0, 0.0], [2.0, 0.0]],
        },
    }


def _cheminement(
    identifiant: str = "id-chemin-1",
    fichier: str = "RPD_Aerien_Reco.geojson",
    ids_cables: list[str] | None = None,
    geometrie: dict[str, Any] | None = None,
) -> EntiteCheminement:
    """Construit une EntiteCheminement de test."""
    return EntiteCheminement(
        id_entite=identifiant,
        fichier=fichier,
        ids_cables=ids_cables or [],
        geometrie=geometrie,
    )


# ---------------------------------------------------------------------------
# TestExtraireIdsCablesHref
# ---------------------------------------------------------------------------


class TestExtraireIdsCablesHref:
    """Tests du parsing du champ cables_href dans le contexte de E402."""

    def test_chaine_unique(self):
        assert _extraire_ids_cables_href("id-cable-terre-1") == ["id-cable-terre-1"]

    def test_chaine_multiple_virgules(self):
        assert _extraire_ids_cables_href("id-1,id-2") == ["id-1", "id-2"]

    def test_none_retourne_liste_vide(self):
        assert _extraire_ids_cables_href(None) == []

    def test_chaine_vide_retourne_liste_vide(self):
        assert _extraire_ids_cables_href("") == []


# ---------------------------------------------------------------------------
# TestChargerIdsCablesTerre
# ---------------------------------------------------------------------------


class TestChargerIdsCablesTerre:
    """Tests du chargement des identifiants de cables de terre."""

    def test_fichier_absent_retourne_set_vide_et_flag(self, tmp_path):
        ids, absent = charger_ids_cables_terre(str(tmp_path))
        assert ids == set()
        assert absent is True

    def test_fichier_present_retourne_flag_false(self, tmp_path):
        chemin = tmp_path / FICHIER_CABLE_TERRE
        ecrire_collection(str(chemin), [])
        _, absent = charger_ids_cables_terre(str(tmp_path))
        assert absent is False

    def test_charge_identifiants(self, tmp_path):
        chemin = tmp_path / FICHIER_CABLE_TERRE
        ecrire_collection(
            str(chemin),
            [_feature_cable_terre("id-t1"), _feature_cable_terre("id-t2")],
        )
        ids, _ = charger_ids_cables_terre(str(tmp_path))
        assert ids == {"id-t1", "id-t2"}

    def test_entite_sans_id_ignoree(self, tmp_path):
        chemin = tmp_path / FICHIER_CABLE_TERRE
        feature_sans_id = {"type": "Feature", "properties": {}, "geometry": None}
        ecrire_collection(str(chemin), [feature_sans_id])
        ids, _ = charger_ids_cables_terre(str(tmp_path))
        assert len(ids) == 0

    def test_retourne_un_set(self, tmp_path):
        chemin = tmp_path / FICHIER_CABLE_TERRE
        ecrire_collection(str(chemin), [_feature_cable_terre("id-t1")])
        ids, _ = charger_ids_cables_terre(str(tmp_path))
        assert isinstance(ids, set)


# ---------------------------------------------------------------------------
# TestChargerCheminementsIncompatibles
# ---------------------------------------------------------------------------


class TestChargerCheminementsIncompatibles:
    """Tests du chargement des cheminements incompatibles avec les cables de terre."""

    def test_fichiers_absents_signales(self, tmp_path):
        _, fichiers_absents, _ = charger_cheminements_incompatibles(str(tmp_path))
        assert set(fichiers_absents) == set(FICHIERS_CHEMINEMENT_INCOMPATIBLES)

    def test_charge_aerien(self, tmp_path):
        chemin = tmp_path / "RPD_Aerien_Reco.geojson"
        ecrire_collection(str(chemin), [_feature_cheminement("id-a1", "id-t1")])
        cheminements, _, _ = charger_cheminements_incompatibles(str(tmp_path))
        assert any(c.id_entite == "id-a1" for c in cheminements)

    def test_charge_protection_mecanique(self, tmp_path):
        chemin = tmp_path / "RPD_ProtectionMecanique_Reco.geojson"
        ecrire_collection(str(chemin), [_feature_cheminement("id-pm1", "id-t1")])
        cheminements, _, _ = charger_cheminements_incompatibles(str(tmp_path))
        assert any(c.id_entite == "id-pm1" for c in cheminements)

    def test_cables_href_propagé(self, tmp_path):
        chemin = tmp_path / "RPD_Aerien_Reco.geojson"
        ecrire_collection(str(chemin), [_feature_cheminement("id-a1", "id-t1")])
        cheminements, _, _ = charger_cheminements_incompatibles(str(tmp_path))
        assert cheminements[0].ids_cables == ["id-t1"]

    def test_crs_propage(self, tmp_path):
        chemin = tmp_path / "RPD_Aerien_Reco.geojson"
        ecrire_collection_avec_crs(str(chemin), [], "EPSG:2154")
        _, _, crs = charger_cheminements_incompatibles(str(tmp_path))
        assert crs is not None
        assert "2154" in crs["properties"]["name"]

    def test_cheminements_des_deux_fichiers_fusionnes(self, tmp_path):
        (tmp_path / "RPD_Aerien_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-a1")],
                }
            )
        )
        (tmp_path / "RPD_ProtectionMecanique_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-pm1")],
                }
            )
        )
        cheminements, _, _ = charger_cheminements_incompatibles(str(tmp_path))
        ids = {c.id_entite for c in cheminements}
        assert "id-a1" in ids
        assert "id-pm1" in ids


# ---------------------------------------------------------------------------
# TestDetecterAnomalies
# ---------------------------------------------------------------------------


class TestDetecterAnomalies:
    """Tests de la detection des relations cable terre / cheminement incompatible."""

    def test_aucune_anomalie_si_pas_de_cable_terre(self):
        cheminements = [_cheminement(ids_cables=["id-electrique"])]
        assert detecter_anomalies(set(), cheminements) == []

    def test_aucune_anomalie_si_reference_non_cable_terre(self):
        ids_terre = {"id-t1"}
        cheminements = [_cheminement(ids_cables=["id-electrique"])]
        assert detecter_anomalies(ids_terre, cheminements) == []

    def test_anomalie_aerien_cable_terre(self):
        ids_terre = {"id-t1"}
        cheminements = [_cheminement("id-a1", "RPD_Aerien_Reco.geojson", ids_cables=["id-t1"])]
        anomalies = detecter_anomalies(ids_terre, cheminements)
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["type_anomalie"] == TYPE_ANOMALIE
        assert a["id_cable_terre"] == "id-t1"
        assert a["id_cheminement"] == "id-a1"
        assert a["fichier_cheminement"] == "RPD_Aerien_Reco.geojson"

    def test_anomalie_protection_mecanique_cable_terre(self):
        ids_terre = {"id-t1"}
        cheminements = [
            _cheminement(
                "id-pm1",
                "RPD_ProtectionMecanique_Reco.geojson",
                ids_cables=["id-t1"],
            )
        ]
        anomalies = detecter_anomalies(ids_terre, cheminements)
        assert len(anomalies) == 1
        assert anomalies[0]["fichier_cheminement"] == "RPD_ProtectionMecanique_Reco.geojson"

    def test_plusieurs_anomalies(self):
        ids_terre = {"id-t1", "id-t2"}
        cheminements = [
            _cheminement("id-a1", ids_cables=["id-t1"]),
            _cheminement("id-a2", ids_cables=["id-t2"]),
        ]
        assert len(detecter_anomalies(ids_terre, cheminements)) == 2

    def test_cheminement_multi_cables_signale_cable_terre_uniquement(self):
        ids_terre = {"id-t1"}
        cheminements = [_cheminement(ids_cables=["id-electrique", "id-t1"])]
        anomalies = detecter_anomalies(ids_terre, cheminements)
        assert len(anomalies) == 1
        assert anomalies[0]["id_cable_terre"] == "id-t1"

    def test_geometrie_propagee(self):
        geometrie = {"type": "LineString", "coordinates": [[0, 0], [1, 0]]}
        ids_terre = {"id-t1"}
        cheminements = [_cheminement(ids_cables=["id-t1"], geometrie=geometrie)]
        anomalie = detecter_anomalies(ids_terre, cheminements)[0]
        assert anomalie["geometrie"] == geometrie

    def test_aucune_anomalie_si_aucun_cheminement(self):
        assert detecter_anomalies({"id-t1"}, []) == []


# ---------------------------------------------------------------------------
# TestConstruireGeojsonEcarts
# ---------------------------------------------------------------------------


class TestConstruireGeojsonEcarts:
    """Tests de la construction du FeatureCollection GeoJSON de sortie."""

    def test_collection_vide(self):
        resultat = construire_geojson_ecarts([])
        assert resultat["type"] == "FeatureCollection"
        assert resultat["features"] == []

    def test_crs_absent_si_none(self):
        assert "crs" not in construire_geojson_ecarts([])

    def test_crs_propage(self):
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], crs)["crs"] == crs

    def test_proprietes_feature(self):
        anomalie = {
            "type_anomalie": TYPE_ANOMALIE,
            "fichier_cheminement": "RPD_Aerien_Reco.geojson",
            "id_cheminement": "id-a1",
            "id_cable_terre": "id-t1",
            "geometrie": None,
        }
        feature = construire_geojson_ecarts([anomalie])["features"][0]
        props = feature["properties"]
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["fichier_cheminement"] == "RPD_Aerien_Reco.geojson"
        assert props["id_cheminement"] == "id-a1"
        assert props["id_cable_terre"] == "id-t1"

    def test_id_cheminement_none_reste_none(self):
        anomalie = {
            "type_anomalie": TYPE_ANOMALIE,
            "fichier_cheminement": "RPD_Aerien_Reco.geojson",
            "id_cheminement": None,
            "id_cable_terre": "id-t1",
            "geometrie": None,
        }
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert props["id_cheminement"] is None

    def test_geometrie_conservee(self):
        geometrie = {"type": "LineString", "coordinates": [[0, 0], [1, 0]]}
        anomalie = {
            "type_anomalie": TYPE_ANOMALIE,
            "fichier_cheminement": "RPD_Aerien_Reco.geojson",
            "id_cheminement": "id-a1",
            "id_cable_terre": "id-t1",
            "geometrie": geometrie,
        }
        assert construire_geojson_ecarts([anomalie])["features"][0]["geometry"] == geometrie


# ---------------------------------------------------------------------------
# TestCli
# ---------------------------------------------------------------------------


class TestCli:
    """Tests de l'orchestration CLI (executer_controle_cli)."""

    def test_repertoire_inexistant(self, tmp_path):
        resultat = executer_controle_cli(str(tmp_path / "inexistant"))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_succes_sans_anomalie(self, tmp_path):
        id_terre = "id-t1"
        (tmp_path / FICHIER_CABLE_TERRE).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cable_terre(id_terre)],
                }
            )
        )
        # Aerien reference un cable electrique, pas un cable de terre
        (tmp_path / "RPD_Aerien_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-a1", "id-electrique")],
                }
            )
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_anomalie_detectee(self, tmp_path):
        id_terre = "id-t1"
        (tmp_path / FICHIER_CABLE_TERRE).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cable_terre(id_terre)],
                }
            )
        )
        (tmp_path / "RPD_Aerien_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-a1", id_terre)],
                }
            )
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_fichier_sortie_cree(self, tmp_path):
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(tmp_path / FICHIER_SORTIE)

    def test_cable_terre_absent_rapporte(self, tmp_path):
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["cable_terre_absent"] is True

    def test_fichiers_cheminement_absents_rapportes(self, tmp_path):
        resultat = executer_controle_cli(str(tmp_path))
        assert set(resultat["fichiers_cheminement_absents"]) == set(FICHIERS_CHEMINEMENT_INCOMPATIBLES)

    def test_compteurs_dans_rapport(self, tmp_path):
        id_terre = "id-t1"
        (tmp_path / FICHIER_CABLE_TERRE).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cable_terre(id_terre)],
                }
            )
        )
        (tmp_path / "RPD_Aerien_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-a1", id_terre)],
                }
            )
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_cables_terre_analyses"] == 1
        assert resultat["nombre_cheminements_analyses"] == 1

    def test_sortie_personnalisee(self, tmp_path):
        dossier_sortie = tmp_path / "sortie"
        dossier_sortie.mkdir()
        executer_controle_cli(str(tmp_path), str(dossier_sortie))
        assert os.path.isfile(dossier_sortie / FICHIER_SORTIE)
