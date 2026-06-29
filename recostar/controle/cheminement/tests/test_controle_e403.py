"""
Tests du controle E403 : coherence du mode d'implantation des cables electriques.

Couvre la regle unique du controle :
    Tout cable electrique simultanement associe a un cheminement aerien et
    a un cheminement souterrain (Fourreau, PleineTerre, ProtectionMecanique)
    est signale comme anomalie.
"""

import json
import os
from typing import Any

from controle_e403 import (
    FICHIER_AERIEN,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_SORTIE,
    FICHIERS_CHEMINEMENT,
    PRIORITE_ANOMALIE,
    TYPE_ANOMALIE,
    EntiteCable,
    EntiteCheminement,
    ReferenceCheminement,
    _extraire_ids_cables_href,
    charger_cables_electriques,
    charger_cheminements,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
    indexer_references,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# ---------------------------------------------------------------------------
# Helpers de construction des objets de test
# ---------------------------------------------------------------------------


def _feature_cable_electrique(identifiant: str) -> dict[str, Any]:
    """Feature GeoJSON minimale representant un cable electrique."""
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
    identifiant: str = "id-ce-1",
    geometrie: dict[str, Any] | None = None,
) -> EntiteCable:
    """Construit une EntiteCable de test."""
    return EntiteCable(id_entite=identifiant, geometrie=geometrie)


def _cheminement(
    identifiant: str = "id-ch-1",
    fichier: str = FICHIER_AERIEN,
    ids_cables: list[str] | None = None,
) -> EntiteCheminement:
    """Construit une EntiteCheminement de test."""
    return EntiteCheminement(
        id_entite=identifiant,
        fichier=fichier,
        ids_cables=ids_cables or [],
    )


def _ref(
    id_cheminement: str | None = "id-ch-1",
    fichier: str = FICHIER_AERIEN,
) -> ReferenceCheminement:
    """Construit une ReferenceCheminement de test."""
    return ReferenceCheminement(id_cheminement=id_cheminement, fichier=fichier)


# ---------------------------------------------------------------------------
# TestExtraireIdsCablesHref
# ---------------------------------------------------------------------------


class TestExtraireIdsCablesHref:
    """Tests du parsing du champ cables_href dans le contexte de E403."""

    def test_chaine_unique(self):
        assert _extraire_ids_cables_href("id-ce-1") == ["id-ce-1"]

    def test_chaine_multiple_virgules(self):
        assert _extraire_ids_cables_href("id-1,id-2") == ["id-1", "id-2"]

    def test_none_retourne_liste_vide(self):
        assert _extraire_ids_cables_href(None) == []

    def test_chaine_vide_retourne_liste_vide(self):
        assert _extraire_ids_cables_href("") == []


# ---------------------------------------------------------------------------
# TestChargerCablesElectriques
# ---------------------------------------------------------------------------


class TestChargerCablesElectriques:
    """Tests du chargement des entites cable electrique."""

    def test_fichier_absent_retourne_dict_vide_et_flag(self, tmp_path):
        cables, absent = charger_cables_electriques(str(tmp_path))
        assert cables == {}
        assert absent is True

    def test_fichier_present_retourne_flag_false(self, tmp_path):
        chemin = tmp_path / FICHIER_CABLE_ELECTRIQUE
        ecrire_collection(str(chemin), [])
        _, absent = charger_cables_electriques(str(tmp_path))
        assert absent is False

    def test_charge_identifiants(self, tmp_path):
        chemin = tmp_path / FICHIER_CABLE_ELECTRIQUE
        ecrire_collection(
            str(chemin),
            [
                _feature_cable_electrique("id-ce-1"),
                _feature_cable_electrique("id-ce-2"),
            ],
        )
        cables, _ = charger_cables_electriques(str(tmp_path))
        assert set(cables.keys()) == {"id-ce-1", "id-ce-2"}

    def test_geometrie_conservee(self, tmp_path):
        chemin = tmp_path / FICHIER_CABLE_ELECTRIQUE
        ecrire_collection(str(chemin), [_feature_cable_electrique("id-ce-1")])
        cables, _ = charger_cables_electriques(str(tmp_path))
        assert cables["id-ce-1"].geometrie is not None
        assert cables["id-ce-1"].geometrie["type"] == "LineString"

    def test_entite_sans_id_ignoree(self, tmp_path):
        chemin = tmp_path / FICHIER_CABLE_ELECTRIQUE
        feature_sans_id = {"type": "Feature", "properties": {}, "geometry": None}
        ecrire_collection(str(chemin), [feature_sans_id])
        cables, _ = charger_cables_electriques(str(tmp_path))
        assert len(cables) == 0


