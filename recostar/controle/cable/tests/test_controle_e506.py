"""
Tests du controle E506 : raccordement des cables aux noeuds du reseau.

Couvre :
  - la provenance des types de noeuds (source de verite : module de conversion)
  - l'indexation des noeuds par cable
  - l'extraction des extremites topologiques (LineString / MultiLineString)
  - la regle 1 : defaut relationnel et defaut topologique (bloquant)
  - la regle 2 : raccordement des cables de terre, deux sens de liaison (majeur)
  - la construction du GeoJSON d'ecarts
  - l'execution CLI complete
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import os
from typing import Any

from controle_e506 import (
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_CABLE_TERRE,
    FICHIER_SORTIE,
    FICHIER_TERRE,
    PRIORITE_CABLE_ELECTRIQUE,
    PRIORITE_CABLE_TERRE,
    STATUT_CONTROLE,
    TYPE_CABLE_TERRE_NON_RACCORDE,
    TYPE_EXTREMITE_NON_RACCORDEE,
    TYPE_NOEUD_UNIQUE,
    TYPE_SANS_NOEUD,
    NoeudRaccorde,
    charger_liaisons_terre,
    compter_anomalies_par_type,
    compter_cables_controles,
    construire_geojson_ecarts,
    detecter_anomalies_cable_electrique,
    detecter_anomalies_cable_terre,
    executer_controle_cli,
    indexer_noeuds_par_cable,
)
from utils_cable import charger_types_noeuds_reseau
from utils_geometrie import extraire_extremites
from utils_tests import construire_feature_noeud, ecrire_collection

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# Deux extremites separees de 100 m sur l'axe X
EXTREMITE_A: list[float] = [0.0, 0.0]
EXTREMITE_B: list[float] = [100.0, 0.0]


def _feature_cable(
    identifiant: str,
    coordonnees: list[list[float]] | None = None,
    statut: str = STATUT_CONTROLE,
) -> dict[str, Any]:
    """Feature GeoJSON d'un cable electrique en LineString."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "Statut": statut},
        "geometry": {"type": "LineString", "coordinates": coordonnees or [EXTREMITE_A, EXTREMITE_B]},
    }


def _feature_cable_terre(
    identifiant: str,
    noeudreseau_href: Any = None,
    statut: str = STATUT_CONTROLE,
) -> dict[str, Any]:
    """Feature GeoJSON d'un cable de terre."""
    return {
        "type": "Feature",
        "properties": {
            "id": identifiant,
            "Statut": statut,
            "noeudreseau_href": noeudreseau_href,
        },
        "geometry": {"type": "LineString", "coordinates": [EXTREMITE_A, EXTREMITE_B]},
    }


def _noeud(identifiant: str, point: tuple[float, float] | None) -> NoeudRaccorde:
    """NoeudRaccorde minimal pour les tests de detection."""
    return NoeudRaccorde(type_entite="RPD_Jonction_Reco", id_entite=identifiant, point=point)


# --------------------------------------------------------------------------- #
# Source de verite des types de noeuds
# --------------------------------------------------------------------------- #


