#!/usr/bin/env python3
"""
Contrat commun décrivant un profil de version RecoStaR pour les contrôles XSD.

Un `ProfilVersion` agrège l'ensemble des tables de données (séquences,
règles métier, règles de valeurs, en-tête) et des constantes qui varient
d'une version du format RecoStaR à l'autre (V1.0, V1.1). Les moteurs de
contrôle (E0110 à E0114) restent uniques et version-agnostiques : ils reçoivent
ce profil et y lisent les tables à appliquer.

Architecture évolutive : ajouter une version = créer un module `versions/vX_Y`
qui instancie un `ProfilVersion`, puis l'enregistrer dans `versions.__init__`.
Aucun moteur n'est à modifier.
"""

from dataclasses import dataclass
from pathlib import Path

from recostar.controle.xsd_structuration.regles_metier import RegleMetier
from recostar.controle.xsd_structuration.regles_valeurs import RegleValeur
from recostar.controle.xsd_structuration.sequenceur_xsd import SlotSequence


# frozen : profil immuable, partageable sans risque de mutation accidentelle.
# slots : empreinte mémoire réduite et accès attribut plus rapide (un seul
# profil par version est instancié, mais le gain reste cohérent avec le reste
# du code qui utilise systématiquement __slots__).
@dataclass(frozen=True, slots=True)
class ProfilVersion:
    """Regroupe toutes les données propres à une version du format RecoStaR.

    Attributs :
        code                  : Identifiant de version ("1.0", "1.1").
        sequences_rpd         : Séquence XSD attendue par type RPD (E0110).
        noms_rpd              : Ensemble des types RPD connus de la version (E0110).
        regles_par_type       : Index des règles métier par type RPD (E0111).
        types_rpd_avec_regles : Types RPD soumis à au moins une règle (E0111).
        index_regles_valeurs  : Index (type_rpd, champ) → règle de valeur (E0114).
        types_avec_regles     : Types portant au moins une règle de valeur (E0114).
        sequences_entete      : Séquence attendue des objets d'en-tête (E0113).
        types_entete          : Ensemble des objets d'en-tête connus (E0113).
        cardinalites_entete   : Cardinalité (min, max) par objet d'en-tête (E0113).
        srs_autorises         : Énumération des SRS autorisés (E0113/E0114).
        namespaces_attendus   : Préfixe XML → URI attendue (E0113).
        fragment_url_xsd      : Fragment d'URL identifiant la version dans le
                                xsi:schemaLocation (E0113 et détection).
        chemin_xsd            : Chemin du XSD officiel de la version (E0112).
        prefixe_code          : Préfixe des codes de contrôle de la version
                                ("E11" -> E0110..E0114 ; "E01" -> E0010..E0014).
    """

    code: str
    sequences_rpd: dict[str, list[SlotSequence]]
    noms_rpd: frozenset[str]
    regles_par_type: dict[str, tuple[RegleMetier, ...]]
    types_rpd_avec_regles: frozenset[str]
    index_regles_valeurs: dict[tuple[str, str], RegleValeur]
    types_avec_regles: frozenset[str]
    sequences_entete: dict[str, list[SlotSequence]]
    types_entete: frozenset[str]
    cardinalites_entete: dict[str, tuple[int, int]]
    srs_autorises: frozenset[str]
    namespaces_attendus: dict[str, str]
    fragment_url_xsd: str
    chemin_xsd: Path
    prefixe_code: str
