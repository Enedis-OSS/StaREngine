#!/usr/bin/env python3
"""
Tests de la sortie JSON harmonisee de la famille de structuration.

Couvre la conversion des six formes d'erreur vers les huit champs communs, la
resolution du code du verificateur depuis le rang du controle, et l'agregation
des rapports en un fichier unique.

Le dernier test est le verrou de l'ensemble : il confronte la nomenclature
redeclaree ici a celle du paquet parent. La duplication est assumee — les
modules de `xsd_structuration/` ne dependent pas de `fonctions_communes` —, mais
une divergence entre les deux doit faire echouer la suite.
"""

import json
from typing import Any

from recostar.controle.xsd_structuration.sortie_structuration import (
    CHAMP_CODE,
    CHAMP_CRITICITE,
    CHAMP_DESIGNATION_RPD,
    CHAMP_FAMILLE_CONTROLE,
    CHAMP_ID_GML,
    CHAMP_ID_GML_ASSOCIE,
    CHAMP_LIBELLE,
    CHAMPS_SORTIE,
    FAMILLE,
    agreger_rapports_structuration,
    construire_info,
    harmoniser_erreur,
    nom_fichier_sortie,
)

# Erreur de geometrie (E0115 / E0015), forme d'`ErreurGeometrie`.
_ERREUR_GEOMETRIE: dict[str, Any] = {
    "type_rpd": "RPD_PleineTerre_Reco",
    "gml_id": "id85823ae0",
    "type_erreur": "GEOMETRIE_INVALIDE",
    "type_geometrie": "LineString",
    "positions_trouvees": 0,
    "positions_attendues": 2,
    "severite": "ERREUR",
    "priorite": "forte",
    "message": "La géométrie LineString ne porte aucune position.",
}

# Erreur d'en-tete (E0113 / E0013), forme d'`ErreurEntete` : ni type_rpd ni gml_id.
_ERREUR_ENTETE: dict[str, Any] = {
    "code": "SCHEMA_LOCATION_VERSION_INCORRECTE",
    "severite": "ERREUR",
    "priorite": "moyenne",
    "element": "xsi:schemaLocation",
    "valeur_trouvee": "…/raw/main/…",
    "valeur_attendue": "URL contenant '/raw/RecoStar-v1.0/'",
    "message": "schemaLocation pointe vers la branche 'main'.",
}