class TestChargerTypesNoeudsReseau:
    """Tests de charger_types_noeuds_reseau (import depuis le module de conversion)."""

    def test_retourne_les_types_de_noeuds(self) -> None:
        types = charger_types_noeuds_reseau()
        assert "RPD_Jonction_Reco" in types
        assert "RPD_Terre_Reco" in types
        assert "RPD_SupportModules_Reco" in types

    def test_exclut_les_cheminements_et_les_cables(self) -> None:
        """Les cheminements portent aussi cables_href mais ne sont pas des noeuds."""
        types = charger_types_noeuds_reseau()
        assert "RPD_Fourreau_Reco" not in types
        assert "RPD_Aerien_Reco" not in types
        assert "RPD_CableElectrique_Reco" not in types

    def test_identique_a_la_constante_de_conversion(self) -> None:
        """La liste n'est pas redefinie dans le controle : elle vient de la conversion."""
        import importlib.util
        from pathlib import Path

        chemin = Path(__file__).resolve().parents[3] / "conversion" / "conversion_V1_1" / "geojson_to_recostar.py"
        specification = importlib.util.spec_from_file_location("_conversion_test", chemin)
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        assert charger_types_noeuds_reseau() == tuple(module.TYPES_NOEUDS_RESEAU)

    def test_v1_0_et_v1_1_declarent_les_memes_types(self) -> None:
        """Le controle est agnostique de version : les deux listes coincident."""
        import importlib.util
        from pathlib import Path

        racine = Path(__file__).resolve().parents[3] / "conversion"
        listes = []
        for version in ("conversion_V1", "conversion_V1_1"):
            specification = importlib.util.spec_from_file_location(
                f"_conv_{version}", racine / version / "geojson_to_recostar.py"
            )
            assert specification is not None and specification.loader is not None
            module = importlib.util.module_from_spec(specification)
            specification.loader.exec_module(module)
            listes.append(tuple(module.TYPES_NOEUDS_RESEAU))
        assert listes[0] == listes[1]

    def test_resultat_mis_en_cache(self) -> None:
        """lru_cache : le module de conversion n'est charge qu'une fois."""
        assert charger_types_noeuds_reseau() is charger_types_noeuds_reseau()


# --------------------------------------------------------------------------- #
# Extraction des extremites
# --------------------------------------------------------------------------- #


