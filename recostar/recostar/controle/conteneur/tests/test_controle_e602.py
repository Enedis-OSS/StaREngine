"""
Tests du controle E602 : unicite des identifiants de materiel entre jonctions.

Couvre :
  - la construction du couple (NumeroLot, NumeroSerie) et son perimetre
  - le regroupement des occurrences par couple
  - la detection du conflit (plusieurs jonctions pour un meme couple)
  - les comptages du rapport
  - la construction du GeoJSON d'ecarts
  - l'execution CLI
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from controle_e601 import LienJonction
from controle_e602 import (
    CHAMP_NUMERO_LOT,
    CHAMP_NUMERO_SERIE,
    FICHIER_JONCTION,
    FICHIER_MATERIEL,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    TYPE_IDENTIFIANTS_PARTAGES,
    OccurrenceMateriel,
    compter_couples_en_conflit,
    compter_materiels_controles,
    construire_geojson_ecarts,
    couple_identifiants,
    detecter_anomalies,
    executer_controle_cli,
    grouper_occurrences_par_couple,
    jonctions_en_conflit,
)
from utils_tests import (
    construire_feature_jonction,
    construire_feature_materiel,
    ecrire_collection,
    ecrire_collection_avec_crs,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _materiel(identifiant: str, lot: Any = "LOT-1", serie: Any = "SN-1") -> dict[str, Any]:
    """Feature materiel portant un couple d'identifiants."""
    return construire_feature_materiel(
        identifiant,
        proprietes_extra={CHAMP_NUMERO_LOT: lot, CHAMP_NUMERO_SERIE: serie},
    )


def _lien(id_jonction: str | None = "j1") -> LienJonction:
    """Lien indexe minimal, avec une geometrie de jonction."""
    return LienJonction(id_jonction, "Jonction", {"type": "Point", "coordinates": [1.0, 2.0, 3.0]})


def _occurrence(id_materiel: str, id_jonction: str) -> OccurrenceMateriel:
    return OccurrenceMateriel(id_materiel, id_jonction, "LOT-1", "SN-1", None)


def _ecrire_jeu(tmp_path: Any, materiels: list[dict[str, Any]], jonctions: list[dict[str, Any]]) -> None:
    ecrire_collection(str(tmp_path / FICHIER_MATERIEL), materiels)
    ecrire_collection(str(tmp_path / FICHIER_JONCTION), jonctions)


# --------------------------------------------------------------------------- #
# Couple d'identifiants
# --------------------------------------------------------------------------- #


class TestCoupleIdentifiants:
    """Tests de couple_identifiants."""

    def test_couple_normalise(self) -> None:
        assert couple_identifiants({CHAMP_NUMERO_LOT: " LOT-1 ", CHAMP_NUMERO_SERIE: "Sn-1"}) == ("lot-1", "sn-1")

    def test_espaces_internes_replies(self) -> None:
        """Meme normalisation qu'E600 : les valeurs issues du GML sont repliees."""
        assert couple_identifiants({CHAMP_NUMERO_LOT: "LOT\n1", CHAMP_NUMERO_SERIE: "SN  1"}) == ("lot 1", "sn 1")

    def test_valeurs_numeriques_converties(self) -> None:
        assert couple_identifiants({CHAMP_NUMERO_LOT: 62, CHAMP_NUMERO_SERIE: 540}) == ("62", "540")

    def test_lot_absent(self) -> None:
        assert couple_identifiants({CHAMP_NUMERO_SERIE: "SN-1"}) is None

    def test_serie_absente(self) -> None:
        assert couple_identifiants({CHAMP_NUMERO_LOT: "LOT-1"}) is None

    def test_lot_vide(self) -> None:
        assert couple_identifiants({CHAMP_NUMERO_LOT: "   ", CHAMP_NUMERO_SERIE: "SN-1"}) is None

    def test_couple_entierement_absent(self) -> None:
        assert couple_identifiants({}) is None


# --------------------------------------------------------------------------- #
# Regroupement
# --------------------------------------------------------------------------- #


