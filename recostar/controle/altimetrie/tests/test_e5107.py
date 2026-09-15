"""
Tests du controle E-5107 (altitude Z non renseignee).

Ce controle reunit sous un meme code deux moteurs, pour un meme
code du verificateur. Les tests de detection restent avec leurs moteurs
(`test_detection_z_absent`, `test_detection_z_nul`) ; on verifie ici ce qui
appartient au controle : la reunion des deux jeux d'ecarts dans une sortie
unique, et les deux perimetres distincts qu'il applique.
"""

import json
import os
from typing import Any

from recostar.controle.altimetrie.e5107 import (
    CODE_CONTROLE,
    FICHIER_SORTIE,
    construire_geojson_ecarts,
    executer_controle_cli,
)
from recostar.controle.altimetrie.tests.utils_tests import (
    construire_feature_avec_proprietes,
    ecrire_collection,
    lire_geojson_depuis,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    FICHIER_CABLE_ELECTRIQUE,
    STATUT_MISE_EN_SERVICE,
)


def _anomalie_z_absent(identifiant: str = "e1") -> dict[str, Any]:
    return {
        "fichier_source": FICHIER_CABLE_ELECTRIQUE,
        "id_entite": identifiant,
        "type_geometrie": "LineString",
        "geometrie": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]},
    }


def _anomalie_z_nul(identifiant: str = "e2") -> dict[str, Any]:
    return {
        "fichier_source": FICHIER_CABLE_ELECTRIQUE,
        "id_entite": identifiant,
        "type_geometrie": "LineString",
        "indice_sommet": 1,
        "coordonnees": [1.0, 1.0, 0.0],
    }


