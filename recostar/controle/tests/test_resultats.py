"""
Tests du module de construction des rapports de controle (fonctions_communes.resultats).

Couvre le rapport « sans objet » — celui d'un controle prive de sa couche source
—, sa reconnaissance, et sa traversee de la chaine de synthese jusqu'au statut
de famille. Ce dernier point est le vrai enjeu : c'est la que se jouait la
confusion entre un jeu de donnees partiel et un defaut de conformite.
"""

from typing import Any

from recostar.controle.fonctions_communes.resultats import (
    MOTIF_AUCUN_GEOJSON,
    est_sans_objet,
    motif_couche_absente,
    rapport_sans_objet,
)
from recostar.controle.synthese_controles import (
    STATUT_CONFORME,
    STATUT_INCOMPLET,
    ResultatFamille,
    normaliser_controle,
)

_COUCHE = "RPD_PointLeveOuvrageReseau_Reco.geojson"
_REPERTOIRE = "/jeu/livraison"


class TestMotifCoucheAbsente:
    """Redaction du motif d'un controle prive de sa couche source."""

    def test_cite_la_couche_et_le_repertoire(self) -> None:
        motif = motif_couche_absente(_COUCHE, _REPERTOIRE)
        assert _COUCHE in motif
        assert _REPERTOIRE in motif

    def test_dit_qu_il_n_y_a_rien_a_controler(self) -> None:
        """Le motif doit expliquer l'absence d'anomalie, pas seulement la constater."""
        assert "aucun element a controler" in motif_couche_absente(_COUCHE, _REPERTOIRE)


class TestRapportSansObjet:
    """Forme du rapport retourne par un controle sans element a controler."""

    def test_est_un_succes(self) -> None:
        """Le point central : ce n'est pas un echec."""
        assert rapport_sans_objet("motif")["succes"] is True

    def test_aucune_anomalie(self) -> None:
        rapport = rapport_sans_objet("motif")
        assert rapport["nombre_anomalies"] == 0
        assert rapport["anomalies_par_type"] == {}

    def test_porte_le_marqueur_et_le_motif(self) -> None:
        rapport = rapport_sans_objet(MOTIF_AUCUN_GEOJSON)
        assert rapport["sans_objet"] is True
        assert rapport["motif"] == MOTIF_AUCUN_GEOJSON

    def test_aucun_fichier_de_sortie(self) -> None:
        """Sans ecart a porter, aucun fichier n'est ecrit."""
        assert rapport_sans_objet("motif")["sortie"] is None

    def test_ne_porte_pas_de_cle_erreur(self) -> None:
        """La cle `erreur` signalerait un echec aux consommateurs du rapport."""
        assert "erreur" not in rapport_sans_objet("motif")

    def test_compteurs_du_controle_preserves(self) -> None:
        """Chaque controle conserve la forme de son rapport pour ses appelants."""
        rapport = rapport_sans_objet("motif", nombre_entites_analysees=0, couches_absentes=["a"])
        assert rapport["nombre_entites_analysees"] == 0
        assert rapport["couches_absentes"] == ["a"]

    def test_compteur_homonyme_ecrase_le_defaut(self) -> None:
        """Un controle peut imposer sa propre valeur : `compteurs` est applique en dernier."""
        assert rapport_sans_objet("motif", sortie="/chemin")["sortie"] == "/chemin"


class TestEstSansObjet:
    """Reconnaissance d'un rapport sans objet."""

    def test_vrai_sur_un_rapport_sans_objet(self) -> None:
        assert est_sans_objet(rapport_sans_objet("motif")) is True

    def test_faux_sur_un_rapport_ordinaire(self) -> None:
        assert est_sans_objet({"succes": True, "nombre_anomalies": 3}) is False

    def test_faux_sur_un_echec(self) -> None:
        assert est_sans_objet({"succes": False, "erreur": "Repertoire introuvable"}) is False


class TestTraverseeDeLaSynthese:
    """Le rapport sans objet doit produire un controle conforme, non un echec."""

    def _normalise(self, rapport: dict[str, Any]):
        return normaliser_controle("E-3300", "Doublons spatiaux", rapport)

    def test_controle_en_succes_sans_anomalie(self) -> None:
        resultat = self._normalise(rapport_sans_objet(motif_couche_absente(_COUCHE, _REPERTOIRE)))
        assert resultat.succes is True
        assert resultat.nombre_anomalies == 0
        assert resultat.anomalies_par_priorite == {}

    def test_marqueur_et_motif_propages(self) -> None:
        resultat = self._normalise(rapport_sans_objet(MOTIF_AUCUN_GEOJSON))
        assert resultat.sans_objet is True
        assert resultat.motif == MOTIF_AUCUN_GEOJSON

    def test_controle_ordinaire_non_marque(self) -> None:
        resultat = self._normalise({"succes": True, "nombre_anomalies": 0})
        assert resultat.sans_objet is False
        assert resultat.motif is None

    def test_famille_conforme_et_non_incomplete(self) -> None:
        """Le defaut corrige : une couche absente declassait la famille en « Incomplet »."""
        famille = ResultatFamille(
            cle="altimetrie",
            libelle="Altimétrie",
            controles=(
                self._normalise(rapport_sans_objet(motif_couche_absente(_COUCHE, _REPERTOIRE))),
                self._normalise({"succes": True, "nombre_anomalies": 0}),
            ),
        )
        assert famille.statut == STATUT_CONFORME
        assert famille.controles_en_echec == ()
        assert famille.nombre_anomalies == 0
        assert famille.controles_sans_objet == ("E-3300",)

    def test_un_vrai_echec_declasse_toujours(self) -> None:
        """La correction ne doit pas masquer les echecs qui restent des echecs."""
        famille = ResultatFamille(
            cle="altimetrie",
            libelle="Altimétrie",
            controles=(
                self._normalise(rapport_sans_objet(MOTIF_AUCUN_GEOJSON)),
                self._normalise({"succes": False, "erreur": "Repertoire introuvable"}),
            ),
        )
        assert famille.statut == STATUT_INCOMPLET
        assert famille.controles_en_echec == ("E-3300",)
