"""
Tests unitaires du module utils_geojson.

Couvre les fonctions partagees par tous les controles altimetriques :
lecture, ecriture, listage de fichiers et extraction d'identifiant.
"""

import json
import os
from typing import Any

from utils_geojson import (
    EXTENSION_GEOJSON,
    PREFIXE_ECARTS,
    ProfilEcarts,
    ecrire_geojson,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    lister_fichiers_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# --------------------------------------------------------------------------- #
# Tests de lire_geojson
# --------------------------------------------------------------------------- #


class TestLireGeojson:
    """Tests de la lecture de fichiers GeoJSON."""

    def test_charge_fichier_existant(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "data.geojson")
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": []}, f)
        contenu = lire_geojson(chemin)
        assert contenu is not None
        assert contenu["type"] == "FeatureCollection"

    def test_retourne_none_si_absent(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "inexistant.geojson")
        assert lire_geojson(chemin) is None


# --------------------------------------------------------------------------- #
# Tests de ecrire_geojson
# --------------------------------------------------------------------------- #


class TestEcrireGeojson:
    """Tests de l'ecriture de fichiers GeoJSON."""

    def test_cree_fichier_valide(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "sortie.geojson")
        donnees = {"type": "FeatureCollection", "features": []}
        ecrire_geojson(donnees, chemin)
        assert os.path.isfile(chemin)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu == donnees


# --------------------------------------------------------------------------- #
# Tests de ecrire_geojson_si_anomalies
# --------------------------------------------------------------------------- #


class TestEcrireGeojsonSiAnomalies:
    """Tests de l'ecriture conditionnee a la presence d'anomalies."""

    def test_ecrit_le_fichier_si_anomalies(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "ecarts.geojson")
        feature = {"type": "Feature", "properties": {"id": "e1"}, "geometry": None}
        donnees = {"type": "FeatureCollection", "features": [feature]}
        resultat = ecrire_geojson_si_anomalies(donnees, chemin)
        assert resultat == chemin
        assert os.path.isfile(chemin)

    def test_aucun_fichier_si_collection_vide(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "ecarts.geojson")
        resultat = ecrire_geojson_si_anomalies({"type": "FeatureCollection", "features": []}, chemin)
        assert resultat is None
        assert not os.path.isfile(chemin)

    def test_supprime_le_fichier_precedent_si_plus_d_anomalie(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "ecarts.geojson")
        ecrire_geojson({"type": "FeatureCollection", "features": [{"type": "Feature"}]}, chemin)
        resultat = ecrire_geojson_si_anomalies({"type": "FeatureCollection", "features": []}, chemin)
        assert resultat is None
        assert not os.path.isfile(chemin)


# --------------------------------------------------------------------------- #
# Tests de lister_fichiers_geojson
# --------------------------------------------------------------------------- #


class TestListerFichiersGeojson:
    """Tests du listing et filtrage des fichiers GeoJSON."""

    def test_liste_fichiers_eligibles(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert "donnees.geojson" in fichiers

    def test_exclut_fichiers_ecarts(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "ecarts_e200_3d.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert "donnees.geojson" in fichiers
        assert "ecarts_e200_3d.geojson" not in fichiers

    def test_exclut_non_geojson(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "readme.txt").write_text("texte", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert len(fichiers) == 1

    def test_retourne_liste_triee(self, tmp_path: Any) -> None:
        (tmp_path / "b.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "a.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert fichiers == ["a.geojson", "b.geojson"]

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        assert lister_fichiers_geojson(str(tmp_path)) == []

    def test_constantes_coherentes(self) -> None:
        assert EXTENSION_GEOJSON == ".geojson"
        assert PREFIXE_ECARTS == "ecarts_"


# --------------------------------------------------------------------------- #
# Tests de obtenir_id_feature
# --------------------------------------------------------------------------- #


class TestObtenirIdFeature:
    """Tests de l'extraction de l'identifiant metier d'une feature."""

    def test_id_chaine(self) -> None:
        feature: dict[str, Any] = {"properties": {"id": "abc"}}
        assert obtenir_id_feature(feature) == "abc"

    def test_id_entier(self) -> None:
        feature: dict[str, Any] = {"properties": {"id": 42}}
        assert obtenir_id_feature(feature) == "42"

    def test_id_absent(self) -> None:
        feature: dict[str, Any] = {"properties": {}}
        assert obtenir_id_feature(feature) is None

    def test_properties_absentes(self) -> None:
        feature: dict[str, Any] = {}
        assert obtenir_id_feature(feature) is None

    def test_properties_nulles(self) -> None:
        feature: dict[str, Any] = {"properties": None}
        assert obtenir_id_feature(feature) is None


# --------------------------------------------------------------------------- #
# Tests de normaliser_geojson_ecarts
# --------------------------------------------------------------------------- #


class TestNormaliserGeojsonEcarts:
    """Tests du socle commun applique aux proprietes des features d'ecarts."""

    profil = ProfilEcarts(
        code_controle="E999",
        descriptions={"anomalie_test": "Phrase décrivant l'anomalie."},
        champs_id=("id_principal", "id_secondaire"),
    )

    def _collection(self, proprietes: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": proprietes, "geometry": None}],
        }

    def test_socle_present_et_en_tete(self) -> None:
        collection = self._collection(
            {"type_anomalie": "anomalie_test", "priorite": "bloquant", "id_principal": "A1", "detail": "x"}
        )
        proprietes = normaliser_geojson_ecarts(collection, self.profil)["features"][0]["properties"]
        assert list(proprietes)[:5] == [
            "code_controle",
            "priorite",
            "id_entite",
            "type_anomalie",
            "description",
        ]
        assert proprietes["code_controle"] == "E999"
        assert proprietes["priorite"] == "bloquant"
        assert proprietes["id_entite"] == "A1"
        assert proprietes["type_anomalie"] == "anomalie_test"
        assert proprietes["description"] == "Phrase décrivant l'anomalie."

    def test_champs_metier_conserves(self) -> None:
        collection = self._collection({"type_anomalie": "anomalie_test", "detail": "x", "version": "1.1"})
        proprietes = normaliser_geojson_ecarts(collection, self.profil)["features"][0]["properties"]
        assert proprietes["detail"] == "x"
        assert proprietes["version"] == "1.1"

    def test_id_entite_resolu_par_ordre_de_priorite(self) -> None:
        collection = self._collection({"type_anomalie": "anomalie_test", "id_secondaire": "B2"})
        proprietes = normaliser_geojson_ecarts(collection, self.profil)["features"][0]["properties"]
        assert proprietes["id_entite"] == "B2"

    def test_id_entite_none_si_aucun_candidat(self) -> None:
        collection = self._collection({"type_anomalie": "anomalie_test"})
        proprietes = normaliser_geojson_ecarts(collection, self.profil)["features"][0]["properties"]
        assert proprietes["id_entite"] is None

    def test_id_entite_ignore_valeur_vide(self) -> None:
        collection = self._collection({"type_anomalie": "anomalie_test", "id_principal": "", "id_secondaire": "B2"})
        proprietes = normaliser_geojson_ecarts(collection, self.profil)["features"][0]["properties"]
        assert proprietes["id_entite"] == "B2"

    def test_description_repli_sur_code_technique(self) -> None:
        collection = self._collection({"type_anomalie": "type_inconnu"})
        proprietes = normaliser_geojson_ecarts(collection, self.profil)["features"][0]["properties"]
        assert proprietes["description"] == "type_inconnu"

    def test_aucune_duplication_des_champs_du_socle(self) -> None:
        collection = self._collection({"type_anomalie": "anomalie_test", "id_entite": "Z9", "priorite": "mineur"})
        proprietes = normaliser_geojson_ecarts(collection, ProfilEcarts("E999", {}))["features"][0]["properties"]
        assert list(proprietes).count("id_entite") == 1
        assert proprietes["id_entite"] == "Z9"
        assert proprietes["priorite"] == "mineur"

    def test_collection_vide_inchangee(self) -> None:
        collection: dict[str, Any] = {"type": "FeatureCollection", "features": []}
        assert normaliser_geojson_ecarts(collection, self.profil) == collection

    def test_properties_absentes_normalisees(self) -> None:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": None}],
        }
        proprietes = normaliser_geojson_ecarts(collection, self.profil)["features"][0]["properties"]
        assert proprietes["code_controle"] == "E999"
        assert proprietes["type_anomalie"] is None

    def test_crs_et_enveloppe_preserves(self) -> None:
        collection = self._collection({"type_anomalie": "anomalie_test"})
        collection["crs"] = {"type": "name", "properties": {"name": "EPSG:2154"}}
        resultat = normaliser_geojson_ecarts(collection, self.profil)
        assert resultat["type"] == "FeatureCollection"
        assert resultat["crs"]["properties"]["name"] == "EPSG:2154"
