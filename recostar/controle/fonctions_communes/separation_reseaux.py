"""
Separation du reseau electrique et du reseau de telecommunication.

Le modele RecoStaR decrit les deux reseaux dans un meme jeu, et le verificateur
interdit de les melanger. Quatre codes portent cette regle, sur deux relations
differentes :

    cables_href    noeud -> cable      E-6113, E-6115, E-6213
    conteneur_href noeud -> conteneur  E-6114

Tous posent la meme question prealable — cette entite appartient-elle au reseau
de telecommunication ? — sur des entites differentes : les trois premiers sur le
noeud qui porte la reference, E-6114 sur le coffret qui la subit. Les predicats
sont donc tenus ici et non dans l'un des controles : aucun n'en est
proprietaire, et les declarer dans un moteur obligerait un controle a dependre
d'un autre.

Ce qu'est une entite de telecommunication
-----------------------------------------
Le modele ne porte pas d'attribut « reseau » : l'appartenance se lit sur le type
de l'entite, et sur lui seul.

  - noeud     : une RPD_Jonction_Reco dont le TypeJonction vaut Telecom. Aucune
                autre couche de noeud n'appartient au reseau de
                telecommunication ;
  - conteneur : un RPD_Coffret_Reco dont le TypeCoffret vaut Telecom.

Les deux valeurs sont celles des enumerations du XSD (TypeJonction §10.4.1,
TypeCoffret §10.3.2) ; leur validite releve du controle de structuration
E0114 / E0014, non des controles
qui les lisent.
"""

from collections.abc import Mapping
from typing import Any

from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_TYPE_COFFRET_HREF,
    CHAMP_TYPE_JONCTION,
    COUCHE_JONCTION,
    TYPE_COFFRET_TELECOM,
    TYPE_JONCTION_TELECOM,
)
from recostar.controle.fonctions_communes.proprietes import valeur_code_liste


def est_noeud_telecom(couche: str, proprietes: Mapping[str, Any]) -> bool:
    """Indique si le noeud appartient au reseau de telecommunication.

    Seule une jonction de TypeJonction Telecom en releve. La couche est testee
    d'abord : aucune autre entite ne porte de TypeJonction, et lire le champ sur
    les autres couches serait sans objet.
    """
    return couche == COUCHE_JONCTION and proprietes.get(CHAMP_TYPE_JONCTION) == TYPE_JONCTION_TELECOM


def est_coffret_telecom(proprietes: Mapping[str, Any]) -> bool:
    """Indique si le coffret appartient au reseau de telecommunication.

    Le TypeCoffret n'est pas porte tel quel par le GeoJSON : c'est une reference
    de code-list, resolue par `valeur_code_liste`. Un coffret sans TypeCoffret
    n'est pas un coffret de telecommunication — l'absence de la valeur releve du
    controle des valeurs, pas de celui qui la lit.
    """
    return valeur_code_liste(proprietes, CHAMP_TYPE_COFFRET_HREF) == TYPE_COFFRET_TELECOM
