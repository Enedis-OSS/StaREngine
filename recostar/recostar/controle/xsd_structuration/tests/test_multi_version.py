"""
Tests croisés multi-version (V1.0 ↔ V1.1).

Ces tests sont le filet de sécurité central de l'évolution multi-version : ils
prouvent qu'un même fichier GML est jugé différemment selon le profil appliqué,
et donc que les profils ne sont pas interchangeables. Ils couvrent les deltas
les plus structurants :

- E110 : champs câble requis en V1.0, optionnels en V1.1 ;
- E111 : règle R001 active en V1.1, absente en V1.0 ;
- E114 : SRS ajoutés en V1.1, refusés en V1.0 ;
- résolution CLI : détection automatique vs version imposée.
"""

import versions
from cli_version import resoudre_profil_cli
from controle_e110 import AnalyseurGML as AnalyseurOrdre
from controle_e111 import AnalyseurGML as AnalyseurMetier
from controle_e114 import AnalyseurValeurs
from utils_gml import creer_feature_member, creer_feature_member_avec_valeurs

PROFIL_V1_0 = versions.resoudre_profil("1.0")
PROFIL_V1_1 = versions.resoudre_profil("1.1")

# URL de schéma V1.0 utilisée pour les tests de détection.
_SCHEMA_LOCATION_V1_0 = (
    "http://StaR-Elec.com https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/"
    "RecoStar-v1.0/RecoStaR/SchemaStarElecRecoStar.xsd"
)


# ---------------------------------------------------------------------------
# E110 : un champ câble requis en V1.0 devient optionnel en V1.1
# ---------------------------------------------------------------------------


def test_e110_champs_cable_requis_seulement_en_v1_0(chemin_gml_tmp):
    """Un câble sans Isolant/Materiau/Section/NombreConducteurs : erreurs en
    V1.0 (champs requis par le XSD), aucune en V1.1 (devenus optionnels)."""
    membre = creer_feature_member(
        "RPD_CableElectrique_Reco",
        "cable_001",
        ["reseau", "DomaineTension", "FonctionCable", "Statut"],
    )
    chemin = chemin_gml_tmp([membre])

    manquants_v0 = {
        e.element_attendu
        for e in AnalyseurOrdre(chemin, PROFIL_V1_0).analyser()
        if e.type_erreur == "ELEMENT_REQUIS_MANQUANT"
    }
    erreurs_v1 = AnalyseurOrdre(chemin, PROFIL_V1_1).analyser()

    assert {"Isolant", "Materiau", "Section", "NombreConducteurs"} <= manquants_v0
    assert erreurs_v1 == []


def test_e110_commentaire_inattendu_en_v1_0(chemin_gml_tmp):
    """L'élément Commentaire (ajouté en V1.1) est inattendu en V1.0."""
    membre = creer_feature_member(
        "RPD_Aerien_Reco",
        "aerien_001",
        ["reseau", "Commentaire", "Geometrie", "ModePose", "PrecisionXY", "PrecisionZ"],
    )
    chemin = chemin_gml_tmp([membre])

    types_v0 = {e.type_erreur for e in AnalyseurOrdre(chemin, PROFIL_V1_0).analyser()}
    assert "ELEMENT_INATTENDU" in types_v0
    assert AnalyseurOrdre(chemin, PROFIL_V1_1).analyser() == []


# ---------------------------------------------------------------------------
# E111 : la règle R001 n'existe qu'en V1.1
# ---------------------------------------------------------------------------


def test_e111_r001_active_en_v1_1_absente_en_v1_0(chemin_gml_tmp):
    """Câble « en attente » sans champs métier : R001 déclenchée en V1.1, pas en V1.0."""
    membre = creer_feature_member_avec_valeurs(
        "RPD_CableElectrique_Reco",
        "cable_attente_001",
        [
            ("reseau", None),
            ("DomaineTension", "HTA"),
            ("FonctionCable", "DistributionEnergie"),
            ("Statut", "UnderCommissionning"),
        ],
    )
    chemin = chemin_gml_tmp([membre])

    regles_v1 = {e.regle for e in AnalyseurMetier(chemin, PROFIL_V1_1).analyser()}
    regles_v0 = {e.regle for e in AnalyseurMetier(chemin, PROFIL_V1_0).analyser()}

    assert "R001_CABLE_ELEC_EN_ATTENTE" in regles_v1
    assert "R001_CABLE_ELEC_EN_ATTENTE" not in regles_v0


# ---------------------------------------------------------------------------
# E114 : un SRS ajouté en V1.1 est refusé en V1.0
# ---------------------------------------------------------------------------


