from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class F1Leaf:
    """
    Single F1 subsystem (generalised).
    """

    code: str
    description: str
    is_common: bool
    count: int = 1
    present_in: list[str] = field(default_factory=list)


@dataclass
class F1Section:
    """
    Group of F1 leaves sharing the same 3-letter prefix (e.g. MQA, BFA).
    """

    prefix: str
    label: str
    description: str = ""
    leaves: list[F1Leaf] = field(default_factory=list)


@dataclass
class F0Group:
    """
    One generalised F0 system group (e.g. =G00n).
    """

    code: str
    description: str
    instances: list[str]
    count: int
    f1_sections: list[F1Section] = field(default_factory=list)