class TestExtraireExtremites:
    """Tests de extraire_extremites."""

    def test_linestring_simple(self) -> None:
        geometrie = {"type": "LineString", "coordinates": [[0.0, 0.0], [50.0, 0.0], [100.0, 0.0]]}
        assert set(extraire_extremites(geometrie)) == {(0.0, 0.0), (100.0, 0.0)}

    def test_ignore_la_composante_z(self) -> None:
        geometrie = {"type": "LineString", "coordinates": [[0.0, 0.0, 12.0], [100.0, 0.0, 30.0]]}
        assert set(extraire_extremites(geometrie)) == {(0.0, 0.0), (100.0, 0.0)}

    def test_multilinestring_parties_chainees_desordonnees(self) -> None:
        """Cas reel : les parties ne sont ni ordonnees ni orientees.

        La partie 1 se raccroche a la partie 0 par son extremite finale, ce qui
        rend faux le couple (premier sommet, dernier sommet) apres mise a plat.
        """
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [
                [[10.0, 0.0], [20.0, 0.0]],  # partie 0 : E1 -> E2
                [[30.0, 0.0], [20.0, 0.0]],  # partie 1 : E3 -> E2 (orientation inverse)
            ],
        }
        assert set(extraire_extremites(geometrie)) == {(10.0, 0.0), (30.0, 0.0)}

    def test_multilinestring_bouclee_sans_extremite(self) -> None:
        """Une geometrie fermee n'a aucune extremite libre."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0], [10.0, 0.0]],
                [[10.0, 0.0], [0.0, 0.0]],
            ],
        }
        assert extraire_extremites(geometrie) == []

    def test_geometrie_absente(self) -> None:
        assert extraire_extremites(None) == []

    def test_geometrie_ponctuelle_ignoree(self) -> None:
        assert extraire_extremites({"type": "Point", "coordinates": [0.0, 0.0]}) == []

    def test_partie_a_un_seul_sommet_ignoree(self) -> None:
        geometrie = {"type": "MultiLineString", "coordinates": [[[0.0, 0.0]], [[5.0, 0.0], [9.0, 0.0]]]}
        assert set(extraire_extremites(geometrie)) == {(5.0, 0.0), (9.0, 0.0)}


# --------------------------------------------------------------------------- #
# Indexation des noeuds
# --------------------------------------------------------------------------- #


class TestIndexerNoeudsParCable:
    """Tests de indexer_noeuds_par_cable."""

    def test_index_multi_couches(self, tmp_path: Any) -> None:
        """Les noeuds de couches differentes alimentent le meme index."""
        ecrire_collection(
            os.path.join(tmp_path, "RPD_Jonction_Reco.geojson"),
            [construire_feature_noeud("n1", "c1", EXTREMITE_A)],
        )
        ecrire_collection(
            os.path.join(tmp_path, "RPD_SupportModules_Reco.geojson"),
            [construire_feature_noeud("n2", "c1", EXTREMITE_B)],
        )
        index, _ = indexer_noeuds_par_cable(str(tmp_path))
        assert len(index["c1"]) == 2
        assert {n.type_entite for n in index["c1"]} == {"RPD_Jonction_Reco", "RPD_SupportModules_Reco"}

    def test_noeud_multi_cables(self, tmp_path: Any) -> None:
        """Un noeud citant plusieurs cables alimente une entree par cable."""
        ecrire_collection(
            os.path.join(tmp_path, "RPD_Jonction_Reco.geojson"),
            [construire_feature_noeud("n1", "c1,c2", EXTREMITE_A)],
        )
        index, _ = indexer_noeuds_par_cable(str(tmp_path))
        assert set(index) == {"c1", "c2"}

    def test_noeud_sans_cables_href_ignore(self, tmp_path: Any) -> None:
        ecrire_collection(
            os.path.join(tmp_path, "RPD_Jonction_Reco.geojson"),
            [construire_feature_noeud("n1", None, EXTREMITE_A)],
        )
        index, _ = indexer_noeuds_par_cable(str(tmp_path))
        assert index == {}

    def test_fichiers_absents_signales(self, tmp_path: Any) -> None:
        """Aucune couche presente : tous les fichiers sont listes, sans erreur."""
        index, absents = indexer_noeuds_par_cable(str(tmp_path))
        assert index == {}
        assert len(absents) == len(charger_types_noeuds_reseau())


# --------------------------------------------------------------------------- #
# Regle 1 : cables electriques
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesCableElectrique:
    """Tests de detecter_anomalies_cable_electrique."""

    def test_cable_conforme(self) -> None:
        """Un noeud a chaque extremite : aucune anomalie."""
        index = {"c1": [_noeud("n1", (0.0, 0.0)), _noeud("n2", (100.0, 0.0))]}
        assert detecter_anomalies_cable_electrique([_feature_cable("c1")], index) == []

    def test_cable_sans_aucun_noeud(self) -> None:
        anomalies = detecter_anomalies_cable_electrique([_feature_cable("c1")], {})
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_SANS_NOEUD
        assert anomalies[0]["nombre_noeuds"] == 0

    def test_cable_un_seul_noeud(self) -> None:
        index = {"c1": [_noeud("n1", (0.0, 0.0))]}
        anomalies = detecter_anomalies_cable_electrique([_feature_cable("c1")], index)
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_NOEUD_UNIQUE
        assert anomalies[0]["nombre_noeuds"] == 1

    def test_deux_noeuds_du_meme_cote(self) -> None:
        """Defaut topologique : les deux noeuds sont proches de la meme extremite."""
        index = {"c1": [_noeud("n1", (0.0, 0.0)), _noeud("n2", (5.0, 0.0))]}
        anomalies = detecter_anomalies_cable_electrique([_feature_cable("c1")], index)
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_EXTREMITE_NON_RACCORDEE
        assert anomalies[0]["nombre_extremites_libres"] == 1

    def test_defauts_exclusifs_une_seule_anomalie_par_cable(self) -> None:
        """Un cable a un seul noeud ne cumule pas les deux defauts."""
        index = {"c1": [_noeud("n1", (0.0, 0.0))]}
        anomalies = detecter_anomalies_cable_electrique([_feature_cable("c1")], index)
        assert len(anomalies) == 1

    def test_noeud_eloigne_mais_plus_proche_reste_conforme(self) -> None:
        """L'affectation est relative : aucun seuil de distance n'est applique.

        Cas reel : un poste electrique represente par un point a plusieurs
        metres du bout de cable qu'il raccorde reste conforme.
        """
        index = {"c1": [_noeud("n1", (-25.0, 3.0)), _noeud("n2", (130.0, 8.0))]}
        assert detecter_anomalies_cable_electrique([_feature_cable("c1")], index) == []

    def test_trois_noeuds_couvrant_les_deux_extremites(self) -> None:
        """Un noeud intermediaire supplementaire ne rend pas le cable non conforme."""
        index = {
            "c1": [
                _noeud("n1", (0.0, 0.0)),
                _noeud("n2", (100.0, 0.0)),
                _noeud("n3", (60.0, 0.0)),
            ]
        }
        assert detecter_anomalies_cable_electrique([_feature_cable("c1")], index) == []

    def test_statut_hors_perimetre_ignore(self) -> None:
        cable = _feature_cable("c1", statut="Commissioned")
        assert detecter_anomalies_cable_electrique([cable], {}) == []

    def test_statut_absent_ignore(self) -> None:
        cable = {"type": "Feature", "properties": {"id": "c1"}, "geometry": None}
        assert detecter_anomalies_cable_electrique([cable], {}) == []

    def test_geometrie_absente_seul_le_relationnel_s_applique(self) -> None:
        """Sans geometrie, deux noeuds suffisent a valider le cable."""
        cable = {
            "type": "Feature",
            "properties": {"id": "c1", "Statut": STATUT_CONTROLE},
            "geometry": None,
        }
        index = {"c1": [_noeud("n1", (0.0, 0.0)), _noeud("n2", (5.0, 0.0))]}
        assert detecter_anomalies_cable_electrique([cable], index) == []

    def test_cable_boucle_echappe_au_controle_topologique(self) -> None:
        """Une geometrie fermee n'a pas deux bouts : seul le relationnel joue."""
        cable = _feature_cable("c1", coordonnees=[[0.0, 0.0], [50.0, 50.0], [0.0, 0.0]])
        index = {"c1": [_noeud("n1", (0.0, 0.0)), _noeud("n2", (0.0, 0.0))]}
        assert detecter_anomalies_cable_electrique([cable], index) == []

    def test_noeuds_sans_geometrie_n_induisent_pas_d_anomalie(self) -> None:
        """Deux noeuds non localises : le raccordement relationnel fait foi."""
        index = {"c1": [_noeud("n1", None), _noeud("n2", None)]}
        assert detecter_anomalies_cable_electrique([_feature_cable("c1")], index) == []


