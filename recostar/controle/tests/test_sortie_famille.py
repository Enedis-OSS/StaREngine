"""
Tests de la sortie GeoJSON harmonisee d'une famille (fonctions_communes.sortie_famille).

Couvre la conversion des proprietes vers les huit champs communs, la resolution
de la couche et des identifiants associes, le repli du detail technique dans
INFO, et l'agregation d'une famille en un fichier unique.

L'enjeu verifie ici est l'uniformite : quels que soient le controle emetteur et
ses attributs d'origine, la sortie porte les memes huit champs.
"""

import json
from typing import Any

from recostar.controle.fonctions_communes.sortie_famille import (
    CHAMP_CODE,
    CHAMP_CRITICITE,
    CHAMP_FAMILLE_CONTROLE,
    CHAMP_ID_GML,
    CHAMP_LIBELLE,
    CHAMPS_SORTIE,
    agreger_ecarts_famille,
    construire_info,
    harmoniser_feature,
    harmoniser_proprietes,
    nom_fichier_famille,
    resoudre_designation,
    resoudre_ids_associes,
)

_FAMILLE = "cheminement"

# Proprietes telles qu'un controle les produit, socle normalise compris.
_ECART = {
    "code_controle": "E-3103",
    "code_erreur": "E-3103",
    "priorite": "forte",
    "id_entite": "idA",
    "type_anomalie": "cheminement_sans_cable",
    "description": "Le cheminement ne référence aucun câble.",
    "couche": "RPD_PleineTerre_Reco",
}


def _ecart(**extra: Any) -> dict[str, Any]:
    return {**_ECART, **extra}


class TestHarmoniserProprietes:
    """Conversion vers les huit champs de la nomenclature commune."""

    def test_les_huit_champs_et_rien_d_autre(self) -> None:
        assert tuple(harmoniser_proprietes(_ecart(), _FAMILLE)) == CHAMPS_SORTIE

    def test_code_vient_du_code_erreur(self) -> None:
        assert harmoniser_proprietes(_ecart(), _FAMILLE)[CHAMP_CODE] == "E-3103"

    def test_code_se_replie_sur_le_code_controle(self) -> None:
        """Un type d'anomalie sans code du vérificateur garde l'identité du contrôle."""
        proprietes = _ecart(code_erreur=None, code_controle="E-9400")
        assert harmoniser_proprietes(proprietes, _FAMILLE)[CHAMP_CODE] == "E-9400"

    def test_criticite_vient_de_la_priorite(self) -> None:
        assert harmoniser_proprietes(_ecart(), _FAMILLE)[CHAMP_CRITICITE] == "forte"

    def test_libelle_vient_du_type_anomalie(self) -> None:
        assert harmoniser_proprietes(_ecart(), _FAMILLE)[CHAMP_LIBELLE] == "cheminement_sans_cable"

    def test_famille_reportee(self) -> None:
        assert harmoniser_proprietes(_ecart(), _FAMILLE)[CHAMP_FAMILLE_CONTROLE] == _FAMILLE

    def test_id_gml_vient_de_id_entite(self) -> None:
        assert harmoniser_proprietes(_ecart(), _FAMILLE)[CHAMP_ID_GML] == "idA"

    def test_schema_identique_quel_que_soit_le_controle(self) -> None:
        """Le point de la demande : deux contrôles hétérogènes, une seule structure."""
        autre = {
            "code_controle": "E-5200",
            "priorite": "moyenne",
            "id_entite": "idB",
            "type_anomalie": "courbe_mal_discretisee",
            "description": "Portion mal discrétisée.",
            "fichier_source": "RPD_CableElectrique_Reco.geojson",
            "fleche_max_m": 0.178,
        }
        assert tuple(harmoniser_proprietes(autre, "cable")) == CHAMPS_SORTIE


class TestResoudreDesignation:
    """DESIGNATION_RPD : la couche de l'entité en anomalie."""

    def test_champ_couche(self) -> None:
        assert resoudre_designation({"couche": "RPD_Coffret_Reco"}) == "RPD_Coffret_Reco"

    def test_extension_retiree(self) -> None:
        """Certains contrôles nomment le fichier, non la couche."""
        assert resoudre_designation({"fichier_source": "RPD_Coffret_Reco.geojson"}) == "RPD_Coffret_Reco"

    def test_ordre_de_preference(self) -> None:
        proprietes = {"fichier_source": "RPD_Autre_Reco", "couche": "RPD_Coffret_Reco"}
        assert resoudre_designation(proprietes) == "RPD_Coffret_Reco"

    def test_aucun_champ_donne_chaine_vide(self) -> None:
        assert resoudre_designation({"id_entite": "idA"}) == ""


