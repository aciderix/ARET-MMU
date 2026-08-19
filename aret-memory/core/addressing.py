"""Adressage canonique et validation stricte des ressources ARET."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, unquote

SCHEMES = {
    "knowledge": "knowledge",
    "component": "component",
    "function": "function",
    "brick": "brick",
    "proof": "proof",
    "relation": "relation",
}


@dataclass(frozen=True)
class Address:
    """Une adresse ARET validée, sans heuristique de résolution."""

    resource_type: str
    identifier: str

    @property
    def canonical(self) -> str:
        if self.resource_type == "front" and self.identifier == "current":
            return "ARET://front/current"
        return f"ARET://{self.resource_type}/{quote(self.identifier, safe='!._-')}"


def make_address(resource_type: str, identifier: str) -> str:
    """Construit une adresse sans accepter de type ou d’identifiant vide."""
    if resource_type == "front" and identifier == "current":
        return "ARET://front/current"
    if resource_type not in SCHEMES:
        raise ValueError(f"Type de ressource ARET inconnu : {resource_type}")
    if not identifier or "/" in identifier:
        raise ValueError("Identifiant ARET vide ou invalide")
    return Address(resource_type, identifier).canonical


def parse_address(address: str) -> Address:
    """Parse une seule adresse absolue ARET, sans recherche ni approximation."""
    if not isinstance(address, str) or not address.startswith("ARET://"):
        raise ValueError("Adresse invalide : le préfixe ARET:// est requis")
    rest = address[len("ARET://") :]
    parts = rest.split("/", 1)
    if len(parts) != 2:
        raise ValueError("Adresse invalide : une ressource et un identifiant sont requis")
    resource_type, raw_identifier = parts
    identifier = unquote(raw_identifier)
    if resource_type == "front" and identifier == "current":
        return Address(resource_type, identifier)
    if resource_type not in SCHEMES or not identifier or "/" in identifier:
        raise ValueError("Adresse ARET inconnue ou non canonique")
    return Address(resource_type, identifier)
