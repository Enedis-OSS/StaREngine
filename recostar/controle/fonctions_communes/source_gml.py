"""
Localisation du GML source d'un jeu de controle.

La plupart des controles lisent les GeoJSON issus de la conversion. Deux cas
imposent de remonter au GML lui-meme :

  - la famille `xsd_structuration`, qui controle la structure du document et
    n'aurait rien a lire dans sa traduction ;
  - les controles portant sur un attribut que la conversion ne conserve pas —
    E-6207 et le couple `Leve` / `TypeLeve`, retire par la normalisation V1.0
    vers V1.1.

Les deux posent la meme question : quel GML accompagne ce repertoire ? Elle est
resolue ici plutot que dans `pipeline_globale`, que les controles ne peuvent pas
importer sans inverser les dependances — l'orchestrateur les appelle, pas
l'inverse.
"""

from pathlib import Path

# Motif de recherche d'un GML dans un repertoire de jeu.
EXTENSION_GML: str = "*.gml"


def resoudre_chemin_gml(repertoire: Path, chemin_gml: Path | None = None) -> tuple[Path | None, str | None]:
    """Determine le GML accompagnant un repertoire. Retourne (chemin, motif_si_absent).

    Un chemin explicite est prioritaire. A defaut, la detection automatique
    n'aboutit que si le repertoire contient exactement un GML : plusieurs
    candidats rendraient le choix arbitraire, l'appelant est alors renseigne par
    un motif explicite plutot que de lire un fichier au hasard.

    Le motif est retourne plutot que leve : l'absence de GML n'est pas une
    erreur pour tous les appelants — un controle peut s'en passer et se replier
    sur les GeoJSON, une famille peut se declarer non executee.
    """
    if chemin_gml is not None:
        chemin = chemin_gml.resolve()
        if not chemin.is_file():
            return None, f"Fichier GML introuvable : {chemin}"
        return chemin, None

    candidats = sorted(repertoire.glob(EXTENSION_GML))
    if not candidats:
        return None, "Aucun fichier GML dans le repertoire"
    if len(candidats) > 1:
        noms = ", ".join(candidat.name for candidat in candidats)
        return None, f"{len(candidats)} fichiers GML trouves ({noms}) : precisez --gml"
    return candidats[0], None
