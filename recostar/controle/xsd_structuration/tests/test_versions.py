"""
Tests du package `versions` : contrat ProfilVersion, registre de résolution
et compatibilité des moteurs paramétrés.

Ces tests verrouillent l'invariant central de l'étape « socle » : le profil
V1.1 assemblé depuis les modules existants doit produire exactement le même
comportement que les globales historiques (refactorisation non destructive).
"""

import dataclasses

import pytest
import versions
from regles_entete import SEQUENCES_ENTETE
from regles_metier import REGLES_PAR_TYPE, evaluer_regles
from regles_valeurs import construire_index, evaluer_valeur
from sequenceur_xsd import NOMS_RPD, SEQUENCES_RPD
from versions.profil import ProfilVersion
from versions.v1_0 import PROFIL_V1_0
from versions.v1_1 import PROFIL_V1_1

# ---------------------------------------------------------------------------
# Registre de résolution
# ---------------------------------------------------------------------------


def test_resoudre_profil_par_defaut_retourne_v1_1():
    """Sans argument, la version par défaut (historique) est la 1.1."""
    profil = versions.resoudre_profil()
    assert profil.code == "1.1"
    assert profil is PROFIL_V1_1


def test_resoudre_profil_code_explicite():
    """Un code de version connu retourne le profil correspondant."""
    assert versions.resoudre_profil("1.1") is PROFIL_V1_1
    assert versions.resoudre_profil("1.0") is PROFIL_V1_0


def test_deux_versions_supportees():
    """Le registre expose bien les deux versions 1.0 et 1.1."""
    assert set(versions.VERSIONS_SUPPORTEES) == {"1.0", "1.1"}


def test_resoudre_profil_code_inconnu_leve_valueerror():
    """Un code inconnu lève ValueError en listant les versions supportées."""
    with pytest.raises(ValueError) as info:
        versions.resoudre_profil("9.9")
    message = str(info.value)
    assert "9.9" in message
    assert "1.1" in message


def test_version_defaut_est_supportee():
    """La version par défaut figure bien dans les versions supportées."""
    assert versions.VERSION_DEFAUT in versions.VERSIONS_SUPPORTEES


# ---------------------------------------------------------------------------
# Cohérence du profil V1.1 avec les catalogues existants
# ---------------------------------------------------------------------------


def test_profil_est_immuable():
    """Le ProfilVersion est gelé : toute mutation est interdite."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        PROFIL_V1_1.code = "1.0"  # type: ignore[misc]


def test_profil_reutilise_les_tables_existantes():
    """Le profil pointe vers les catalogues du module, sans recopie."""
    assert PROFIL_V1_1.sequences_rpd is SEQUENCES_RPD
    assert PROFIL_V1_1.noms_rpd is NOMS_RPD
    assert PROFIL_V1_1.regles_par_type is REGLES_PAR_TYPE


def test_profil_index_valeurs_coherent_avec_catalogue():
    """L'index de valeurs du profil couvre les mêmes clés que le catalogue."""
    assert PROFIL_V1_1.index_regles_valeurs.keys() == construire_index().keys()


def test_profil_xsd_existe():
    """Le chemin XSD porté par le profil pointe vers un fichier réel."""
    assert PROFIL_V1_1.chemin_xsd.is_file()


def test_profil_fragment_url_cible_v1_1():
    """Le fragment d'URL identifie bien la version 1.1."""
    assert "v1.1" in PROFIL_V1_1.fragment_url_xsd


# ---------------------------------------------------------------------------
# Compatibilité des moteurs paramétrés (mêmes résultats qu'en défaut)
# ---------------------------------------------------------------------------


def test_evaluer_regles_avec_table_du_profil_identique_au_defaut():
    """Passer la table du profil donne le même résultat que le défaut."""
    valeurs = {
        "DomaineTension": "HTA",
        "Statut": "UnderCommissionning",
        "Materiau": "Alu",
    }
    attendu = evaluer_regles("RPD_CableElectrique_Reco", "c1", valeurs)
    obtenu = evaluer_regles(
        "RPD_CableElectrique_Reco",
        "c1",
        valeurs,
        regles_par_type=PROFIL_V1_1.regles_par_type,
    )
    # Comparaison sur les champs sérialisés (ErreurMetier n'est pas comparable).
    assert [e.vers_dict() for e in obtenu] == [e.vers_dict() for e in attendu]


def test_evaluer_valeur_avec_index_du_profil_identique_au_defaut():
    """Passer l'index du profil donne le même résultat que le défaut."""
    attendu = evaluer_valeur("RPD_CableElectrique_Reco", "DomaineTension", "ZZZ", "c1")
    obtenu = evaluer_valeur(
        "RPD_CableElectrique_Reco",
        "DomaineTension",
        "ZZZ",
        "c1",
        index=PROFIL_V1_1.index_regles_valeurs,
    )
    assert attendu is not None and obtenu is not None
    assert obtenu.vers_dict() == attendu.vers_dict()


def test_profil_version_est_bien_typee():
    """Le registre ne contient que des instances de ProfilVersion."""
    assert all(isinstance(versions.resoudre_profil(code), ProfilVersion) for code in versions.VERSIONS_SUPPORTEES)


# ---------------------------------------------------------------------------
# Profil V1.0 : deltas par rapport à la V1.1
# ---------------------------------------------------------------------------


def test_v1_0_code():
    """Le profil V1.0 porte le bon code de version."""
    assert PROFIL_V1_0.code == "1.0"


def test_v1_0_sans_type_telecom():
    """Le type télécom (nouveau en V1.1) est absent du périmètre V1.0."""
    assert "RPD_CableTelecommunication_Reco" not in PROFIL_V1_0.noms_rpd
    assert "RPD_CableTelecommunication_Reco" in PROFIL_V1_1.noms_rpd


def test_v1_0_regle_r001_retiree():
    """R001 (concept V1.1) n'est pas appliquée en V1.0, R002/R003 le sont."""
    ids_v0 = {r.identifiant for rs in PROFIL_V1_0.regles_par_type.values() for r in rs}
    assert "R001_CABLE_ELEC_EN_ATTENTE" not in ids_v0
    assert "R002_CABLE_ELEC_BT" in ids_v0
    assert "R003_SUPPORT_POTEAU_EN_ATTENTE" in ids_v0


def test_v1_0_srs_sous_ensemble_de_v1_1():
    """L'énumération SRS de la V1.0 est plus restreinte que celle de la V1.1."""
    assert PROFIL_V1_0.srs_autorises < PROFIL_V1_1.srs_autorises


def test_v1_0_geometrie_supplementaire_en_2_5d():
    """La V1.0 attend Ligne2.5D/Surface2.5D (renommés 3D en V1.1)."""
    noms = {s.nom for s in PROFIL_V1_0.sequences_rpd["RPD_GeometrieSupplementaire_Reco"]}
    assert "Ligne2.5D" in noms
    assert "Ligne3D" not in noms


def test_v1_0_entete_reutilise_v1_1():
    """L'en-tête (Metadata/ReseauUtilite) est partagé entre versions."""
    assert PROFIL_V1_0.sequences_entete is SEQUENCES_ENTETE


def test_v1_0_xsd_existe():
    """Le profil V1.0 pointe vers son propre XSD, présent sur disque."""
    assert PROFIL_V1_0.chemin_xsd.is_file()
    assert PROFIL_V1_0.chemin_xsd != PROFIL_V1_1.chemin_xsd
