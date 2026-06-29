#!/usr/bin/env python3
"""
Profil de version RecoStaR V1.1.

Ce module ne redéfinit aucune table : il assemble le `ProfilVersion` 1.1 à
partir des catalogues déjà présents dans les modules de support
(`sequenceur_xsd`, `regles_metier`, `regles_valeurs`, `regles_entete`). La
version 1.1 est la version historiquement implémentée ; ce profil ne fait donc
que rendre explicite et réutilisable ce qui existait sous forme de globales de
module.
"""

from pathlib import Path

from regles_entete import (
    CARDINALITES_ENTETE,
    FRAGMENT_URL_XSD_V1_1,
    NAMESPACES_ATTENDUS,
    SEQUENCES_ENTETE,
    SRS_AUTORISES,
    TYPES_ENTETE,
)
from regles_metier import REGLES_PAR_TYPE, TYPES_RPD_AVEC_REGLES
from regles_valeurs import TYPES_AVEC_REGLES, construire_index
from sequenceur_xsd import NOMS_RPD, SEQUENCES_RPD

from versions.profil import ProfilVersion

# Le profil porte le chemin du XSD officiel de sa version (consommé par E112).
# Résolu relativement à ce fichier : versions/ -> xsd_structuration/ ->
# controle/ -> recostar/, puis conversion/conversion_V1_1/xsd/.
_RACINE_RECOSTAR: Path = Path(__file__).resolve().parents[3]
CHEMIN_XSD_V1_1: Path = _RACINE_RECOSTAR / "conversion" / "conversion_V1_1" / "xsd" / "SchemaStarElecRecoStar.xsd"


PROFIL_V1_1: ProfilVersion = ProfilVersion(
    code="1.1",
    sequences_rpd=SEQUENCES_RPD,
    noms_rpd=NOMS_RPD,
    regles_par_type=REGLES_PAR_TYPE,
    types_rpd_avec_regles=TYPES_RPD_AVEC_REGLES,
    # Reconstruit l'index à partir du catalogue V1.1 via la fabrique partagée :
    # aucune copie de la table d'indexation n'est faite ici.
    index_regles_valeurs=construire_index(),
    types_avec_regles=TYPES_AVEC_REGLES,
    sequences_entete=SEQUENCES_ENTETE,
    types_entete=TYPES_ENTETE,
    cardinalites_entete=CARDINALITES_ENTETE,
    srs_autorises=SRS_AUTORISES,
    namespaces_attendus=NAMESPACES_ATTENDUS,
    fragment_url_xsd=FRAGMENT_URL_XSD_V1_1,
    chemin_xsd=CHEMIN_XSD_V1_1,
)
