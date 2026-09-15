"""
Tests du moteur de rattachement des boites a leur materiel, et de ses controles.

Couvre :
  - le filtre de perimetre : TypeJonction et Statut
  - le decompte des materiels distincts, forme fragmentee et doublons compris
  - le classement selon le nombre de materiels, exclusif et exhaustif
  - la repartition des anomalies entre E-7100 et E-7101
  - l'absence de GML, seul cas ou le controle est sans objet
  - l'execution CLI complete
"""

import json
from collections import Counter
from typing import Any

from recostar.controle.conteneur.detection_rattachement_materiel import (
    TYPE_MATERIELS_MULTIPLES,
    TYPE_SANS_MATERIEL,
    classifier_boite,
    compter_materiels_par_ouvrage,
    construire_geojson_ecarts,
    detecter_anomalies,
    est_boite_a_controler,
    lire_boites,
)
from recostar.controle.conteneur.e7100 import FICHIER_SORTIE, PROFIL_ECARTS, executer_controle_cli
from recostar.controle.conteneur.e7101 import FICHIER_SORTIE as FICHIER_SORTIE_7101
from recostar.controle.conteneur.e7101 import PROFIL_ECARTS as PROFIL_7101
from recostar.controle.conteneur.e7101 import executer_controle_cli as executer_7101
from recostar.controle.fonctions_communes.geojson import PRIORITE_FORTE
from recostar.controle.fonctions_communes.lecture_gml import charger_racine
from recostar.controle.fonctions_communes.resultats import CLE_SANS_OBJET

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_ENTETE_GML: str = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2"'
    ' xmlns:RecoStaR="http://StaR-Elec.com"'
    ' xmlns:xlink="http://www.w3.org/1999/xlink">'
)

_MEMBRE_JONCTION: str = """  <gml:featureMember>
    <RecoStaR:RPD_Jonction_Reco gml:id="{fid}">
      <RecoStaR:DomaineTension>HTA</RecoStaR:DomaineTension>
      <RecoStaR:TypeJonction>{type_jonction}</RecoStaR:TypeJonction>
      <RecoStaR:Statut>{statut}</RecoStaR:Statut>
      <RecoStaR:Geometrie>
        <gml:Point srsDimension="3"><gml:pos>10.0 20.0 5.0</gml:pos></gml:Point>
      </RecoStaR:Geometrie>
    </RecoStaR:RPD_Jonction_Reco>
  </gml:featureMember>"""

_MEMBRE_RELATION: str = """  <gml:featureMember>
    <RecoStaR:Ouvrage_Materiel>
      <RecoStaR:ouvrage xlink:href="{ouvrage}"/>
      <RecoStaR:materiel xlink:href="{materiel}"/>
    </RecoStaR:Ouvrage_Materiel>
  </gml:featureMember>"""


def _jonction(fid: str = "j1", type_jonction: str = "Jonction", statut: str = "UnderCommissionning") -> str:
    return _MEMBRE_JONCTION.format(fid=fid, type_jonction=type_jonction, statut=statut)


def _relation(ouvrage: str = "j1", materiel: str = "m1") -> str:
    return _MEMBRE_RELATION.format(ouvrage=ouvrage, materiel=materiel)


def _ecrire_gml(tmp_path: Any, membres: list[str], nom: str = "recolement.gml") -> Any:
    chemin = tmp_path / nom
    chemin.write_text(f"{_ENTETE_GML}\n" + "\n".join(membres) + "\n</gml:FeatureCollection>", encoding="utf-8")
    return chemin


def _racine(tmp_path: Any, membres: list[str]) -> Any:
    return charger_racine(_ecrire_gml(tmp_path, membres))


# --------------------------------------------------------------------------- #
# Perimetre
# --------------------------------------------------------------------------- #


class TestPerimetre:
    """Seules les boites en service sont controlees."""

    def test_jonction_retenue(self, tmp_path: Any) -> None:
        assert len(lire_boites(_racine(tmp_path, [_jonction(type_jonction="Jonction")]))) == 1

    def test_derivation_retenue(self, tmp_path: Any) -> None:
        assert len(lire_boites(_racine(tmp_path, [_jonction(type_jonction="Derivation")]))) == 1

    def test_extremite_reseau_ecartee(self, tmp_path: Any) -> None:
        """Une extremite de reseau n'abrite legitimement aucun materiel."""
        assert lire_boites(_racine(tmp_path, [_jonction(type_jonction="ExtremiteReseau")])) == []

    def test_remontee_aero_souterraine_ecartee(self, tmp_path: Any) -> None:
        assert lire_boites(_racine(tmp_path, [_jonction(type_jonction="RemonteeAeroSouterraine")])) == []

    def test_statut_hors_perimetre_ecarte(self, tmp_path: Any) -> None:
        assert lire_boites(_racine(tmp_path, [_jonction(statut="Functional")])) == []

    def test_predicat_sur_element(self, tmp_path: Any) -> None:
        from recostar.controle.fonctions_communes.lecture_gml import parcourir_objets

        racine = _racine(tmp_path, [_jonction()])
        element = next(parcourir_objets(racine, frozenset({"RPD_Jonction_Reco"})))
        assert est_boite_a_controler(element) is True

    def test_geometrie_lue(self, tmp_path: Any) -> None:
        boite = lire_boites(_racine(tmp_path, [_jonction()]))[0]
        assert boite["geometrie"] == {"type": "Point", "coordinates": [10.0, 20.0, 5.0]}
        assert boite["id_jonction"] == "j1"


