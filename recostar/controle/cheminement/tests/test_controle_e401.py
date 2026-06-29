"""
Tests du controle E401 : integrite des relations cables/cheminements.

Couvre les quatre regles du controle :
  - Regle 4a : cheminement sans cables_href
  - Regle 4b : cheminement referençant plusieurs cables
  - Regle 2  : reference cables_href sans cable correspondant
  - Regles 1/3 : cable non reference par aucun cheminement
"""

import json
import os
from typing import Any

from controle_e401 import (
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    EntiteCable,
    EntiteCheminement,
    _analyser_cheminement,
    _extraire_ids_cables_href,
    charger_cables,
    charger_cheminements,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# ---------------------------------------------------------------------------
# Helpers de construction des features de test
# ---------------------------------------------------------------------------


def _feature_cable(identifiant: str) -> dict[str, Any]:
    """Feature GeoJSON minimale representant un cable."""
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


def _cable(
    identifiant: str = "id-cable-1",
    fichier: str = "RPD_CableElectrique_Reco.geojson",
    geometrie: dict[str, Any] | None = None,
) -> EntiteCable:
    """Construit une EntiteCable de test."""
    return EntiteCable(
        id_entite=identifiant,
        fichier=fichier,
        geometrie=geometrie,
    )


def _cheminement(
    identifiant: str = "id-chemin-1",
    fichier: str = "RPD_Fourreau_Reco.geojson",
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
    """Tests du parsing du champ cables_href."""

    def test_chaine_unique(self):
        assert _extraire_ids_cables_href("id-cable-1") == ["id-cable-1"]

    def test_chaine_multiple_virgules(self):
        assert _extraire_ids_cables_href("id-1,id-2,id-3") == ["id-1", "id-2", "id-3"]

    def test_chaine_avec_espaces_apres_virgule(self):
        assert _extraire_ids_cables_href("id-1, id-2") == ["id-1", "id-2"]

    def test_none_retourne_liste_vide(self):
        assert _extraire_ids_cables_href(None) == []

    def test_chaine_vide_retourne_liste_vide(self):
        assert _extraire_ids_cables_href("") == []

    def test_liste_retourne_liste(self):
        assert _extraire_ids_cables_href(["id-1", "id-2"]) == ["id-1", "id-2"]

    def test_liste_ignore_none(self):
        assert _extraire_ids_cables_href(["id-1", None, "id-2"]) == ["id-1", "id-2"]

    def test_entier_retourne_liste_vide(self):
        assert _extraire_ids_cables_href(42) == []


# ---------------------------------------------------------------------------
# TestChargerCables
# ---------------------------------------------------------------------------


class TestChargerCables:
    """Tests du chargement des entites cable depuis les fichiers GeoJSON."""

    def test_fichier_absent_signale(self, tmp_path):
        _, fichiers_absents = charger_cables(str(tmp_path))
        assert "RPD_CableElectrique_Reco.geojson" in fichiers_absents

    def test_charge_entites_avec_id(self, tmp_path):
        chemin = tmp_path / "RPD_CableElectrique_Reco.geojson"
        ecrire_collection(str(chemin), [_feature_cable("id-c1"), _feature_cable("id-c2")])
        cables, _ = charger_cables(str(tmp_path))
        assert "id-c1" in cables
        assert "id-c2" in cables
        assert cables["id-c1"].fichier == "RPD_CableElectrique_Reco.geojson"

    def test_entite_sans_id_ignoree(self, tmp_path):
        chemin = tmp_path / "RPD_CableElectrique_Reco.geojson"
        feature_sans_id = {
            "type": "Feature",
            "properties": {},
            "geometry": None,
        }
        ecrire_collection(str(chemin), [feature_sans_id])
        cables, _ = charger_cables(str(tmp_path))
        assert len(cables) == 0

    def test_cables_de_plusieurs_fichiers_fusionnes(self, tmp_path):
        (tmp_path / "RPD_CableElectrique_Reco.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": [_feature_cable("id-e1")]})
        )
        (tmp_path / "RPD_CableTerre_Reco.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": [_feature_cable("id-t1")]})
        )
        cables, _ = charger_cables(str(tmp_path))
        assert "id-e1" in cables
        assert "id-t1" in cables

    def test_geometrie_conservee(self, tmp_path):
        chemin = tmp_path / "RPD_CableElectrique_Reco.geojson"
        ecrire_collection(str(chemin), [_feature_cable("id-c1")])
        cables, _ = charger_cables(str(tmp_path))
        assert cables["id-c1"].geometrie is not None
        assert cables["id-c1"].geometrie["type"] == "LineString"