# --------------------------------------------------------------------------- #
# Regle 2 : cables de terre
# --------------------------------------------------------------------------- #


class TestChargerLiaisonsTerre:
    """Tests de charger_liaisons_terre."""

    def test_charge_les_deux_sens(self, tmp_path: Any) -> None:
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_TERRE),
            [construire_feature_noeud("terre1", "ct1")],
        )
        ids_terre, ids_cables, absent = charger_liaisons_terre(str(tmp_path))
        assert ids_terre == {"terre1"}
        assert ids_cables == {"ct1"}
        assert absent is False

    def test_fichier_absent(self, tmp_path: Any) -> None:
        ids_terre, ids_cables, absent = charger_liaisons_terre(str(tmp_path))
        assert ids_terre == set()
        assert ids_cables == set()
        assert absent is True


class TestDetecterAnomaliesCableTerre:
    """Tests de detecter_anomalies_cable_terre."""

    def test_lie_via_noeudreseau_href(self) -> None:
        """Sens 1 : le cable designe la prise de terre."""
        cable = _feature_cable_terre("ct1", noeudreseau_href="terre1")
        assert detecter_anomalies_cable_terre([cable], {"terre1"}, set()) == []

    def test_lie_via_cables_href_de_la_terre(self) -> None:
        """Sens 2 : la prise de terre designe le cable."""
        cable = _feature_cable_terre("ct1", noeudreseau_href=None)
        assert detecter_anomalies_cable_terre([cable], set(), {"ct1"}) == []

    def test_non_lie(self) -> None:
        cable = _feature_cable_terre("ct1", noeudreseau_href=None)
        anomalies = detecter_anomalies_cable_terre([cable], {"terre1"}, set())
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_CABLE_TERRE_NON_RACCORDE

    def test_reference_vers_une_terre_inexistante(self) -> None:
        """Un href pointant vers une entite absente ne vaut pas raccordement."""
        cable = _feature_cable_terre("ct1", noeudreseau_href="terre_fantome")
        anomalies = detecter_anomalies_cable_terre([cable], {"terre1"}, set())
        assert len(anomalies) == 1
        assert anomalies[0]["noeudreseau_href"] == "terre_fantome"

    def test_aucune_terre_dans_le_jeu_de_donnees(self) -> None:
        """Sans aucune prise de terre, tout cable de terre controle est en anomalie."""
        cable = _feature_cable_terre("ct1", noeudreseau_href="terre1")
        assert len(detecter_anomalies_cable_terre([cable], set(), set())) == 1

    def test_statut_hors_perimetre_ignore(self) -> None:
        cable = _feature_cable_terre("ct1", statut="Commissioned")
        assert detecter_anomalies_cable_terre([cable], set(), set()) == []


