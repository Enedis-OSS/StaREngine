"""Traitements partages par les controles, independants de tout controle particulier.

Un module de ce paquet ne connait aucun code de controle : il porte une logique
reutilisable (lecture GeoJSON, geometrie, emprise DR, vocabulaire du modele
RecoStaR, detection de version...) que plusieurs controles consomment. C'est le
seul endroit ou une logique partagee est implementee : un controle qui en
importerait un autre pour reutiliser une fonction signalerait une extraction
manquante ici.
"""
