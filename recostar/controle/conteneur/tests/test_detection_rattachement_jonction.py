"""
Tests du moteur de rattachement du materiel a la jonction qui le porte — et
de ses deux controles : E-7102 (type de la jonction) et E-7103 (son statut).

Couvre :
  - la cascade type puis statut, exclusive et exhaustive
  - la repartition des anomalies entre les deux codes voisins
  - la construction de l'index inverse {materiel: [jonctions]}
  - la regle de validite du TypeJonction
  - la detection (orphelin, type invalide, liens multiples)
  - les comptages du rapport
  - la construction du GeoJSON d'ecarts, geometrie nulle comprise
  - l'execution CLI (fichiers presents, absents, sortie conditionnelle)
  - la coherence avec E-7104, qui parcourt la meme relation en sens inverse
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from recostar.controle.conteneur.detection_rattachement_jonction import (
    TYPE_JONCTION_ABSENTE,
    TYPE_JONCTION_INVALIDE,
    TYPE_STATUT_INVALIDE,
    TYPES_JONCTION_VALIDES,
    LienJonction,
    classifier_lien,
    compter_liens_controles,
    compter_materiels_non_conformes,
    construire_geojson_ecarts,
    detecter_anomalies,
    indexer_jonctions_par_materiel,
    type_jonction_valide,
)
from recostar.controle.conteneur.e7102 import FICHIER_SORTIE, PROFIL_ECARTS, executer_controle_cli
from recostar.controle.conteneur.e7103 import executer_controle_cli as executer_7103
from recostar.controle.conteneur.tests.utils_tests import (
    construire_feature_jonction,
    construire_feature_materiel,
    ecrire_collection,
    ecrire_collection_avec_crs,
)
from recostar.controle.fonctions_communes.geojson import PRIORITE_FORTE
from recostar.controle.fonctions_communes.modele_recostar import (
    FICHIER_JONCTION,
    FICHIER_MATERIEL,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _lien(
    id_jonction: str = "j1",
    type_jonction: Any = "Jonction",
    statut: Any = "UnderCommissionning",
) -> LienJonction:
    """Lien indexe minimal, conforme par defaut : boite en cours de mise en service."""
    return LienJonction(id_jonction, type_jonction, {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}, statut)


def construire_geojson_ecarts_profil(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit les ecarts sous le profil d'E-7102, celui des tests existants."""
    return construire_geojson_ecarts(anomalies, PROFIL_ECARTS, crs)


def _jeu_conforme(tmp_path: Any) -> None:
    """Ecrit un materiel porte par une jonction de type valide."""
    ecrire_collection(
        str(tmp_path / FICHIER_MATERIEL),
        [construire_feature_materiel("m1", fabricant="3M", modele="A")],
    )
    ecrire_collection(
        str(tmp_path / FICHIER_JONCTION),
        [construire_feature_jonction("j1", materiel_href="m1")],
    )


# --------------------------------------------------------------------------- #
# Index inverse
# --------------------------------------------------------------------------- #


class TestIndexerJonctionsParMateriel:
    """Tests de indexer_jonctions_par_materiel."""

    def test_index_par_materiel(self) -> None:
        index = indexer_jonctions_par_materiel(
            [
                construire_feature_jonction("j1", materiel_href="m1"),
                construire_feature_jonction("j2", type_jonction="Derivation", materiel_href="m2"),
            ]
        )
        assert set(index) == {"m1", "m2"}
        assert index["m1"][0].id_jonction == "j1"
        assert index["m2"][0].type_jonction == "Derivation"

    def test_jonction_sans_materiel_href_ignoree(self) -> None:
        assert indexer_jonctions_par_materiel([construire_feature_jonction("j1", materiel_href=None)]) == {}

    def test_materiel_href_vide_ignore(self) -> None:
        assert indexer_jonctions_par_materiel([construire_feature_jonction("j1", materiel_href="  ")]) == {}

    def test_href_espaces_normalise(self) -> None:
        """Le href est resolu comme cote E-7104 : les deux controles voient le meme lien."""
        index = indexer_jonctions_par_materiel([construire_feature_jonction("j1", materiel_href=" m1 ")])
        assert set(index) == {"m1"}

    def test_plusieurs_jonctions_sur_un_materiel(self) -> None:
        index = indexer_jonctions_par_materiel(
            [
                construire_feature_jonction("j1", materiel_href="m1"),
                construire_feature_jonction("j2", type_jonction="ExtremiteReseau", materiel_href="m1"),
            ]
        )
        assert [lien.id_jonction for lien in index["m1"]] == ["j1", "j2"]

    def test_geometrie_conservee(self) -> None:
        index = indexer_jonctions_par_materiel(
            [construire_feature_jonction("j1", materiel_href="m1", coordonnees=[5.0, 6.0, 7.0])]
        )
        assert index["m1"][0].geometrie == {"type": "Point", "coordinates": [5.0, 6.0, 7.0]}

    def test_liste_vide(self) -> None:
        assert indexer_jonctions_par_materiel([]) == {}