# --------------------------------------------------------------------------- #
# Decompte des relations
# --------------------------------------------------------------------------- #


class TestCompterMateriels:
    """Le decompte que la conversion perd, lu directement dans le GML."""

    def test_une_relation(self, tmp_path: Any) -> None:
        assert compter_materiels_par_ouvrage(_racine(tmp_path, [_relation()])) == Counter({"j1": 1})

    def test_plusieurs_relations_cumulees(self, tmp_path: Any) -> None:
        """Le convertisseur ecraserait la premiere ; le GML les porte toutes."""
        membres = [_relation(materiel="m1"), _relation(materiel="m2"), _relation(materiel="m3")]
        assert compter_materiels_par_ouvrage(_racine(tmp_path, membres))["j1"] == 3

    def test_forme_fragmentee_resolue(self, tmp_path: Any) -> None:
        """Le GML admet « #idXXXX » : le fragment designe l'objet du document."""
        decompte = compter_materiels_par_ouvrage(_racine(tmp_path, [_relation(ouvrage="#j1", materiel="#m1")]))
        assert decompte == Counter({"j1": 1})

    def test_doublon_de_jointure_compte_une_fois(self, tmp_path: Any) -> None:
        """Deux lignes identiques decrivent un rattachement, non deux.

        Les compter separement ferait sortir en E-7101 une boite qui n'a qu'un
        materiel : le defaut est alors un doublon de table de jointure, code
        E-0012 du verificateur.
        """
        membres = [_relation(materiel="m1"), _relation(materiel="m1")]
        assert compter_materiels_par_ouvrage(_racine(tmp_path, membres)) == Counter({"j1": 1})

    def test_relation_incomplete_ignoree(self, tmp_path: Any) -> None:
        incomplete = """  <gml:featureMember>
    <RecoStaR:Ouvrage_Materiel><RecoStaR:ouvrage xlink:href="j1"/></RecoStaR:Ouvrage_Materiel>
  </gml:featureMember>"""
        assert compter_materiels_par_ouvrage(_racine(tmp_path, [incomplete])) == Counter()

    def test_ouvrages_distincts(self, tmp_path: Any) -> None:
        """Chaque ouvrage porte son propre decompte de materiels distincts."""
        membres = [
            _relation(ouvrage="j1", materiel="m1"),
            _relation(ouvrage="j2", materiel="m2"),
            _relation(ouvrage="j2", materiel="m3"),
        ]
        decompte = compter_materiels_par_ouvrage(_racine(tmp_path, membres))
        assert decompte == Counter({"j1": 1, "j2": 2})


# --------------------------------------------------------------------------- #
# Regle metier
# --------------------------------------------------------------------------- #


