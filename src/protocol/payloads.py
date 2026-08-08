from dataclasses import dataclass

@dataclass(slots=True)
class DiscoverPayload:
    name: str
    port: int


@dataclass(slots=True)
class DiscoverResponsePayload:
    name: str
    port: int