class TestConstruireGeojsonEcarts:
    """Reunion des deux formes d'anomalie dans une collection unique."""

    def test_collection_vide(self) -> None:
        assert construire_geojson_ecarts([], [], "1.1") == {"type": "FeatureCollection", "features": []}

    def test_les_deux_formes_coexistent(self) -> None:
        """Un seul fichier porte les deux types : c'est l'objet de la fusion."""
        geojson = construire_geojson_ecarts([_anomalie_z_absent()], [_anomalie_z_nul()], "1.1")
        types = [f["properties"]["type_anomalie"] for f in geojson["features"]]
        assert types == ["absence_coordonnee_z", "z_null"]

    def test_meme_code_pour_les_deux_formes(self) -> None:
        """Le code ne distingue pas les deux formes ; le type d'anomalie, si."""
        geojson = construire_geojson_ecarts([_anomalie_z_absent()], [_anomalie_z_nul()], "1.1")
        codes = {f["properties"]["code_controle"] for f in geojson["features"]}
        assert codes == {CODE_CONTROLE}

    def test_geometrie_de_l_entite_pour_le_z_absent(self) -> None:
        """L'anomalie porte sur l'entite entiere : sa geometrie est conservee."""
        feature = construire_geojson_ecarts([_anomalie_z_absent()], [], "1.1")["features"][0]
        assert feature["geometry"]["type"] == "LineString"

    def test_geometrie_du_sommet_pour_le_z_nul(self) -> None:
        """L'anomalie est localisee : la sortie pointe le sommet fautif."""
        feature = construire_geojson_ecarts([], [_anomalie_z_nul()], "1.1")["features"][0]
        assert feature["geometry"] == {"type": "Point", "coordinates": [1.0, 1.0, 0.0]}
        assert feature["properties"]["indice_sommet"] == 1

    def test_version_reportee_sur_le_z_nul(self) -> None:
        feature = construire_geojson_ecarts([], [_anomalie_z_nul()], "1.0")["features"][0]
        assert feature["properties"]["version"] == "1.0"

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], [], "1.1", crs)["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        assert "crs" not in construire_geojson_ecarts([], [], "1.1")


def _ecrire_cable(repertoire: str, coordonnees: list[list[float]], statut: str = STATUT_MISE_EN_SERVICE) -> None:
    """Ecrit une couche de cables portant une entite au statut donne."""
    feature = construire_feature_avec_proprietes("c1", "LineString", coordonnees, {"Statut": statut})
    ecrire_collection(os.path.join(repertoire, FICHIER_CABLE_ELECTRIQUE), [feature])


class TestCli:
    """Execution complete du controle."""

    def test_repertoire_inexistant_sans_objet(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path / "absent"))
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_aucun_geojson_sans_objet(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

    def test_entite_2d_detectee(self, tmp_path: Any) -> None:
        _ecrire_cable(str(tmp_path), [[0.0, 0.0], [1.0, 1.0]])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["anomalies_par_type"]["absence_coordonnee_z"] == 1

    def test_sommet_a_z_nul_detecte(self, tmp_path: Any) -> None:
        _ecrire_cable(str(tmp_path), [[0.0, 0.0, 5.0], [1.0, 1.0, 0.0]])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"]["z_null"] == 1

    def test_les_deux_formes_dans_un_seul_fichier(self, tmp_path: Any) -> None:
        """La sortie unique est la raison d'etre de la fusion."""
        _ecrire_cable(str(tmp_path), [[0.0, 0.0], [1.0, 1.0]])
        ecrire_collection(
            os.path.join(str(tmp_path), "RPD_CableTerre_Reco.geojson"),
            [
                construire_feature_avec_proprietes(
                    "t1", "LineString", [[0.0, 0.0, 3.0], [2.0, 2.0, 0.0]], {"Statut": STATUT_MISE_EN_SERVICE}
                )
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert set(resultat["anomalies_par_type"]) == {"absence_coordonnee_z", "z_null"}
        assert os.path.basename(resultat["sortie"]) == FICHIER_SORTIE

    def test_perimetres_distincts_des_deux_moteurs(self, tmp_path: Any) -> None:
        """Une entite hors statut reste 2D-controlee mais echappe au Z nul.

        C'est la difference de perimetre que la fusion devait preserver : une
        geometrie plane est fautive quel que soit le statut de l'ouvrage.
        """
        _ecrire_cable(str(tmp_path), [[0.0, 0.0], [1.0, 1.0]], statut="Functional")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"].get("absence_coordonnee_z") == 1
        assert "z_null" not in resultat["anomalies_par_type"]

    def test_z_nul_ignore_hors_statut(self, tmp_path: Any) -> None:
        _ecrire_cable(str(tmp_path), [[0.0, 0.0, 3.0], [1.0, 1.0, 0.0]], statut="Functional")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0

    def test_aucune_anomalie_n_ecrit_pas_de_fichier(self, tmp_path: Any) -> None:
        _ecrire_cable(str(tmp_path), [[0.0, 0.0, 3.0], [1.0, 1.0, 4.0]])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["sortie"] is None

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        entree = tmp_path / "entree"
        entree.mkdir()
        sortie = tmp_path / "sortie"
        _ecrire_cable(str(entree), [[0.0, 0.0], [1.0, 1.0]])
        resultat = executer_controle_cli(str(entree), str(sortie))
        assert resultat["sortie"] == str(sortie / FICHIER_SORTIE)
        assert lire_geojson_depuis(resultat["sortie"])["features"]

    def test_rapport_distingue_les_deux_perimetres(self, tmp_path: Any) -> None:
        """Les deux moteurs ne lisent pas les memes couches : le rapport le dit."""
        _ecrire_cable(str(tmp_path), [[0.0, 0.0], [1.0, 1.0]])
        resultat = executer_controle_cli(str(tmp_path))
        assert "fichiers_analyses" in resultat
        assert "fichiers_analyses_z_nul" in resultat

    def test_sortie_serialisable(self, tmp_path: Any) -> None:
        """Le rapport est ecrit en JSON par le pipeline : rien d'inserialisable."""
        _ecrire_cable(str(tmp_path), [[0.0, 0.0], [1.0, 1.0]])
        assert json.dumps(executer_controle_cli(str(tmp_path)), ensure_ascii=False)