# ---------------------------------------------------------------------------
# TestChargerCheminements
# ---------------------------------------------------------------------------


class TestChargerCheminements:
    """Tests du chargement des entites de cheminement depuis les fichiers GeoJSON."""

    def test_fichier_absent_signale(self, tmp_path):
        _, fichiers_absents, _ = charger_cheminements(str(tmp_path))
        assert "RPD_Fourreau_Reco.geojson" in fichiers_absents

    def test_charge_cables_href_en_liste(self, tmp_path):
        chemin = tmp_path / "RPD_Fourreau_Reco.geojson"
        ecrire_collection(str(chemin), [_feature_cheminement("id-f1", "id-c1")])
        cheminements, _, _ = charger_cheminements(str(tmp_path))
        assert cheminements[0].ids_cables == ["id-c1"]

    def test_cables_href_null_donne_liste_vide(self, tmp_path):
        chemin = tmp_path / "RPD_Fourreau_Reco.geojson"
        ecrire_collection(str(chemin), [_feature_cheminement("id-f1", None)])
        cheminements, _, _ = charger_cheminements(str(tmp_path))
        assert cheminements[0].ids_cables == []

    def test_crs_propage(self, tmp_path):
        chemin = tmp_path / "RPD_Fourreau_Reco.geojson"
        ecrire_collection_avec_crs(str(chemin), [], "EPSG:2154")
        _, _, crs = charger_cheminements(str(tmp_path))
        assert crs is not None
        assert "2154" in crs["properties"]["name"]

    def test_cheminements_de_plusieurs_fichiers_fusionnes(self, tmp_path):
        (tmp_path / "RPD_Fourreau_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-f1", "id-c1")],
                }
            )
        )
        (tmp_path / "RPD_Aerien_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-a1", "id-c2")],
                }
            )
        )
        cheminements, _, _ = charger_cheminements(str(tmp_path))
        ids = [c.id_entite for c in cheminements]
        assert "id-f1" in ids
        assert "id-a1" in ids


# ---------------------------------------------------------------------------
# TestAnalyserCheminement
# ---------------------------------------------------------------------------


class TestAnalyserCheminement:
    """Tests de la detection des anomalies sur un cheminement individuel."""

    def test_reference_valide_aucune_anomalie(self):
        ch = _cheminement(ids_cables=["id-c1"])
        anomalies = _analyser_cheminement(ch, {"id-c1"})
        assert anomalies == []

    def test_sans_cable_retourne_anomalie(self):
        ch = _cheminement(ids_cables=[])
        anomalies = _analyser_cheminement(ch, {"id-c1"})
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == "cheminement_sans_cable"
        assert anomalies[0]["id_cheminement"] == "id-chemin-1"

    def test_multi_cables_retourne_anomalie(self):
        ch = _cheminement(ids_cables=["id-c1", "id-c2"])
        anomalies = _analyser_cheminement(ch, {"id-c1", "id-c2"})
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == "cheminement_multi_cables"
        assert anomalies[0]["nb_cables"] == 2

    def test_reference_invalide_retourne_anomalie(self):
        ch = _cheminement(ids_cables=["id-inexistant"])
        anomalies = _analyser_cheminement(ch, {"id-c1"})
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == "reference_orpheline"
        assert anomalies[0]["cables_href_invalide"] == "id-inexistant"

    def test_multi_cables_invalides_cumule_anomalies(self):
        ch = _cheminement(ids_cables=["id-x", "id-y"])
        anomalies = _analyser_cheminement(ch, set())
        types = {a["type_anomalie"] for a in anomalies}
        # cardinalite + deux references orphelines
        assert "cheminement_multi_cables" in types
        assert "reference_orpheline" in types
        nb_orphelines = sum(1 for a in anomalies if a["type_anomalie"] == "reference_orpheline")
        assert nb_orphelines == 2

    def test_fichier_cheminement_propagé(self):
        ch = _cheminement(fichier="RPD_Aerien_Reco.geojson", ids_cables=[])
        anomalie = _analyser_cheminement(ch, set())[0]
        assert anomalie["fichier_cheminement"] == "RPD_Aerien_Reco.geojson"