class TestResoudreIdsAssocies:
    """ID_GML_ASSOCIE : les autres entités en cause, séparées par des virgules."""

    def test_identifiant_unique(self) -> None:
        assert resoudre_ids_associes({"id_cable": "idC"}, "idA") == "idC"

    def test_plusieurs_champs_cumules(self) -> None:
        proprietes = {"id_cable": "idC", "id_noeud": "idN"}
        assert resoudre_ids_associes(proprietes, "idA") == "idC,idN"

    def test_valeur_en_liste(self) -> None:
        assert resoudre_ids_associes({"ids_cheminements": ["id1", "id2"]}, "idA") == "id1,id2"

    def test_valeur_deja_separee_par_virgules(self) -> None:
        assert resoudre_ids_associes({"ids_cheminements": "id1,id2"}, "idA") == "id1,id2"

    def test_identifiant_principal_exclu(self) -> None:
        """Une entité ne s'associe pas à elle-même."""
        assert resoudre_ids_associes({"id_cable": "idA"}, "idA") == ""

    def test_id_entite_exclu(self) -> None:
        assert resoudre_ids_associes({"id_entite": "idA", "id_cable": "idC"}, "idA") == "idC"

    def test_doublons_ecartes_ordre_conserve(self) -> None:
        proprietes = {"id_cable": "idC", "ids_autres": "idC,idD"}
        assert resoudre_ids_associes(proprietes, "idA") == "idC,idD"

    def test_aucun_associe(self) -> None:
        assert resoudre_ids_associes({"couche": "RPD_X_Reco"}, "idA") == ""


class TestConstruireInfo:
    """INFO : la description, augmentée du détail technique."""

    def test_description_seule(self) -> None:
        assert construire_info(_ecart()) == "Le cheminement ne référence aucun câble."

    def test_champs_metier_replies(self) -> None:
        info = construire_info(_ecart(fleche_max_m=0.178, rayon_min_m=0.64))
        assert "fleche_max_m : 0.178" in info
        assert "rayon_min_m : 0.64" in info

    def test_champs_du_socle_non_repetes(self) -> None:
        """Ce qu'une autre colonne exprime déjà n'a pas à figurer dans INFO."""
        info = construire_info(_ecart())
        for interdit in ("code_erreur", "priorite", "type_anomalie", "couche", "id_entite"):
            assert interdit not in info

    def test_identifiants_non_repetes(self) -> None:
        info = construire_info(_ecart(id_cable="idC"))
        assert "id_cable" not in info

    def test_valeur_nulle_ignoree(self) -> None:
        assert construire_info(_ecart(mesure=None)) == "Le cheminement ne référence aucun câble."

    def test_description_absente(self) -> None:
        proprietes = {"type_anomalie": "x", "mesure": 3}
        assert construire_info(proprietes) == "mesure : 3"


class TestHarmoniserFeature:
    """La géométrie est reprise telle quelle, seules les propriétés changent."""

    def test_geometrie_conservee(self) -> None:
        geometrie = {"type": "Point", "coordinates": [1.0, 2.0]}
        feature = {"type": "Feature", "properties": _ecart(), "geometry": geometrie}
        assert harmoniser_feature(feature, _FAMILLE)["geometry"] == geometrie

    def test_geometrie_nulle_admise(self) -> None:
        feature = {"type": "Feature", "properties": _ecart(), "geometry": None}
        assert harmoniser_feature(feature, _FAMILLE)["geometry"] is None