class TestHarmoniserErreur:
    """Conversion vers les huit champs, quelle que soit la forme de l'erreur."""

    def test_les_huit_champs_et_rien_d_autre(self) -> None:
        assert tuple(harmoniser_erreur(_ERREUR_GEOMETRIE, "E0015")) == CHAMPS_SORTIE

    def test_schema_identique_pour_une_autre_forme_d_erreur(self) -> None:
        """Le point de la demande : six formes d'erreur, une seule structure."""
        assert tuple(harmoniser_erreur(_ERREUR_ENTETE, "E0013")) == CHAMPS_SORTIE

    def test_code_resolu_depuis_le_rang_du_controle(self) -> None:
        """Une règle ne se résout qu'au rang du contrôle qui l'émet."""
        assert harmoniser_erreur(_ERREUR_GEOMETRIE, "E0015")[CHAMP_CODE] == "E-1108"

    def test_code_de_l_entete(self) -> None:
        assert harmoniser_erreur(_ERREUR_ENTETE, "E0013")[CHAMP_CODE] == "E-0010"

    def test_code_se_replie_sur_le_controle(self) -> None:
        """Une règle sans code du vérificateur garde l'identité du contrôle."""
        erreur = {**_ERREUR_GEOMETRIE, "type_erreur": "REGLE_SANS_CODE_CONNU"}
        assert harmoniser_erreur(erreur, "E0110")[CHAMP_CODE] is not None

    def test_criticite(self) -> None:
        assert harmoniser_erreur(_ERREUR_GEOMETRIE, "E0015")[CHAMP_CRITICITE] == "forte"

    def test_criticite_absente_se_replie_sur_le_defaut(self) -> None:
        erreur = {k: v for k, v in _ERREUR_GEOMETRIE.items() if k != "priorite"}
        assert harmoniser_erreur(erreur, "E0015")[CHAMP_CRITICITE] == "forte"

    def test_libelle_depuis_type_erreur(self) -> None:
        assert harmoniser_erreur(_ERREUR_GEOMETRIE, "E0015")[CHAMP_LIBELLE] == "GEOMETRIE_INVALIDE"

    def test_libelle_depuis_code(self) -> None:
        """`ErreurEntete` nomme sa règle `code`, non `type_erreur`."""
        libelle = harmoniser_erreur(_ERREUR_ENTETE, "E0013")[CHAMP_LIBELLE]
        assert libelle == "SCHEMA_LOCATION_VERSION_INCORRECTE"

    def test_libelle_depuis_regle(self) -> None:
        """`ErreurMetier` la nomme `regle`."""
        erreur = {"regle": "R001_CABLE_ELEC_EN_ATTENTE", "message": "x", "priorite": "forte"}
        assert harmoniser_erreur(erreur, "E0011")[CHAMP_LIBELLE] == "R001_CABLE_ELEC_EN_ATTENTE"

    def test_famille(self) -> None:
        assert harmoniser_erreur(_ERREUR_GEOMETRIE, "E0015")[CHAMP_FAMILLE_CONTROLE] == FAMILLE

    def test_designation_depuis_type_rpd(self) -> None:
        assert harmoniser_erreur(_ERREUR_GEOMETRIE, "E0015")[CHAMP_DESIGNATION_RPD] == "RPD_PleineTerre_Reco"

    def test_designation_vide_sans_type_rpd(self) -> None:
        """L'en-tête porte sur le fichier, non sur un objet RPD."""
        assert harmoniser_erreur(_ERREUR_ENTETE, "E0013")[CHAMP_DESIGNATION_RPD] == ""

    def test_id_gml(self) -> None:
        assert harmoniser_erreur(_ERREUR_GEOMETRIE, "E0015")[CHAMP_ID_GML] == "id85823ae0"

    def test_id_gml_vide_sans_identifiant(self) -> None:
        assert harmoniser_erreur(_ERREUR_ENTETE, "E0013")[CHAMP_ID_GML] == ""

    def test_marqueur_sans_id_ramene_a_vide(self) -> None:
        """Les moteurs écrivent « <sans id> » : la sortie n'a qu'une forme du vide."""
        erreur = {**_ERREUR_GEOMETRIE, "gml_id": "<sans id>"}
        assert harmoniser_erreur(erreur, "E0015")[CHAMP_ID_GML] == ""

    def test_id_associe_toujours_vide(self) -> None:
        """La structuration ne met qu'une entité en cause, mais le champ existe."""
        assert harmoniser_erreur(_ERREUR_GEOMETRIE, "E0015")[CHAMP_ID_GML_ASSOCIE] == ""


class TestConstruireInfo:
    """INFO : le message, augmenté du détail technique."""

    def test_message_repris(self) -> None:
        assert "aucune position" in construire_info(_ERREUR_GEOMETRIE)

    def test_detail_replie(self) -> None:
        info = construire_info(_ERREUR_GEOMETRIE)
        assert "positions_trouvees : 0" in info
        assert "positions_attendues : 2" in info

    def test_champs_deja_rendus_non_repetes(self) -> None:
        info = construire_info(_ERREUR_GEOMETRIE)
        for interdit in ("type_rpd", "gml_id", "type_erreur", "priorite", "severite"):
            assert interdit not in info

    def test_valeurs_vides_ignorees(self) -> None:
        assert construire_info({"message": "x", "position": None, "contexte": ""}) == "x"

    def test_sans_message(self) -> None:
        assert construire_info({"ligne": 12}) == "ligne : 12"