# ---------------------------------------------------------------------------
# TestDetecterAnomalies
# ---------------------------------------------------------------------------


class TestDetecterAnomalies:
    """Tests de l'orchestration de la detection de toutes les anomalies."""

    def test_aucune_anomalie(self):
        cables = {"id-c1": _cable("id-c1")}
        cheminements = [_cheminement(ids_cables=["id-c1"])]
        assert detecter_anomalies(cables, cheminements) == []

    def test_cable_non_reference(self):
        cables = {"id-c1": _cable("id-c1")}
        anomalies = detecter_anomalies(cables, [])
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == "cable_non_reference"
        assert anomalies[0]["id_cable"] == "id-c1"

    def test_reference_orpheline(self):
        cables = {"id-c1": _cable("id-c1")}
        cheminements = [_cheminement(ids_cables=["id-inexistant"])]
        anomalies = detecter_anomalies(cables, cheminements)
        types = {a["type_anomalie"] for a in anomalies}
        assert "reference_orpheline" in types
        # id-c1 est non reference aussi
        assert "cable_non_reference" in types

    def test_cheminement_sans_cable(self):
        cables = {"id-c1": _cable("id-c1")}
        cheminements = [_cheminement(ids_cables=[])]
        anomalies = detecter_anomalies(cables, cheminements)
        types = {a["type_anomalie"] for a in anomalies}
        assert "cheminement_sans_cable" in types
        assert "cable_non_reference" in types

    def test_cheminement_multi_cables(self):
        cables = {
            "id-c1": _cable("id-c1"),
            "id-c2": _cable("id-c2"),
        }
        cheminements = [_cheminement(ids_cables=["id-c1", "id-c2"])]
        anomalies = detecter_anomalies(cables, cheminements)
        types = {a["type_anomalie"] for a in anomalies}
        assert "cheminement_multi_cables" in types
        # Les deux cables sont references malgre la violation de cardinalite
        assert "cable_non_reference" not in types

    def test_cables_reference_valide_non_signales(self):
        cables = {
            "id-c1": _cable("id-c1"),
            "id-c2": _cable("id-c2"),
        }
        cheminements = [
            _cheminement("id-f1", ids_cables=["id-c1"]),
            _cheminement("id-f2", ids_cables=["id-c2"]),
        ]
        assert detecter_anomalies(cables, cheminements) == []

    def test_plusieurs_cables_dont_un_non_reference(self):
        cables = {
            "id-c1": _cable("id-c1"),
            "id-c2": _cable("id-c2"),
        }
        cheminements = [_cheminement(ids_cables=["id-c1"])]
        anomalies = detecter_anomalies(cables, cheminements)
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == "cable_non_reference"
        assert anomalies[0]["id_cable"] == "id-c2"

    def test_aucun_cheminement_tous_cables_signales(self):
        cables = {
            "id-c1": _cable("id-c1"),
            "id-c2": _cable("id-c2"),
        }
        anomalies = detecter_anomalies(cables, [])
        ids_signales = {a["id_cable"] for a in anomalies}
        assert ids_signales == {"id-c1", "id-c2"}


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
        resultat = construire_geojson_ecarts([])
        assert "crs" not in resultat

    def test_crs_propage(self):
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        resultat = construire_geojson_ecarts([], crs)
        assert resultat["crs"] == crs

    def test_feature_cable_non_reference(self):
        anomalie = {
            "type_anomalie": "cable_non_reference",
            "fichier_cable": "RPD_CableElectrique_Reco.geojson",
            "id_cable": "id-c1",
            "geometrie": None,
        }
        resultat = construire_geojson_ecarts([anomalie])
        feature = resultat["features"][0]
        props = feature["properties"]
        assert props["type_anomalie"] == "cable_non_reference"
        assert props["id_cable"] == "id-c1"
        assert props["fichier_cable"] == "RPD_CableElectrique_Reco.geojson"
        assert props["priorite"] == PRIORITE_ANOMALIE

    def test_feature_reference_orpheline(self):
        anomalie = {
            "type_anomalie": "reference_orpheline",
            "fichier_cheminement": "RPD_Fourreau_Reco.geojson",
            "id_cheminement": "id-f1",
            "cables_href_invalide": "id-inexistant",
            "geometrie": None,
        }
        resultat = construire_geojson_ecarts([anomalie])
        props = resultat["features"][0]["properties"]
        assert props["type_anomalie"] == "reference_orpheline"
        assert props["cables_href_invalide"] == "id-inexistant"
        assert props["id_cheminement"] == "id-f1"

    def test_feature_cheminement_sans_cable(self):
        anomalie = {
            "type_anomalie": "cheminement_sans_cable",
            "fichier_cheminement": "RPD_PleineTerre_Reco.geojson",
            "id_cheminement": "id-p1",
            "geometrie": None,
        }
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert props["type_anomalie"] == "cheminement_sans_cable"
        assert props["id_cheminement"] == "id-p1"

    def test_feature_cheminement_multi_cables(self):
        anomalie = {
            "type_anomalie": "cheminement_multi_cables",
            "fichier_cheminement": "RPD_Aerien_Reco.geojson",
            "id_cheminement": "id-a1",
            "nb_cables": 2,
            "cables_href": "id-c1,id-c2",
            "geometrie": None,
        }
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert props["type_anomalie"] == "cheminement_multi_cables"
        assert props["nb_cables"] == 2
        assert props["cables_href"] == "id-c1,id-c2"

    def test_geometrie_conservee(self):
        geometrie = {"type": "LineString", "coordinates": [[0, 0], [1, 0]]}
        anomalie = {
            "type_anomalie": "cable_non_reference",
            "fichier_cable": "RPD_CableElectrique_Reco.geojson",
            "id_cable": "id-c1",
            "geometrie": geometrie,
        }
        feature = construire_geojson_ecarts([anomalie])["features"][0]
        assert feature["geometry"] == geometrie


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
        cable_id = "idabc"
        (tmp_path / "RPD_CableElectrique_Reco.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": [_feature_cable(cable_id)]})
        )
        (tmp_path / "RPD_Fourreau_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-f1", cable_id)],
                }
            )
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_fichier_sortie_cree(self, tmp_path):
        (tmp_path / "RPD_CableElectrique_Reco.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": []})
        )
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(tmp_path / FICHIER_SORTIE)

    def test_anomalies_par_type_dans_rapport(self, tmp_path):
        cable_id = "id-c1"
        (tmp_path / "RPD_CableElectrique_Reco.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": [_feature_cable(cable_id)]})
        )
        # Cheminement sans cables_href
        (tmp_path / "RPD_Fourreau_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-f1", None)],
                }
            )
        )
        resultat = executer_controle_cli(str(tmp_path))
        par_type = resultat["anomalies_par_type"]
        assert par_type.get("cheminement_sans_cable", 0) >= 1
        assert par_type.get("cable_non_reference", 0) >= 1

    def test_fichiers_absents_rapportes(self, tmp_path):
        resultat = executer_controle_cli(str(tmp_path))
        assert "RPD_CableElectrique_Reco.geojson" in resultat["fichiers_cables_absents"]
        assert "RPD_Fourreau_Reco.geojson" in resultat["fichiers_cheminement_absents"]

    def test_sortie_personnalisee(self, tmp_path):
        dossier_sortie = tmp_path / "sortie"
        dossier_sortie.mkdir()
        executer_controle_cli(str(tmp_path), str(dossier_sortie))
        assert os.path.isfile(dossier_sortie / FICHIER_SORTIE)

    def test_compteurs_cables_et_cheminements(self, tmp_path):
        cable_id = "id-c1"
        (tmp_path / "RPD_CableElectrique_Reco.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": [_feature_cable(cable_id)]})
        )
        (tmp_path / "RPD_Fourreau_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-f1", cable_id)],
                }
            )
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_cables_analyses"] == 1
        assert resultat["nombre_cheminements_analyses"] == 1
