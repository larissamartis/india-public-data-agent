"""Official state and UT list keyed on LGD codes, with name matching.

Every source joins to this list. A name that does not match fails the build, and a name that
matches a state which did not exist on the data's date (Telangana before June 2014, say)
is an error too, so impossible rows never reach the warehouse.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from functools import cache
from importlib import resources


class UnknownStateError(ValueError):
    """A state name that matches nothing in the reference list."""


class StateDateError(ValueError):
    """A state name that matches, but the state did not exist on the given date."""


@dataclass(frozen=True)
class State:
    code: int
    name: str
    kind: str
    valid_from: date | None
    valid_to: date | None
    aliases: tuple[str, ...]

    def exists_on(self, day: date) -> bool:
        if self.valid_from is not None and day < self.valid_from:
            return False
        return not (self.valid_to is not None and day > self.valid_to)


def normalise_name(name: str) -> str:
    """Lower-case, treat '&' as 'and', drop punctuation and extra spaces."""
    text = name.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.removeprefix("the ")


def _parse_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


@cache
def load_states() -> tuple[State, ...]:
    text = resources.files("bharat.reference").joinpath("states.csv").read_text(encoding="utf-8")
    states = []
    for row in csv.DictReader(text.splitlines()):
        states.append(
            State(
                code=int(row["state_code"]),
                name=row["state_name"],
                kind=row["kind"],
                valid_from=_parse_date(row["valid_from"]),
                valid_to=_parse_date(row["valid_to"]),
                aliases=tuple(a for a in row["aliases"].split("|") if a),
            )
        )
    return tuple(states)


@cache
def _name_index() -> dict[str, State]:
    index: dict[str, State] = {}
    for state in load_states():
        for name in (state.name, *state.aliases):
            key = normalise_name(name)
            if key in index and index[key] != state:
                raise ValueError(
                    f"Name {name!r} matches two states: {index[key].name}, {state.name}"
                )
            index[key] = state
    return index


def resolve_state(name: str, on: date | None = None) -> State:
    """Return the state for a source's name, optionally checking it existed on a date."""
    state = _name_index().get(normalise_name(name))
    if state is None:
        raise UnknownStateError(f"Unknown state name: {name!r}")
    if on is not None and not state.exists_on(on):
        raise StateDateError(f"{state.name} did not exist on {on.isoformat()}")
    return state