# --------------------------------------------------------------------------- #
# Regle metier
# --------------------------------------------------------------------------- #


class TestTypeJonctionValide:
    """Tests de type_jonction_valide."""

    def test_jonction(self) -> None:
        assert type_jonction_valide("Jonction") is True

    def test_derivation(self) -> None:
        assert type_jonction_valide("Derivation") is True

    def test_extremite_reseau(self) -> None:
        assert type_jonction_valide("ExtremiteReseau") is False

    def test_remontee_aero_souterraine(self) -> None:
        """Type reellement present dans les jeux de reference."""
        assert type_jonction_valide("RemonteeAeroSouterraine") is False

    def test_absent(self) -> None:
        assert type_jonction_valide(None) is False

    def test_casse_differente_invalide(self) -> None:
        """TypeJonction est une enumeration du XSD : la comparaison est stricte."""
        assert type_jonction_valide("jonction") is False

    def test_les_deux_types_declares(self) -> None:
        assert TYPES_JONCTION_VALIDES == frozenset({"Derivation", "Jonction"})


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_materiel_conforme(self) -> None:
        materiels = [construire_feature_materiel("m1")]
        assert detecter_anomalies(materiels, {"m1": [_lien()]}) == []

    def test_derivation_conforme(self) -> None:
        materiels = [construire_feature_materiel("m1")]
        assert detecter_anomalies(materiels, {"m1": [_lien(type_jonction="Derivation")]}) == []

    def test_materiel_orphelin(self) -> None:
        anomalies = detecter_anomalies([construire_feature_materiel("m1")], {})
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_JONCTION_ABSENTE
        assert anomalies[0]["id_materiel"] == "m1"
        assert anomalies[0]["id_jonction"] is None
        assert anomalies[0]["geometrie"] is None

    def test_type_jonction_invalide(self) -> None:
        materiels = [construire_feature_materiel("m1")]
        anomalies = detecter_anomalies(materiels, {"m1": [_lien("j9", "ExtremiteReseau")]})
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_JONCTION_INVALIDE
        assert anomalies[0]["id_jonction"] == "j9"
        assert anomalies[0]["type_jonction"] == "ExtremiteReseau"
        assert anomalies[0]["geometrie"]["type"] == "Point"

    def test_index_vide_pour_le_materiel_vaut_orphelin(self) -> None:
        """Une liste de liens vide equivaut a l'absence de cle."""
        anomalies = detecter_anomalies([construire_feature_materiel("m1")], {"m1": []})
        assert anomalies[0]["type_anomalie"] == TYPE_JONCTION_ABSENTE

    def test_materiel_sans_identifiant_est_orphelin(self) -> None:
        """Sans identifiant, aucune jonction ne peut le referencer."""
        feature = construire_feature_materiel("m1")
        feature["properties"].pop("id")
        anomalies = detecter_anomalies([feature], {"m1": [_lien()]})
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_JONCTION_ABSENTE
        assert anomalies[0]["id_materiel"] is None

    def test_une_anomalie_par_lien_fautif(self) -> None:
        """Deux jonctions inaptes sur un meme materiel : deux defauts a corriger."""
        materiels = [construire_feature_materiel("m1")]
        liens = {"m1": [_lien("j1", "ExtremiteReseau"), _lien("j2", "RemonteeAeroSouterraine")]}
        anomalies = detecter_anomalies(materiels, liens)
        assert [a["id_jonction"] for a in anomalies] == ["j1", "j2"]

    def test_lien_valide_n_efface_pas_un_lien_fautif(self) -> None:
        materiels = [construire_feature_materiel("m1")]
        liens = {"m1": [_lien("j1", "Jonction"), _lien("j2", "ExtremiteReseau")]}
        anomalies = detecter_anomalies(materiels, liens)
        assert len(anomalies) == 1
        assert anomalies[0]["id_jonction"] == "j2"

    def test_plusieurs_materiels(self) -> None:
        materiels = [construire_feature_materiel(f"m{i}") for i in range(1, 4)]
        liens = {"m1": [_lien()], "m2": [_lien("j2", "ExtremiteReseau")]}
        anomalies = detecter_anomalies(materiels, liens)
        assert {(a["id_materiel"], a["type_anomalie"]) for a in anomalies} == {
            ("m2", TYPE_JONCTION_INVALIDE),
            ("m3", TYPE_JONCTION_ABSENTE),
        }

    def test_aucun_materiel(self) -> None:
        assert detecter_anomalies([], {"m1": [_lien()]}) == []


