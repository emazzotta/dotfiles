"""Site experts, plus the generic fallback that reads every other site.

Adding a site: put a class with `name`, `matches(page)` and `extract(page, fetcher)`
in a module next to srf/, list an instance in EXPERTS, test it on a synthetic page.
"""

from __future__ import annotations

from typing import Final

from scrapelib.experts.base import Expert, Page
from scrapelib.experts.generic import GenericExpert
from scrapelib.experts.srf import SrfExpert

EXPERTS: Final[tuple[Expert, ...]] = (SrfExpert(),)
FALLBACK: Final[Expert] = GenericExpert()


def all_experts() -> tuple[Expert, ...]:
    return (*EXPERTS, FALLBACK)


def expert_names() -> tuple[str, ...]:
    return tuple(sorted(expert.name for expert in all_experts()))


def expert_for(page: Page, name: str | None = None) -> Expert:
    if name is not None:
        return named_expert(name)
    return next((expert for expert in EXPERTS if expert.matches(page)), FALLBACK)


def named_expert(name: str) -> Expert:
    for expert in all_experts():
        if expert.name == name:
            return expert
    raise ValueError(f"unknown expert {name!r}, known: {', '.join(expert_names())}")
