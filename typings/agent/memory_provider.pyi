# The slice of the Hermes API provider.py uses. Hermes isn't installed in CI; this keeps type checks honest there.
class MemoryProvider: ...

class RecallStatus:
    provider_label: str
    count: int
    glyph: str
    def __init__(self, provider_label: str, count: int, glyph: str = ...) -> None: ...

def is_trivial_prompt(text: str | None) -> bool: ...