# ---------------------------------------------------------------------------
# TestChargerCheminements
# ---------------------------------------------------------------------------


class TestChargerCheminements:
    """Tests du chargement des entites de cheminement (aerien + souterrains)."""

    def test_tous_fichiers_absents_signales(self, tmp_path):
        _, fichiers_absents, _ = charger_cheminements(str(tmp_path))
        assert set(fichiers_absents) == set(FICHIERS_CHEMINEMENT)

    def test_charge_cheminement_aerien(self, tmp_path):
        chemin = tmp_path / FICHIER_AERIEN
        ecrire_collection(str(chemin), [_feature_cheminement("id-a1", "id-ce-1")])
        cheminements, _, _ = charger_cheminements(str(tmp_path))
        assert any(c.id_entite == "id-a1" for c in cheminements)

    def test_charge_cheminement_souterrain(self, tmp_path):
        chemin = tmp_path / "RPD_Fourreau_Reco.geojson"
        ecrire_collection(str(chemin), [_feature_cheminement("id-f1", "id-ce-1")])
        cheminements, _, _ = charger_cheminements(str(tmp_path))
        assert any(c.id_entite == "id-f1" for c in cheminements)

    def test_cables_href_extrait(self, tmp_path):
        chemin = tmp_path / FICHIER_AERIEN
        ecrire_collection(str(chemin), [_feature_cheminement("id-a1", "id-ce-1")])
        cheminements, _, _ = charger_cheminements(str(tmp_path))
        assert cheminements[0].ids_cables == ["id-ce-1"]

    def test_crs_propage(self, tmp_path):
        chemin = tmp_path / FICHIER_AERIEN
        ecrire_collection_avec_crs(str(chemin), [], "EPSG:2154")
        _, _, crs = charger_cheminements(str(tmp_path))
        assert crs is not None
        assert "2154" in crs["properties"]["name"]

    def test_tous_fichiers_fusionnes(self, tmp_path):
        (tmp_path / FICHIER_AERIEN).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-a1")],
                }
            )
        )
        (tmp_path / "RPD_Fourreau_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-f1")],
                }
            )
        )
        cheminements, _, _ = charger_cheminements(str(tmp_path))
        ids = {c.id_entite for c in cheminements}
        assert "id-a1" in ids
        assert "id-f1" in ids


# ---------------------------------------------------------------------------
# TestIndexerReferences
# ---------------------------------------------------------------------------


class TestIndexerReferences:
    """Tests de la construction des index inverses aerien et souterrain."""

    def test_cheminement_aerien_indexe_dans_refs_aerien(self):
        ch = _cheminement("id-a1", FICHIER_AERIEN, ids_cables=["id-ce-1"])
        refs_aerien, refs_souterrain = indexer_references([ch], {"id-ce-1"})
        assert "id-ce-1" in refs_aerien
        assert "id-ce-1" not in refs_souterrain

    def test_cheminement_souterrain_indexe_dans_refs_souterrain(self):
        ch = _cheminement("id-f1", "RPD_Fourreau_Reco.geojson", ids_cables=["id-ce-1"])
        refs_aerien, refs_souterrain = indexer_references([ch], {"id-ce-1"})
        assert "id-ce-1" not in refs_aerien
        assert "id-ce-1" in refs_souterrain

    def test_cable_non_electrique_ignore(self):
        ch = _cheminement("id-a1", FICHIER_AERIEN, ids_cables=["id-terre-1"])
        refs_aerien, refs_souterrain = indexer_references([ch], {"id-ce-1"})
        assert len(refs_aerien) == 0
        assert len(refs_souterrain) == 0

    def test_plusieurs_cheminements_meme_cable(self):
        cheminements = [
            _cheminement("id-a1", FICHIER_AERIEN, ids_cables=["id-ce-1"]),
            _cheminement("id-a2", FICHIER_AERIEN, ids_cables=["id-ce-1"]),
        ]
        refs_aerien, _ = indexer_references(cheminements, {"id-ce-1"})
        assert len(refs_aerien["id-ce-1"]) == 2

    def test_aeriens_et_souterrains_separes(self):
        cheminements = [
            _cheminement("id-a1", FICHIER_AERIEN, ids_cables=["id-ce-1"]),
            _cheminement("id-f1", "RPD_Fourreau_Reco.geojson", ids_cables=["id-ce-1"]),
        ]
        refs_aerien, refs_souterrain = indexer_references(cheminements, {"id-ce-1"})
        assert "id-ce-1" in refs_aerien
        assert "id-ce-1" in refs_souterrain

    def test_fichier_conserve_dans_reference(self):
        ch = _cheminement("id-f1", "RPD_Fourreau_Reco.geojson", ids_cables=["id-ce-1"])
        _, refs_souterrain = indexer_references([ch], {"id-ce-1"})
        assert refs_souterrain["id-ce-1"][0].fichier == "RPD_Fourreau_Reco.geojson"

    def test_identifiant_cheminement_conserve_dans_reference(self):
        ch = _cheminement("id-a1", FICHIER_AERIEN, ids_cables=["id-ce-1"])
        refs_aerien, _ = indexer_references([ch], {"id-ce-1"})
        assert refs_aerien["id-ce-1"][0].id_cheminement == "id-a1"

    def test_cheminements_sans_cables_href_ignores(self):
        ch = _cheminement("id-a1", FICHIER_AERIEN, ids_cables=[])
        refs_aerien, refs_souterrain = indexer_references([ch], {"id-ce-1"})
        assert len(refs_aerien) == 0