class TestGrouperOccurrencesParCouple:
    """Tests de grouper_occurrences_par_couple."""

    def test_regroupement_sur_le_couple(self) -> None:
        materiels = [_materiel("m1"), _materiel("m2")]
        groupes = grouper_occurrences_par_couple(materiels, {"m1": [_lien("j1")], "m2": [_lien("j2")]})
        assert list(groupes) == [("lot-1", "sn-1")]
        assert len(groupes[("lot-1", "sn-1")]) == 2

    def test_couples_distincts_separes(self) -> None:
        materiels = [_materiel("m1", serie="SN-1"), _materiel("m2", serie="SN-2")]
        groupes = grouper_occurrences_par_couple(materiels, {"m1": [_lien("j1")], "m2": [_lien("j2")]})
        assert set(groupes) == {("lot-1", "sn-1"), ("lot-1", "sn-2")}

    def test_lot_commun_serie_differente_non_regroupes(self) -> None:
        """Cas reel Echantillon2 : un lot de fabrication equipe plusieurs jonctions.

        C'est la raison d'etre du couple : NumeroLot seul ne discrimine pas.
        """
        materiels = [_materiel("m1", lot="123654654", serie="r"), _materiel("m2", lot="123654654", serie="FE3214321")]
        groupes = grouper_occurrences_par_couple(materiels, {"m1": [_lien("j1")], "m2": [_lien("j2")]})
        assert len(groupes) == 2

    def test_couple_incomplet_hors_perimetre(self) -> None:
        materiels = [_materiel("m1", serie=None), _materiel("m2", lot=None)]
        assert grouper_occurrences_par_couple(materiels, {"m1": [_lien("j1")], "m2": [_lien("j2")]}) == {}

    def test_materiel_orphelin_hors_perimetre(self) -> None:
        """Sans jonction, un materiel ne peut etre associe a plusieurs : c'est E601."""
        assert grouper_occurrences_par_couple([_materiel("m1")], {}) == {}

    def test_materiel_sans_identifiant_hors_perimetre(self) -> None:
        feature = _materiel("m1")
        feature["properties"].pop("id")
        assert grouper_occurrences_par_couple([feature], {"m1": [_lien("j1")]}) == {}

    def test_jonction_sans_identifiant_ecartee(self) -> None:
        """Des jonctions indiscernables gonfleraient le compte et creeraient un conflit fictif."""
        materiels = [_materiel("m1"), _materiel("m2")]
        liens = {"m1": [_lien(None)], "m2": [_lien(None)]}
        assert grouper_occurrences_par_couple(materiels, liens) == {}

    def test_materiel_multi_jonctions_produit_deux_occurrences(self) -> None:
        groupes = grouper_occurrences_par_couple([_materiel("m1")], {"m1": [_lien("j1"), _lien("j2")]})
        assert [o.id_jonction for o in groupes[("lot-1", "sn-1")]] == ["j1", "j2"]

    def test_valeurs_brutes_conservees(self) -> None:
        groupes = grouper_occurrences_par_couple([_materiel("m1", lot=" LOT-1 ")], {"m1": [_lien("j1")]})
        assert groupes[("lot-1", "sn-1")][0].numero_lot == " LOT-1 "

    def test_aucun_materiel(self) -> None:
        assert grouper_occurrences_par_couple([], {"m1": [_lien()]}) == {}