class TestComptages:
    """Tests des comptages du rapport."""

    def test_liens_controles(self) -> None:
        """Les liens d'un materiel absent du fichier ne sont pas comptes."""
        materiels = [construire_feature_materiel("m1"), construire_feature_materiel("m2")]
        liens = {"m1": [_lien(), _lien("j2")], "m2": [_lien("j3")], "m9": [_lien("j4")]}
        assert compter_liens_controles(materiels, liens) == 3

    def test_liens_controles_sans_lien(self) -> None:
        assert compter_liens_controles([construire_feature_materiel("m1")], {}) == 0

    def test_materiels_non_conformes_dedoublonnes(self) -> None:
        anomalies = [
            {"id_materiel": "m1", "type_anomalie": TYPE_JONCTION_INVALIDE},
            {"id_materiel": "m1", "type_anomalie": TYPE_JONCTION_INVALIDE},
            {"id_materiel": "m2", "type_anomalie": TYPE_JONCTION_ABSENTE},
        ]
        assert compter_materiels_non_conformes(anomalies) == 2

    def test_materiels_non_conformes_liste_vide(self) -> None:
        assert compter_materiels_non_conformes([]) == 0


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_JONCTION_INVALIDE,
            "id_materiel": "m1",
            "id_jonction": "j1",
            "type_jonction": "ExtremiteReseau",
            "statut_jonction": "UnderCommissionning",
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }

    def test_socle_commun(self) -> None:
        props = construire_geojson_ecarts_profil([self._anomalie()])["features"][0]["properties"]
        assert props["code_controle"] == "E-7102"
        assert props["priorite"] == PRIORITE_FORTE
        assert props["id_entite"] == "m1"
        assert props["type_anomalie"] == TYPE_JONCTION_INVALIDE
        assert props["description"]

    def test_proprietes_metier(self) -> None:
        props = construire_geojson_ecarts_profil([self._anomalie()])["features"][0]["properties"]
        assert props["fichier_source"] == FICHIER_MATERIEL
        assert props["id_materiel"] == "m1"
        assert props["id_jonction"] == "j1"
        assert props["type_jonction"] == "ExtremiteReseau"

    def test_geometrie_de_la_jonction(self) -> None:
        geom = construire_geojson_ecarts_profil([self._anomalie()])["features"][0]["geometry"]
        assert geom == {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}

    def test_geometrie_nulle_pour_un_orphelin(self) -> None:
        """Un materiel orphelin n'a aucune position connue : geometrie nulle."""
        anomalie = {
            "type_anomalie": TYPE_JONCTION_ABSENTE,
            "id_materiel": "m1",
            "id_jonction": None,
            "type_jonction": None,
            "statut_jonction": None,
            "geometrie": None,
        }
        feature = construire_geojson_ecarts_profil([anomalie])["features"][0]
        assert feature["geometry"] is None
        assert feature["properties"]["id_entite"] == "m1"

    def test_id_entite_replie_sur_la_jonction(self) -> None:
        """Un materiel sans identifiant laisse la jonction identifier l'ecart."""
        anomalie = {**self._anomalie(), "id_materiel": None}
        props = construire_geojson_ecarts_profil([anomalie])["features"][0]["properties"]
        assert props["id_entite"] == "j1"

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts_profil([self._anomalie()], crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts_profil([])["features"] == []


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
        _jeu_conforme(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_materiels_analyses"] == 1
        assert resultat["nombre_liens_controles"] == 1
        assert resultat["anomalies_par_type"] == {}

    def test_fichier_jonction_absent_rend_les_materiels_orphelins(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_MATERIEL), [construire_feature_materiel("m1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["fichier_jonction_absent"] is True
        assert resultat["anomalies_par_type"] == {TYPE_JONCTION_ABSENTE: 1}

    def test_type_jonction_invalide(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_MATERIEL), [construire_feature_materiel("m1")])
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", type_jonction="ExtremiteReseau", materiel_href="m1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_JONCTION_INVALIDE: 1}
        assert resultat["nombre_materiels_non_conformes"] == 1

    def test_statut_de_la_jonction_sans_effet(self, tmp_path: Any) -> None:
        """A la difference d'E-7104, ce moteur n'applique aucun filtre de statut."""
        ecrire_collection(str(tmp_path / FICHIER_MATERIEL), [construire_feature_materiel("m1")])
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", statut="Decommissioned", materiel_href="m1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_MATERIEL), [construire_feature_materiel("m1")])
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        _jeu_conforme(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_crs_propage(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_MATERIEL), [construire_feature_materiel("m1")])
        ecrire_collection_avec_crs(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", type_jonction="ExtremiteReseau", materiel_href="m1")],
            "EPSG:2154",
        )
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert "2154" in ecarts["crs"]["properties"]["name"]

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        _jeu_conforme(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "nombre_anomalies",
            "anomalies_par_type",
            "nombre_materiels_analyses",
            "nombre_materiels_non_conformes",
            "nombre_jonctions_analysees",
            "nombre_liens_controles",
            "fichier_materiel_absent",
            "fichier_jonction_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Coherence avec E-7104
# --------------------------------------------------------------------------- #


class TestCoherenceAvecE600:
    """Les deux controles parcourent la meme relation, en sens opposes."""

    def test_memes_types_de_jonction(self) -> None:
        from recostar.controle.conteneur.detection_catalogue_materiel import TYPES_JONCTION_CONTROLES

        assert TYPES_JONCTION_VALIDES is TYPES_JONCTION_CONTROLES

    def test_memes_fichiers_source(self) -> None:
        from recostar.controle.conteneur.detection_catalogue_materiel import FICHIER_JONCTION as E600_JONCTION
        from recostar.controle.conteneur.detection_catalogue_materiel import FICHIER_MATERIEL as E600_MATERIEL

        assert (FICHIER_JONCTION, FICHIER_MATERIEL) == (E600_JONCTION, E600_MATERIEL)

    def test_materiel_orphelin_invisible_pour_e7104(self, tmp_path: Any) -> None:
        """Justification du moteur : E-7104 ne rencontre jamais un materiel orphelin.

        E-7104 itere sur les jonctions ; un materiel qu'aucune jonction ne
        reference lui echappe structurellement. Ce moteur est le seul a le voir.
        """
        from recostar.controle.conteneur.e7104 import executer_controle_cli as executer_e7104

        ecrire_collection(str(tmp_path / FICHIER_MATERIEL), [construire_feature_materiel("m_orphelin")])
        ecrire_collection(str(tmp_path / FICHIER_JONCTION), [])
        assert executer_e7104(str(tmp_path))["nombre_anomalies"] == 0
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 1


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Le rattachement est controle identiquement en V1.0 et V1.1.

    Les champs additionnels de la V1.1 n'interviennent ni dans la resolution du
    lien ni dans la validite du TypeJonction.
    """

    def test_v11_champs_extra_sans_effet(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_MATERIEL),
            [construire_feature_materiel("m1", proprietes_extra={"NumeroLot": "LOT-1"})],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", materiel_href="m1", proprietes_extra={"Commentaire": "note"})],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0


# --------------------------------------------------------------------------- #
# Cascade type / statut et repartition entre les deux controles
# --------------------------------------------------------------------------- #


class TestClassifierLien:
    """La cascade : le type d'abord, le statut ensuite."""

    def test_lien_conforme(self) -> None:
        assert classifier_lien(_lien()) is None

    def test_type_invalide(self) -> None:
        assert classifier_lien(_lien(type_jonction="ExtremiteReseau")) == TYPE_JONCTION_INVALIDE

    def test_statut_invalide(self) -> None:
        assert classifier_lien(_lien(statut="Decommissioned")) == TYPE_STATUT_INVALIDE

    def test_statut_absent(self) -> None:
        """Un statut non renseigne n'est aucun des etats du schema."""
        assert classifier_lien(_lien(statut=None)) == TYPE_STATUT_INVALIDE

    def test_type_invalide_court_circuite_le_statut(self) -> None:
        """Une ExtremiteReseau hors statut n'est signalee qu'une fois."""
        assert classifier_lien(_lien(type_jonction="ExtremiteReseau", statut="Decommissioned")) == (
            TYPE_JONCTION_INVALIDE
        )

    def test_cascade_exhaustive(self) -> None:
        """Tout lien releve d'un des deux codes, ou d'aucun."""
        for type_jonction in ("Jonction", "Derivation", "ExtremiteReseau", None):
            for statut in ("UnderCommissionning", "Decommissioned", None):
                resultat = classifier_lien(_lien(type_jonction=type_jonction, statut=statut))
                assert resultat in (None, TYPE_JONCTION_INVALIDE, TYPE_STATUT_INVALIDE)


class TestRepartitionEntreControles:
    """Chaque controle ne retient que les types de son code."""

    @staticmethod
    def _jeu(tmp_path: Any, type_jonction: str, statut: str) -> None:
        ecrire_collection(str(tmp_path / FICHIER_MATERIEL), [construire_feature_materiel("m1")])
        jonction = construire_feature_jonction("j1", type_jonction=type_jonction, materiel_href="m1")
        jonction["properties"]["Statut"] = statut
        ecrire_collection(str(tmp_path / FICHIER_JONCTION), [jonction])

    def test_types_retenus_disjoints(self) -> None:
        from recostar.controle.conteneur.e7102 import TYPES_RETENUS as TYPES_7102
        from recostar.controle.conteneur.e7103 import TYPES_RETENUS as TYPES_7103

        assert not TYPES_7102 & TYPES_7103

    def test_lien_conforme(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, "Jonction", "UnderCommissionning")
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0
        assert executer_7103(str(tmp_path))["nombre_anomalies"] == 0

    def test_statut_invalide_ne_sort_que_d_e7103(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, "Jonction", "Decommissioned")
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0
        assert executer_7103(str(tmp_path))["anomalies_par_type"] == {TYPE_STATUT_INVALIDE: 1}

    def test_type_invalide_ne_sort_que_d_e7102(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, "ExtremiteReseau", "Decommissioned")
        assert executer_controle_cli(str(tmp_path))["anomalies_par_type"] == {TYPE_JONCTION_INVALIDE: 1}
        assert executer_7103(str(tmp_path))["nombre_anomalies"] == 0

    def test_orphelin_ne_sort_que_d_e7102(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_MATERIEL), [construire_feature_materiel("m1")])
        assert executer_controle_cli(str(tmp_path))["anomalies_par_type"] == {TYPE_JONCTION_ABSENTE: 1}
        assert executer_7103(str(tmp_path))["nombre_anomalies"] == 0

    def test_code_erreur_et_statut_reportes(self, tmp_path: Any) -> None:
        self._jeu(tmp_path, "Derivation", "Projected")
        chemin = executer_7103(str(tmp_path))["sortie"]
        assert chemin is not None
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-7103"
        assert proprietes["statut_jonction"] == "Projected"