class TestAgregerEcartsFamille:
    """Fusion des fichiers d'une famille en un GeoJSON unique."""

    _CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}

    def _ecrire(self, dossier, nom: str, proprietes: list[dict[str, Any]], crs=None) -> str:
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": p, "geometry": {"type": "Point", "coordinates": [0.0, 0.0]}}
                for p in proprietes
            ],
        }
        if crs is not None:
            collection["crs"] = crs
        chemin = str(dossier / nom)
        with open(chemin, "w", encoding="utf-8") as fichier:
            json.dump(collection, fichier)
        return chemin

    def test_fichier_unique_produit(self, tmp_path) -> None:
        a = self._ecrire(tmp_path, "ecarts_a.geojson", [_ecart()])
        b = self._ecrire(tmp_path, "ecarts_b.geojson", [_ecart(id_entite="idB")])
        resultat = agreger_ecarts_famille([a, b], str(tmp_path), _FAMILLE)
        assert resultat["sortie"] == str(tmp_path / nom_fichier_famille(_FAMILLE))
        assert resultat["nombre_ecarts"] == 2

    def test_fichiers_sources_supprimes(self, tmp_path) -> None:
        """La famille ne doit laisser qu'un GeoJSON."""
        import os

        a = self._ecrire(tmp_path, "ecarts_a.geojson", [_ecart()])
        agreger_ecarts_famille([a], str(tmp_path), _FAMILLE)
        assert not os.path.isfile(a)
        restants = [n for n in os.listdir(tmp_path) if n.startswith("ecarts_")]
        assert restants == [nom_fichier_famille(_FAMILLE)]

    def test_sources_conservees_sur_demande(self, tmp_path) -> None:
        import os

        a = self._ecrire(tmp_path, "ecarts_a.geojson", [_ecart()])
        agreger_ecarts_famille([a], str(tmp_path), _FAMILLE, supprimer_sources=False)
        assert os.path.isfile(a)

    def test_chemins_none_ignores(self, tmp_path) -> None:
        """Un contrôle sans écart déclare une sortie nulle."""
        a = self._ecrire(tmp_path, "ecarts_a.geojson", [_ecart()])
        assert agreger_ecarts_famille([None, a, None], str(tmp_path), _FAMILLE)["nombre_ecarts"] == 1

    def test_aucun_ecart_aucun_fichier(self, tmp_path) -> None:
        import os

        resultat = agreger_ecarts_famille([None], str(tmp_path), _FAMILLE)
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / nom_fichier_famille(_FAMILLE)))

    def test_fichier_precedent_supprime_si_plus_d_ecart(self, tmp_path) -> None:
        """Une exécution qui ne relève plus rien ne doit pas laisser l'ancien fichier."""
        import os

        a = self._ecrire(tmp_path, "ecarts_a.geojson", [_ecart()])
        agreger_ecarts_famille([a], str(tmp_path), _FAMILLE)
        agreger_ecarts_famille([None], str(tmp_path), _FAMILLE)
        assert not os.path.isfile(str(tmp_path / nom_fichier_famille(_FAMILLE)))

    def test_crs_propage(self, tmp_path) -> None:
        a = self._ecrire(tmp_path, "ecarts_a.geojson", [_ecart()], crs=self._CRS)
        chemin = agreger_ecarts_famille([a], str(tmp_path), _FAMILLE)["sortie"]
        assert chemin is not None
        with open(chemin, encoding="utf-8") as fichier:
            assert json.load(fichier)["crs"] == self._CRS

    def test_schema_uniforme_sur_des_sources_heterogenes(self, tmp_path) -> None:
        """Deux contrôles aux attributs différents donnent un seul schéma."""
        a = self._ecrire(tmp_path, "ecarts_a.geojson", [_ecart(id_cable="idC")])
        autre = {
            "code_controle": "E-5200",
            "priorite": "moyenne",
            "id_entite": "idB",
            "type_anomalie": "courbe_mal_discretisee",
            "description": "Portion mal discrétisée.",
            "fichier_source": "RPD_CableElectrique_Reco.geojson",
            "fleche_max_m": 0.178,
        }
        b = self._ecrire(tmp_path, "ecarts_b.geojson", [autre])
        chemin = agreger_ecarts_famille([a, b], str(tmp_path), _FAMILLE)["sortie"]
        assert chemin is not None
        with open(chemin, encoding="utf-8") as fichier:
            features = json.load(fichier)["features"]
        assert {tuple(f["properties"]) for f in features} == {CHAMPS_SORTIE}

    def test_fichier_illisible_n_interrompt_pas(self, tmp_path) -> None:
        """Les écarts des autres contrôles restent exploitables."""
        casse = str(tmp_path / "ecarts_casse.geojson")
        with open(casse, "w", encoding="utf-8") as fichier:
            fichier.write("{ pas du json")
        bon = self._ecrire(tmp_path, "ecarts_a.geojson", [_ecart()])
        assert agreger_ecarts_famille([casse, bon], str(tmp_path), _FAMILLE)["nombre_ecarts"] == 1

    def test_nom_du_fichier_porte_la_famille(self) -> None:
        assert nom_fichier_famille("cable") == "ecarts_cable.geojson"
