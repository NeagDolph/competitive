from typing import NotRequired, TypedDict


class Link(TypedDict):
    href: str
    html: str
    title: NotRequired[str]
