#!/usr/bin/env python3
"""
Contrat commun décrivant un profil de version RecoStaR pour les contrôles XSD.

Un `ProfilVersion` agrège l'ensemble des tables de données (séquences,
règles métier, règles de valeurs, en-tête) et des constantes qui varient
d'une version du format RecoStaR à l'autre (V1.0, V1.1). Les moteurs de
contrôle (E110 à E114) restent uniques et version-agnostiques : ils reçoivent
ce profil et y lisent les tables à appliquer.

Architecture évolutive : ajouter une version = créer un module `versions/vX_Y`
qui instancie un `ProfilVersion`, puis l'enregistrer dans `versions.__init__`.
Aucun moteur n'est à modifier.
"""

from dataclasses import dataclass
from pathlib import Path

from regles_metier import RegleMetier
from regles_valeurs import RegleValeur
from sequenceur_xsd import SlotSequence


# frozen : profil immuable, partageable sans risque de mutation accidentelle.
# slots : empreinte mémoire réduite et accès attribut plus rapide (un seul
# profil par version est instancié, mais le gain reste cohérent avec le reste
# du code qui utilise systématiquement __slots__).
@dataclass(frozen=True, slots=True)
class ProfilVersion:
    """Regroupe toutes les données propres à une version du format RecoStaR.

    Attributs :
        code                  : Identifiant de version ("1.0", "1.1").
        sequences_rpd         : Séquence XSD attendue par type RPD (E110).
        noms_rpd              : Ensemble des types RPD connus de la version (E110).
        regles_par_type       : Index des règles métier par type RPD (E111).
        types_rpd_avec_regles : Types RPD soumis à au moins une règle (E111).
        index_regles_valeurs  : Index (type_rpd, champ) → règle de valeur (E114).
        types_avec_regles     : Types portant au moins une règle de valeur (E114).
        sequences_entete      : Séquence attendue des objets d'en-tête (E113).
        types_entete          : Ensemble des objets d'en-tête connus (E113).
        cardinalites_entete   : Cardinalité (min, max) par objet d'en-tête (E113).
        srs_autorises         : Énumération des SRS autorisés (E113/E114).
        namespaces_attendus   : Préfixe XML → URI attendue (E113).
        fragment_url_xsd      : Fragment d'URL identifiant la version dans le
                                xsi:schemaLocation (E113 et détection).
        chemin_xsd            : Chemin du XSD officiel de la version (E112).
        prefixe_code          : Préfixe des codes de contrôle de la version
                                ("E11" -> E110..E114 ; "E01" -> E010..E014).
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