# --------------------------------------------------------------------------- #
# Comptages
# --------------------------------------------------------------------------- #


class TestComptages:
    """Tests de compter_cables_controles et compter_anomalies_par_type."""

    def test_compter_cables_controles(self) -> None:
        features = [
            _feature_cable("c1"),
            _feature_cable("c2", statut="Commissioned"),
            _feature_cable("c3"),
        ]
        assert compter_cables_controles(features) == 2

    def test_compter_anomalies_par_type(self) -> None:
        anomalies = [
            {"type_anomalie": TYPE_SANS_NOEUD},
            {"type_anomalie": TYPE_SANS_NOEUD},
            {"type_anomalie": TYPE_CABLE_TERRE_NON_RACCORDE},
        ]
        assert compter_anomalies_par_type(anomalies) == {
            TYPE_SANS_NOEUD: 2,
            TYPE_CABLE_TERRE_NON_RACCORDE: 1,
        }


# --------------------------------------------------------------------------- #
# GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def test_priorite_par_regle(self) -> None:
        """Les deux regles cohabitent dans un fichier avec des priorites distinctes."""
        anomalies = [
            {"type_anomalie": TYPE_SANS_NOEUD, "id_cable": "c1", "nombre_noeuds": 0, "geometrie": None},
            {"type_anomalie": TYPE_CABLE_TERRE_NON_RACCORDE, "id_cable": "ct1", "geometrie": None},
        ]
        resultat = construire_geojson_ecarts(anomalies)
        priorites = [f["properties"]["priorite"] for f in resultat["features"]]
        assert priorites == [PRIORITE_CABLE_ELECTRIQUE, PRIORITE_CABLE_TERRE]

    def test_champs_specifiques_omis_si_absents(self) -> None:
        """Une anomalie de terre ne porte pas les champs de la regle electrique."""
        anomalies = [{"type_anomalie": TYPE_CABLE_TERRE_NON_RACCORDE, "id_cable": "ct1", "geometrie": None}]
        props = construire_geojson_ecarts(anomalies)["features"][0]["properties"]
        assert "nombre_extremites_libres" not in props
        assert "nombre_noeuds" not in props

    def test_geometrie_du_cable_conservee(self) -> None:
        geometrie = {"type": "LineString", "coordinates": [EXTREMITE_A, EXTREMITE_B]}
        anomalies = [{"type_anomalie": TYPE_SANS_NOEUD, "id_cable": "c1", "nombre_noeuds": 0, "geometrie": geometrie}]
        assert construire_geojson_ecarts(anomalies)["features"][0]["geometry"] == geometrie

    def test_crs_propage(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], crs)["crs"] == crs

    def test_sans_crs(self) -> None:
        assert "crs" not in construire_geojson_ecarts([])


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_introuvable(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(os.path.join(tmp_path, "absent"))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        """Aucun fichier : succes, ecarts vides, fichiers signales absents."""
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["fichier_cable_electrique_absent"] is True
        assert resultat["fichier_terre_absent"] is True

    def test_jeu_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        ecrire_collection(
            os.path.join(tmp_path, "RPD_Jonction_Reco.geojson"),
            [
                construire_feature_noeud("n1", "c1", EXTREMITE_A),
                construire_feature_noeud("n2", "c1", EXTREMITE_B),
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_electriques_controles"] == 1

    def test_anomalies_des_deux_regles(self, tmp_path: Any) -> None:
        """Les deux regles alimentent le meme fichier d'ecarts."""
        ecrire_collection(os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_CABLE_TERRE),
            [_feature_cable_terre("ct1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 2
        assert resultat["anomalies_par_type"] == {
            TYPE_SANS_NOEUD: 1,
            TYPE_CABLE_TERRE_NON_RACCORDE: 1,
        }

    def test_fichier_sortie_ecrit(self, tmp_path: Any) -> None:
        ecrire_collection(os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert os.path.isfile(resultat["sortie"])
        assert resultat["sortie"].endswith(FICHIER_SORTIE)

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        entree = tmp_path / "entree"
        sortie = tmp_path / "sortie"
        entree.mkdir()
        ecrire_collection(os.path.join(entree, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        resultat = executer_controle_cli(str(entree), str(sortie))
        assert os.path.isfile(os.path.join(sortie, FICHIER_SORTIE))
        assert resultat["succes"] is True

    def test_priorites_exposees(self, tmp_path: Any) -> None:
        """Le rapport annonce la priorite de chaque type d'anomalie."""
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["priorites"][TYPE_SANS_NOEUD] == PRIORITE_CABLE_ELECTRIQUE
        assert resultat["priorites"][TYPE_EXTREMITE_NON_RACCORDEE] == PRIORITE_CABLE_ELECTRIQUE
        assert resultat["priorites"][TYPE_CABLE_TERRE_NON_RACCORDE] == PRIORITE_CABLE_TERRE


# --------------------------------------------------------------------------- #
# Compatibilite V1.0 / V1.1
# --------------------------------------------------------------------------- #


class TestCompatibiliteVersions:
    """Le controle doit se comporter identiquement en V1.0 et V1.1."""

    def test_champs_additionnels_v1_1_sans_effet(self, tmp_path: Any) -> None:
        """Etiquette et Commentaire (V1.1) n'influencent pas le resultat."""
        ecrire_collection(os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        ecrire_collection(
            os.path.join(tmp_path, "RPD_Jonction_Reco.geojson"),
            [
                construire_feature_noeud(
                    "n1", "c1", EXTREMITE_A, proprietes_extra={"Commentaire": "essai", "Etiquette": "E"}
                ),
                construire_feature_noeud("n2", "c1", EXTREMITE_B),
            ],
        )
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_cables_href_separe_par_espaces(self, tmp_path: Any) -> None:
        """La convention d'espacement (E202) est acceptee comme la virgule."""
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1"), _feature_cable("c2")],
        )
        ecrire_collection(
            os.path.join(tmp_path, "RPD_Jonction_Reco.geojson"),
            [
                construire_feature_noeud("n1", "c1 c2", EXTREMITE_A),
                construire_feature_noeud("n2", "c1,c2", EXTREMITE_B),
            ],
        )
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0
