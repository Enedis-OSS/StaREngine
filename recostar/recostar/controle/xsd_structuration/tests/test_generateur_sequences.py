"""
Tests du générateur de séquences XSD.

Le test pivot (`test_generation_v1_1_identique_a_la_table_manuelle`) verrouille
la fidélité du générateur : tant qu'il reproduit exactement la table V1.1
écrite à la main, on peut lui faire confiance pour dériver la table V1.0.
"""

from generateur_sequences import generer_enumeration, generer_sequences
from regles_entete import SRS_AUTORISES
from sequenceur_xsd import SEQUENCES_RPD
from versions.v1_0 import CHEMIN_XSD_V1_0
from versions.v1_1 import CHEMIN_XSD_V1_1

# ---------------------------------------------------------------------------
# Fidélité : régénération de la V1.1
# ---------------------------------------------------------------------------


def test_generation_v1_1_identique_a_la_table_manuelle():
    """Le générateur reproduit à l'identique la table V1.1 codée à la main."""
    assert generer_sequences(CHEMIN_XSD_V1_1) == SEQUENCES_RPD


def test_generation_porte_sur_tous_les_types_rpd():
    """Tous les types RPD de la table manuelle sont retrouvés par génération."""
    genere = generer_sequences(CHEMIN_XSD_V1_1)
    assert set(genere) == set(SEQUENCES_RPD)


# ---------------------------------------------------------------------------
# Dérivation de la V1.0 (deltas structurels attendus)
# ---------------------------------------------------------------------------


def test_v1_0_sans_type_telecom():
    """Le type télécom, ajouté en V1.1, est absent de la V1.0."""
    genere = generer_sequences(CHEMIN_XSD_V1_0)
    assert "RPD_CableTelecommunication_Reco" not in genere


def test_v1_0_geometrie_supplementaire_utilise_2_5d():
    """En V1.0, GeometrieSupplementaire porte Ligne2.5D/Surface2.5D (pas 3D)."""
    genere = generer_sequences(CHEMIN_XSD_V1_0)
    noms = {s.nom for s in genere["RPD_GeometrieSupplementaire_Reco"]}
    assert "Ligne2.5D" in noms and "Surface2.5D" in noms
    assert "Ligne3D" not in noms and "Surface3D" not in noms


def test_v1_0_champs_cable_requis():
    """En V1.0, Isolant/Materiau/Section/NombreConducteurs sont requis (min=1)."""
    genere = generer_sequences(CHEMIN_XSD_V1_0)
    par_nom = {s.nom: s for s in genere["RPD_CableElectrique_Reco"]}
    for champ in ("Isolant", "Materiau", "Section", "NombreConducteurs"):
        assert par_nom[champ].min_occurs == 1, champ


def test_occurs_non_borne_traduit_en_moins_un():
    """maxOccurs='unbounded' (ex. 'reseau') est traduit en -1."""
    genere = generer_sequences(CHEMIN_XSD_V1_1)
    reseau = next(s for s in genere["RPD_Aerien_Reco"] if s.nom == "reseau")
    assert reseau.max_occurs == -1
    assert reseau.min_occurs == 1


# ---------------------------------------------------------------------------
# Extraction d'énumération
# ---------------------------------------------------------------------------


def test_enumeration_srs_v1_1_coherente_avec_regles_entete():
    """L'extraction du SRS V1.1 correspond à la constante SRS_AUTORISES."""
    assert generer_enumeration(CHEMIN_XSD_V1_1, "SRSValueType") == SRS_AUTORISES


def test_enumeration_srs_v1_0_incluse_dans_v1_1():
    """Le jeu de SRS de la V1.0 est un sous-ensemble strict de celui de la V1.1."""
    srs_v0 = generer_enumeration(CHEMIN_XSD_V1_0, "SRSValueType")
    srs_v1 = generer_enumeration(CHEMIN_XSD_V1_1, "SRSValueType")
    assert srs_v0 < srs_v1
    assert len(srs_v0) == 15 and len(srs_v1) == 25


def test_enumeration_type_inconnu_retourne_vide():
    """Un type simple inexistant donne un frozenset vide (cas limite)."""
    assert generer_enumeration(CHEMIN_XSD_V1_1, "TypeQuiNexistePas") == frozenset()
