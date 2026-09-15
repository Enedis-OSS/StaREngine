from collections.abc import Iterator, Sequence
from os import PathLike
from typing import Any
from xml.etree.ElementTree import Element as Element
from xml.etree.ElementTree import ElementTree as ElementTree
from xml.etree.ElementTree import XMLParser as XMLParser

class DefusedXMLParser(XMLParser):
    def __init__(
        self,
        html: object = ...,
        target: Any = ...,
        encoding: str | None = ...,
        forbid_dtd: bool = ...,
        forbid_entities: bool = ...,
        forbid_external: bool = ...,
    ) -> None: ...

def parse(
    source: str | bytes | PathLike[str],
    parser: XMLParser | None = ...,
    forbid_dtd: bool = ...,
    forbid_entities: bool = ...,
    forbid_external: bool = ...,
) -> ElementTree[Element]: ...
def fromstring(
    text: str | bytes, forbid_dtd: bool = ..., forbid_entities: bool = ..., forbid_external: bool = ...
) -> Element: ...
def iterparse(
    source: str | bytes,
    events: Sequence[str] | None = ...,
    forbid_dtd: bool = ...,
    forbid_entities: bool = ...,
    forbid_external: bool = ...,
) -> Iterator[tuple[str, Element]]: ...
def tostring(element: Element, encoding: str = ..., method: str = ...) -> str | bytes: ...