class TestAgregerRapports:
    """Fusion des rapports de la famille en un fichier unique."""

    def _ecrire_rapport(self, dossier, nom: str, type_controle: str, erreurs: list[dict[str, Any]]) -> str:
        chemin = str(dossier / nom)
        with open(chemin, "w", encoding="utf-8") as fichier:
            json.dump({"type_controle": type_controle, "erreurs": erreurs}, fichier)
        return chemin

    def test_fichier_unique_produit(self, tmp_path) -> None:
        a = self._ecrire_rapport(tmp_path, "j_controle_e0015.json", "E0015_GEOMETRIE", [_ERREUR_GEOMETRIE])
        b = self._ecrire_rapport(tmp_path, "j_controle_e0013.json", "E0013_ENTETE", [_ERREUR_ENTETE])
        resultat = agreger_rapports_structuration([a, b], str(tmp_path / "j.gml"), str(tmp_path))
        assert resultat["nombre_anomalies"] == 2
        assert resultat["rapports_agreges"] == 2

    def test_rapports_sources_supprimes(self, tmp_path) -> None:
        import os

        a = self._ecrire_rapport(tmp_path, "j_controle_e0015.json", "E0015_GEOMETRIE", [_ERREUR_GEOMETRIE])
        agreger_rapports_structuration([a], str(tmp_path / "j.gml"), str(tmp_path))
        assert not os.path.isfile(a)
        restants = sorted(n for n in os.listdir(tmp_path) if n.endswith(".json"))
        assert restants == [nom_fichier_sortie("j.gml")]

    def test_sources_conservees_sur_demande(self, tmp_path) -> None:
        import os

        a = self._ecrire_rapport(tmp_path, "j_controle_e0015.json", "E0015_GEOMETRIE", [_ERREUR_GEOMETRIE])
        agreger_rapports_structuration([a], str(tmp_path / "j.gml"), str(tmp_path), supprimer_sources=False)
        assert os.path.isfile(a)

    def test_fichier_ecrit_meme_sans_anomalie(self, tmp_path) -> None:
        """La structuration rend toujours un verdict : c'est l'information attendue."""
        import os

        a = self._ecrire_rapport(tmp_path, "j_controle_e0015.json", "E0015_GEOMETRIE", [])
        resultat = agreger_rapports_structuration([a], str(tmp_path / "j.gml"), str(tmp_path))
        assert os.path.isfile(resultat["sortie"])
        with open(resultat["sortie"], encoding="utf-8") as fichier:
            assert json.load(fichier)["conformite"] == "CONFORME"

    def test_ventilation_par_criticite(self, tmp_path) -> None:
        a = self._ecrire_rapport(tmp_path, "j_controle_e0015.json", "E0015_GEOMETRIE", [_ERREUR_GEOMETRIE])
        b = self._ecrire_rapport(tmp_path, "j_controle_e0013.json", "E0013_ENTETE", [_ERREUR_ENTETE])
        chemin = agreger_rapports_structuration([a, b], str(tmp_path / "j.gml"), str(tmp_path))["sortie"]
        with open(chemin, encoding="utf-8") as fichier:
            rapport = json.load(fichier)
        assert rapport["anomalies_par_criticite"] == {"forte": 1, "moyenne": 1}
        assert rapport["nombre_anomalies_bloquantes"] == 1

    def test_entete_reportee(self, tmp_path) -> None:
        a = self._ecrire_rapport(tmp_path, "j_controle_e0015.json", "E0015_GEOMETRIE", [])
        chemin = agreger_rapports_structuration(
            [a], str(tmp_path / "j.gml"), str(tmp_path), entete={"version_controlee": "1.0"}
        )["sortie"]
        with open(chemin, encoding="utf-8") as fichier:
            assert json.load(fichier)["version_controlee"] == "1.0"

    def test_chemins_none_ignores(self, tmp_path) -> None:
        a = self._ecrire_rapport(tmp_path, "j_controle_e0015.json", "E0015_GEOMETRIE", [_ERREUR_GEOMETRIE])
        resultat = agreger_rapports_structuration([None, a], str(tmp_path / "j.gml"), str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_rapport_illisible_n_interrompt_pas(self, tmp_path) -> None:
        casse = str(tmp_path / "j_controle_casse.json")
        with open(casse, "w", encoding="utf-8") as fichier:
            fichier.write("{ pas du json")
        bon = self._ecrire_rapport(tmp_path, "j_controle_e0015.json", "E0015_GEOMETRIE", [_ERREUR_GEOMETRIE])
        resultat = agreger_rapports_structuration([casse, bon], str(tmp_path / "j.gml"), str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_nom_du_fichier(self) -> None:
        assert nom_fichier_sortie("/jeu/RAC-001.gml") == "RAC-001_controle_structuration.json"


class TestCoherenceAvecLesFamillesGeoJson:
    """La nomenclature redéclarée ici doit rester celle du paquet parent.

    `xsd_structuration/` ne dépend pas de `fonctions_communes` — même parti que
    `priorites_structuration` pour l'échelle de priorités. La duplication est
    donc assumée, mais elle doit être surveillée : c'est l'objet de ce test.
    """

    def test_memes_champs_dans_le_meme_ordre(self) -> None:
        from recostar.controle.fonctions_communes.sortie_famille import CHAMPS_SORTIE as CHAMPS_PARENT

        assert CHAMPS_SORTIE == CHAMPS_PARENT

    def test_meme_cle_de_famille_que_le_registre(self) -> None:
        """La clé doit être celle que `familles_controle` déclare."""
        from recostar.controle.familles_controle import FAMILLES

        assert FAMILLE in {famille.cle for famille in FAMILLES}