class TestJonctionsEnConflit:
    """Tests de jonctions_en_conflit."""

    def test_une_seule_jonction_conforme(self) -> None:
        assert jonctions_en_conflit([_occurrence("m1", "j1")]) == []

    def test_deux_enregistrements_sur_la_meme_jonction_conformes(self) -> None:
        """La regle porte sur la pluralite des jonctions, pas des enregistrements."""
        assert jonctions_en_conflit([_occurrence("m1", "j1"), _occurrence("m2", "j1")]) == []

    def test_deux_jonctions_en_conflit(self) -> None:
        assert jonctions_en_conflit([_occurrence("m1", "j1"), _occurrence("m2", "j2")]) == ["j1", "j2"]

    def test_resultat_trie_et_dedoublonne(self) -> None:
        occurrences = [_occurrence("m1", "j2"), _occurrence("m2", "j1"), _occurrence("m3", "j2")]
        assert jonctions_en_conflit(occurrences) == ["j1", "j2"]

    def test_liste_vide(self) -> None:
        assert jonctions_en_conflit([]) == []


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_couples_uniques_conformes(self) -> None:
        materiels = [_materiel("m1", serie="SN-1"), _materiel("m2", serie="SN-2")]
        assert detecter_anomalies(materiels, {"m1": [_lien("j1")], "m2": [_lien("j2")]}) == []

    def test_couple_partage_entre_deux_jonctions(self) -> None:
        materiels = [_materiel("m1"), _materiel("m2")]
        anomalies = detecter_anomalies(materiels, {"m1": [_lien("j1")], "m2": [_lien("j2")]})
        assert len(anomalies) == 2
        assert {a["id_materiel"] for a in anomalies} == {"m1", "m2"}
        assert all(a["type_anomalie"] == TYPE_IDENTIFIANTS_PARTAGES for a in anomalies)

    def test_une_anomalie_par_occurrence(self) -> None:
        """Le conflit se corrige a chacune des positions qu'il met en cause."""
        materiels = [_materiel(f"m{i}") for i in range(1, 5)]
        liens = {f"m{i}": [_lien(f"j{i}")] for i in range(1, 5)}
        anomalies = detecter_anomalies(materiels, liens)
        assert len(anomalies) == 4
        assert all(a["nombre_jonctions"] == 4 for a in anomalies)

    def test_liste_des_jonctions_en_conflit(self) -> None:
        materiels = [_materiel("m1"), _materiel("m2")]
        anomalies = detecter_anomalies(materiels, {"m1": [_lien("j2")], "m2": [_lien("j1")]})
        assert anomalies[0]["jonctions_en_conflit"] == "j1,j2"

    def test_meme_jonction_non_signalee(self) -> None:
        materiels = [_materiel("m1"), _materiel("m2")]
        assert detecter_anomalies(materiels, {"m1": [_lien("j1")], "m2": [_lien("j1")]}) == []

    def test_casse_et_espaces_ignores(self) -> None:
        """Deux saisies differentes du meme identifiant restent le meme materiel."""
        materiels = [_materiel("m1", lot="LOT-1", serie="SN-1"), _materiel("m2", lot=" lot-1", serie="sn-1 ")]
        assert len(detecter_anomalies(materiels, {"m1": [_lien("j1")], "m2": [_lien("j2")]})) == 2

    def test_materiel_multi_jonctions_en_conflit_avec_lui_meme(self) -> None:
        """Un seul materiel rattache a deux jonctions viole aussi la regle.

        Le rattachement multiple est par ailleurs signale par E601 : les deux
        constats sont exacts et repondent a des questions differentes.
        """
        anomalies = detecter_anomalies([_materiel("m1")], {"m1": [_lien("j1"), _lien("j2")]})
        assert len(anomalies) == 2
        assert {a["id_jonction"] for a in anomalies} == {"j1", "j2"}

    def test_couple_incomplet_jamais_signale(self) -> None:
        """Sans NumeroSerie, tous les materiels d'un lot convergeraient a tort."""
        materiels = [_materiel("m1", serie=None), _materiel("m2", serie=None)]
        assert detecter_anomalies(materiels, {"m1": [_lien("j1")], "m2": [_lien("j2")]}) == []

    def test_geometrie_de_la_jonction_conservee(self) -> None:
        materiels = [_materiel("m1"), _materiel("m2")]
        anomalies = detecter_anomalies(materiels, {"m1": [_lien("j1")], "m2": [_lien("j2")]})
        assert anomalies[0]["geometrie"]["type"] == "Point"