# ---------------------------------------------------------------------------
# TestDetecterAnomalies
# ---------------------------------------------------------------------------


class TestDetecterAnomalies:
    """Tests de la detection des cables electriques a implantation incoherente."""

    def test_aucune_anomalie_si_cable_uniquement_aerien(self):
        cables = {"id-ce-1": _cable()}
        refs_aerien = {"id-ce-1": [_ref()]}
        assert detecter_anomalies(cables, refs_aerien, {}) == []

    def test_aucune_anomalie_si_cable_uniquement_souterrain(self):
        cables = {"id-ce-1": _cable()}
        refs_souterrain = {"id-ce-1": [_ref(fichier="RPD_Fourreau_Reco.geojson")]}
        assert detecter_anomalies(cables, {}, refs_souterrain) == []

    def test_anomalie_si_cable_dans_les_deux_categories(self):
        cables = {"id-ce-1": _cable()}
        refs_aerien = {"id-ce-1": [_ref()]}
        refs_souterrain = {"id-ce-1": [_ref(fichier="RPD_Fourreau_Reco.geojson")]}
        anomalies = detecter_anomalies(cables, refs_aerien, refs_souterrain)
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_ANOMALIE
        assert anomalies[0]["id_cable_electrique"] == "id-ce-1"

    def test_seuls_cables_incoherents_signales(self):
        cables = {
            "id-ce-1": _cable("id-ce-1"),  # aerien + souterrain → anomalie
            "id-ce-2": _cable("id-ce-2"),  # aerien seulement → OK
        }
        refs_aerien = {
            "id-ce-1": [_ref("id-a1")],
            "id-ce-2": [_ref("id-a2")],
        }
        refs_souterrain = {"id-ce-1": [_ref("id-f1", "RPD_Fourreau_Reco.geojson")]}
        anomalies = detecter_anomalies(cables, refs_aerien, refs_souterrain)
        assert len(anomalies) == 1
        assert anomalies[0]["id_cable_electrique"] == "id-ce-1"

    def test_anomalie_contient_les_deux_listes_de_references(self):
        cables = {"id-ce-1": _cable()}
        refs_aerien = {"id-ce-1": [_ref("id-a1"), _ref("id-a2")]}
        refs_souterrain = {"id-ce-1": [_ref("id-f1", "RPD_Fourreau_Reco.geojson")]}
        anomalie = detecter_anomalies(cables, refs_aerien, refs_souterrain)[0]
        assert len(anomalie["cheminements_aeriens"]) == 2
        assert len(anomalie["cheminements_souterrains"]) == 1

    def test_geometrie_cable_propagee(self):
        geometrie = {"type": "LineString", "coordinates": [[0, 0], [1, 0]]}
        cables = {"id-ce-1": _cable(geometrie=geometrie)}
        refs_aerien = {"id-ce-1": [_ref()]}
        refs_souterrain = {"id-ce-1": [_ref(fichier="RPD_Fourreau_Reco.geojson")]}
        anomalie = detecter_anomalies(cables, refs_aerien, refs_souterrain)[0]
        assert anomalie["geometrie"] == geometrie

    def test_aucune_anomalie_si_aucun_cheminement(self):
        assert detecter_anomalies({"id-ce-1": _cable()}, {}, {}) == []


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

    def test_proprietes_communes(self):
        anomalie = {
            "type_anomalie": TYPE_ANOMALIE,
            "id_cable_electrique": "id-ce-1",
            "cheminements_aeriens": [_ref("id-a1")],
            "cheminements_souterrains": [_ref("id-f1", "RPD_Fourreau_Reco.geojson")],
            "geometrie": None,
        }
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_cable_electrique"] == "id-ce-1"

    def test_compteurs_et_ids_csv(self):
        anomalie = {
            "type_anomalie": TYPE_ANOMALIE,
            "id_cable_electrique": "id-ce-1",
            "cheminements_aeriens": [_ref("id-a1"), _ref("id-a2")],
            "cheminements_souterrains": [_ref("id-f1", "RPD_Fourreau_Reco.geojson")],
            "geometrie": None,
        }
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert props["nb_cheminements_aeriens"] == 2
        assert "id-a1" in props["ids_cheminements_aeriens"]
        assert "id-a2" in props["ids_cheminements_aeriens"]
        assert props["nb_cheminements_souterrains"] == 1
        assert props["ids_cheminements_souterrains"] == "id-f1"

    def test_fichiers_souterrains_en_csv(self):
        anomalie = {
            "type_anomalie": TYPE_ANOMALIE,
            "id_cable_electrique": "id-ce-1",
            "cheminements_aeriens": [_ref("id-a1")],
            "cheminements_souterrains": [
                _ref("id-f1", "RPD_Fourreau_Reco.geojson"),
                _ref("id-pt1", "RPD_PleineTerre_Reco.geojson"),
            ],
            "geometrie": None,
        }
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert "RPD_Fourreau_Reco.geojson" in props["fichiers_cheminements_souterrains"]
        assert "RPD_PleineTerre_Reco.geojson" in props["fichiers_cheminements_souterrains"]

    def test_geometrie_cable_conservee(self):
        geometrie = {"type": "LineString", "coordinates": [[0, 0], [1, 0]]}
        anomalie = {
            "type_anomalie": TYPE_ANOMALIE,
            "id_cable_electrique": "id-ce-1",
            "cheminements_aeriens": [_ref()],
            "cheminements_souterrains": [_ref(fichier="RPD_Fourreau_Reco.geojson")],
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

    def test_succes_sans_anomalie_cable_uniquement_aerien(self, tmp_path):
        id_ce = "id-ce-1"
        (tmp_path / FICHIER_CABLE_ELECTRIQUE).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cable_electrique(id_ce)],
                }
            )
        )
        (tmp_path / FICHIER_AERIEN).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-a1", id_ce)],
                }
            )
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_anomalie_detectee_aerien_et_souterrain(self, tmp_path):
        id_ce = "id-ce-1"
        (tmp_path / FICHIER_CABLE_ELECTRIQUE).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cable_electrique(id_ce)],
                }
            )
        )
        (tmp_path / FICHIER_AERIEN).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-a1", id_ce)],
                }
            )
        )
        (tmp_path / "RPD_Fourreau_Reco.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-f1", id_ce)],
                }
            )
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_fichier_sortie_cree(self, tmp_path):
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(tmp_path / FICHIER_SORTIE)

    def test_cable_electrique_absent_rapporte(self, tmp_path):
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["cable_electrique_absent"] is True

    def test_fichiers_cheminement_absents_rapportes(self, tmp_path):
        resultat = executer_controle_cli(str(tmp_path))
        assert set(resultat["fichiers_cheminement_absents"]) == set(FICHIERS_CHEMINEMENT)

    def test_compteurs_dans_rapport(self, tmp_path):
        id_ce = "id-ce-1"
        (tmp_path / FICHIER_CABLE_ELECTRIQUE).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cable_electrique(id_ce)],
                }
            )
        )
        (tmp_path / FICHIER_AERIEN).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [_feature_cheminement("id-a1", id_ce)],
                }
            )
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_cables_electriques_analyses"] == 1
        assert resultat["nombre_cheminements_analyses"] == 1

    def test_sortie_personnalisee(self, tmp_path):
        dossier_sortie = tmp_path / "sortie"
        dossier_sortie.mkdir()
        executer_controle_cli(str(tmp_path), str(dossier_sortie))
        assert os.path.isfile(dossier_sortie / FICHIER_SORTIE)