def test_e114_srs_v1_1_refuse_en_v1_0(chemin_gml_tmp):
    """EPSG:9842 (ajouté en V1.1) est conforme en V1.1, hors énumération en V1.0."""
    membre = creer_feature_member_avec_valeurs("Metadata", "metadata_001", [("SRS", "EPSG:9842")])
    chemin = chemin_gml_tmp([membre])

    erreurs_v0 = AnalyseurValeurs(chemin, PROFIL_V1_0).analyser()
    erreurs_v1 = AnalyseurValeurs(chemin, PROFIL_V1_1).analyser()

    assert any(e.champ == "SRS" for e in erreurs_v0)
    assert all(e.champ != "SRS" for e in erreurs_v1)


# ---------------------------------------------------------------------------
# Résolution CLI : détection automatique et override explicite
# ---------------------------------------------------------------------------


def test_resolution_auto_detecte_la_version(chemin_gml_entete_tmp):
    """En mode auto, le profil est déduit du schemaLocation du fichier."""
    chemin = chemin_gml_entete_tmp([], schema_location_override=_SCHEMA_LOCATION_V1_0)
    assert resoudre_profil_cli(chemin, "auto").code == "1.0"


def test_resolution_version_explicite_prioritaire(chemin_gml_entete_tmp):
    """Une version imposée prime sur ce que contient le fichier."""
    chemin = chemin_gml_entete_tmp([], schema_location_override=_SCHEMA_LOCATION_V1_0)
    assert resoudre_profil_cli(chemin, "1.1").code == "1.1"


def test_resolution_auto_repli_si_indetectable(chemin_gml_entete_tmp):
    """Sans schemaLocation, le mode auto se replie sur la version par défaut."""
    chemin = chemin_gml_entete_tmp([], inclure_schema_location=False)
    assert resoudre_profil_cli(chemin, "auto").code == versions.VERSION_DEFAUT


# ---------------------------------------------------------------------------
# E114 : le champ portant le type de levé est renommé entre versions
# ---------------------------------------------------------------------------


def test_e114_type_leve_controle_seulement_en_v1_0(chemin_gml_tmp):
    """`TypeLeve` (nom V1.0) est contrôlé en V1.0 ; ce champ n'existe plus en V1.1."""
    membre = creer_feature_member_avec_valeurs(
        "RPD_PointLeveOuvrageReseau_Reco",
        "point_leve_001",
        [("TypeLeve", "ValeurInvalide")],
    )
    chemin = chemin_gml_tmp([membre])

    champs_v0 = {e.champ for e in AnalyseurValeurs(chemin, PROFIL_V1_0).analyser()}
    champs_v1 = {e.champ for e in AnalyseurValeurs(chemin, PROFIL_V1_1).analyser()}

    assert "TypeLeve" in champs_v0
    assert "TypeLeve" not in champs_v1


def test_e114_type_leve_valide_accepte_en_v1_0(chemin_gml_tmp):
    """Une valeur de l'énumération LeveType reste acceptée en V1.0."""
    membre = creer_feature_member_avec_valeurs(
        "RPD_PointLeveOuvrageReseau_Reco",
        "point_leve_002",
        [("TypeLeve", "ChargeGeneratrice")],
    )
    chemin = chemin_gml_tmp([membre])
    assert AnalyseurValeurs(chemin, PROFIL_V1_0).analyser() == []


# ---------------------------------------------------------------------------
# E110 : le type télécom n'existe qu'en V1.1
# ---------------------------------------------------------------------------


def test_e110_type_telecom_absent_du_profil_v1_0():
    """RPD_CableTelecommunication_Reco est connu de la V1.1 seulement."""
    assert "RPD_CableTelecommunication_Reco" in PROFIL_V1_1.noms_rpd
    assert "RPD_CableTelecommunication_Reco" not in PROFIL_V1_0.noms_rpd


def test_e110_geometrie_supplementaire_renommee_entre_versions(chemin_gml_tmp):
    """Ligne2.5D/Surface2.5D (V1.0) deviennent Ligne3D/Surface3D (V1.1)."""
    membre = creer_feature_member(
        "RPD_GeometrieSupplementaire_Reco",
        "geom_sup_001",
        ["Ligne2.5D", "PrecisionXY", "PrecisionZ"],
    )
    chemin = chemin_gml_tmp([membre])

    assert AnalyseurOrdre(chemin, PROFIL_V1_0).analyser() == []
    types_v1 = {e.type_erreur for e in AnalyseurOrdre(chemin, PROFIL_V1_1).analyser()}
    assert "ELEMENT_INATTENDU" in types_v1