class TestComptages:
    """Tests des comptages du rapport."""

    def test_couples_en_conflit(self) -> None:
        materiels = [_materiel("m1"), _materiel("m2"), _materiel("m3", serie="SN-9")]
        liens = {"m1": [_lien("j1")], "m2": [_lien("j2")], "m3": [_lien("j3")]}
        assert compter_couples_en_conflit(materiels, liens) == 1

    def test_aucun_conflit(self) -> None:
        assert compter_couples_en_conflit([_materiel("m1")], {"m1": [_lien("j1")]}) == 0

    def test_materiels_controles(self) -> None:
        """Seuls les materiels a couple complet et rattaches sont comptes."""
        materiels = [_materiel("m1"), _materiel("m2", serie=None), _materiel("m3")]
        liens = {"m1": [_lien("j1")], "m2": [_lien("j2")]}
        assert compter_materiels_controles(materiels, liens) == 1

    def test_materiels_controles_liste_vide(self) -> None:
        assert compter_materiels_controles([], {}) == 0


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_IDENTIFIANTS_PARTAGES,
            "id_materiel": "m1",
            "id_jonction": "j1",
            "numero_lot": "062",
            "numero_serie": "0540",
            "nombre_jonctions": 4,
            "jonctions_en_conflit": "j1,j2,j3,j4",
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }

    def test_socle_commun(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["code_controle"] == "E602"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_entite"] == "m1"
        assert props["type_anomalie"] == TYPE_IDENTIFIANTS_PARTAGES
        assert props["description"]

    def test_proprietes_metier(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["fichier_source"] == FICHIER_MATERIEL
        assert props["id_jonction"] == "j1"
        assert props["numero_lot"] == "062"
        assert props["numero_serie"] == "0540"
        assert props["nombre_jonctions"] == 4
        assert props["jonctions_en_conflit"] == "j1,j2,j3,j4"

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
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichiers_absents_non_bloquants(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_materiel_absent"] is True
        assert resultat["fichier_jonction_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_nominal_conforme(self, tmp_path: Any) -> None:
        _ecrire_jeu(
            tmp_path,
            [_materiel("m1", serie="SN-1"), _materiel("m2", serie="SN-2")],
            [
                construire_feature_jonction("j1", materiel_href="m1"),
                construire_feature_jonction("j2", materiel_href="m2"),
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_materiels_controles"] == 2
        assert resultat["priorite"] == "majeur"

    def test_nominal_en_conflit(self, tmp_path: Any) -> None:
        _ecrire_jeu(
            tmp_path,
            [_materiel("m1"), _materiel("m2")],
            [
                construire_feature_jonction("j1", materiel_href="m1"),
                construire_feature_jonction("j2", materiel_href="m2"),
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 2
        assert resultat["nombre_couples_en_conflit"] == 1

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        _ecrire_jeu(
            tmp_path,
            [_materiel("m1"), _materiel("m2")],
            [
                construire_feature_jonction("j1", materiel_href="m1"),
                construire_feature_jonction("j2", materiel_href="m2"),
            ],
        )
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_materiel("m1")], [construire_feature_jonction("j1", materiel_href="m1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_crs_propage(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_MATERIEL), [_materiel("m1"), _materiel("m2")])
        ecrire_collection_avec_crs(
            str(tmp_path / FICHIER_JONCTION),
            [
                construire_feature_jonction("j1", materiel_href="m1"),
                construire_feature_jonction("j2", materiel_href="m2"),
            ],
            "EPSG:2154",
        )
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert "2154" in ecarts["crs"]["properties"]["name"]

    def test_type_de_jonction_sans_effet(self, tmp_path: Any) -> None:
        """E602 ne filtre pas sur TypeJonction : c'est la regle d'E601."""
        _ecrire_jeu(
            tmp_path,
            [_materiel("m1"), _materiel("m2")],
            [
                construire_feature_jonction("j1", type_jonction="ExtremiteReseau", materiel_href="m1"),
                construire_feature_jonction("j2", type_jonction="Derivation", materiel_href="m2"),
            ],
        )
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 2

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_materiel("m1")], [construire_feature_jonction("j1", materiel_href="m1")])
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "nombre_couples_en_conflit",
            "nombre_materiels_analyses",
            "nombre_materiels_controles",
            "nombre_jonctions_analysees",
            "fichier_materiel_absent",
            "fichier_jonction_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """L'unicite est controlee identiquement en V1.0 et V1.1."""

    def test_v11_champs_extra_sans_effet(self, tmp_path: Any) -> None:
        materiels = [_materiel("m1"), _materiel("m2")]
        materiels[0]["properties"]["Fabricant"] = "3M"
        _ecrire_jeu(
            tmp_path,
            materiels,
            [
                construire_feature_jonction("j1", materiel_href="m1", proprietes_extra={"Commentaire": "note"}),
                construire_feature_jonction("j2", materiel_href="m2"),
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 2