class TestClassifierBoite:
    """Les deux regles sont exclusives et couvrent tous les cas."""

    def test_aucun_materiel(self) -> None:
        assert classifier_boite(0) == TYPE_SANS_MATERIEL

    def test_un_materiel_conforme(self) -> None:
        assert classifier_boite(1) is None

    def test_deux_materiels(self) -> None:
        assert classifier_boite(2) == TYPE_MATERIELS_MULTIPLES

    def test_beaucoup_de_materiels(self) -> None:
        assert classifier_boite(10) == TYPE_MATERIELS_MULTIPLES

    def test_exclusivite(self) -> None:
        """Aucun decompte ne peut relever des deux codes."""
        for nombre in range(0, 6):
            resultat = classifier_boite(nombre)
            assert resultat in (None, TYPE_SANS_MATERIEL, TYPE_MATERIELS_MULTIPLES)


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    @staticmethod
    def _boite(identifiant: str = "j1") -> dict[str, Any]:
        return {"id_jonction": identifiant, "type_jonction": "Jonction", "geometrie": None}

    def test_boite_sans_materiel(self) -> None:
        anomalies = detecter_anomalies([self._boite()], Counter())
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_SANS_MATERIEL]
        assert anomalies[0]["nombre_materiels"] == 0

    def test_boite_conforme(self) -> None:
        assert detecter_anomalies([self._boite()], Counter({"j1": 1})) == []

    def test_boite_multiple(self) -> None:
        anomalies = detecter_anomalies([self._boite()], Counter({"j1": 3}))
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_MATERIELS_MULTIPLES]
        assert anomalies[0]["nombre_materiels"] == 3

    def test_une_anomalie_par_boite(self) -> None:
        """Trois materiels en trop ne font qu'une anomalie : c'est le lien a corriger."""
        assert len(detecter_anomalies([self._boite()], Counter({"j1": 4}))) == 1

    def test_boites_independantes(self) -> None:
        boites = [self._boite("j1"), self._boite("j2"), self._boite("j3")]
        anomalies = detecter_anomalies(boites, Counter({"j1": 1, "j2": 2}))
        assert sorted(a["id_jonction"] for a in anomalies) == ["j2", "j3"]

    def test_aucune_boite(self) -> None:
        assert detecter_anomalies([], Counter({"j1": 5})) == []


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    @staticmethod
    def _anomalie(type_anomalie: str = TYPE_SANS_MATERIEL, nombre: int = 0) -> dict[str, Any]:
        return {
            "type_anomalie": type_anomalie,
            "id_jonction": "j1",
            "type_jonction": "Jonction",
            "nombre_materiels": nombre,
            "geometrie": {"type": "Point", "coordinates": [10.0, 20.0, 5.0]},
        }

    def test_proprietes_du_socle_7100(self) -> None:
        proprietes = construire_geojson_ecarts([self._anomalie()], PROFIL_ECARTS)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-7100"
        assert proprietes["priorite"] == PRIORITE_FORTE
        assert proprietes["nombre_materiels"] == 0

    def test_proprietes_du_socle_7101(self) -> None:
        anomalie = self._anomalie(TYPE_MATERIELS_MULTIPLES, 3)
        proprietes = construire_geojson_ecarts([anomalie], PROFIL_7101)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-7101"
        assert proprietes["nombre_materiels"] == 3

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([], PROFIL_ECARTS)["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI et repartition entre controles
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli, pour les deux codes."""

    def test_sans_gml_sans_objet(self, tmp_path: Any) -> None:
        """Le decompte ne se lit que dans le GML : sans lui, rien a conclure."""
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat[CLE_SANS_OBJET] is True
        assert resultat["nombre_anomalies"] == 0

    def test_boite_sans_materiel(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_jonction("j1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_SANS_MATERIEL: 1}
        assert resultat["nombre_boites_controlees"] == 1

    def test_boite_conforme(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_jonction("j1"), _relation("j1", "m1")])
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0
        assert executer_7101(str(tmp_path))["nombre_anomalies"] == 0

    def test_doublon_de_jointure_reste_conforme(self, tmp_path: Any) -> None:
        """Un meme materiel declare deux fois n'est pas « plusieurs materiels »."""
        _ecrire_gml(tmp_path, [_jonction("j1"), _relation("j1", "m1"), _relation("j1", "m1")])
        assert executer_7101(str(tmp_path))["nombre_anomalies"] == 0
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_boite_multiple_ne_sort_que_d_e7101(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_jonction("j1"), _relation("j1", "m1"), _relation("j1", "m2")])
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0
        assert executer_7101(str(tmp_path))["anomalies_par_type"] == {TYPE_MATERIELS_MULTIPLES: 1}

    def test_boite_orpheline_ne_sort_que_d_e7100(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_jonction("j1")])
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 1
        assert executer_7101(str(tmp_path))["nombre_anomalies"] == 0

    def test_types_retenus_disjoints(self) -> None:
        from recostar.controle.conteneur.e7100 import TYPES_RETENUS as TYPES_7100
        from recostar.controle.conteneur.e7101 import TYPES_RETENUS as TYPES_7101

        assert not TYPES_7100 & TYPES_7101

    def test_fichiers_de_sortie_distincts(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_jonction("j1"), _jonction("j2"), _relation("j2", "m1"), _relation("j2", "m2")])
        assert executer_controle_cli(str(tmp_path))["sortie"].endswith(FICHIER_SORTIE)
        assert executer_7101(str(tmp_path))["sortie"].endswith(FICHIER_SORTIE_7101)

    def test_chemin_gml_explicite(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_jonction("j1")], nom="a.gml")
        _ecrire_gml(tmp_path, [_jonction("j2"), _relation("j2", "m1")], nom="b.gml")
        assert executer_controle_cli(str(tmp_path), chemin_gml=chemin)["nombre_anomalies"] == 1

    def test_fichier_ecarts_ecrit(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_jonction("j1")])
        chemin = executer_controle_cli(str(tmp_path))["sortie"]
        assert chemin is not None
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-7100"
        assert proprietes["id_jonction"] == "j1"

    def test_aucun_fichier_si_conforme(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_jonction("j1"), _relation("j1", "m1")])
        assert executer_controle_cli(str(tmp_path))["sortie"] is None
