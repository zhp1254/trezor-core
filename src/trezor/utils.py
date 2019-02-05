import gc
import sys
from trezorutils import (  # noqa: F401
    EMULATOR,
    GITREV,
    MODEL,
    VERSION_MAJOR,
    VERSION_MINOR,
    VERSION_PATCH,
    halt,
    memcpy,
    set_mode_unprivileged,
)

if False:
    from typing import Iterable, Iterator, TypeVar, Sequence


def unimport_begin() -> Iterable[str]:
    return set(sys.modules)


def unimport_end(mods: Iterable[str]) -> None:
    for mod in sys.modules:
        if mod not in mods:
            # remove reference from sys.modules
            del sys.modules[mod]
            # remove reference from the parent module
            i = mod.rfind(".")
            if i < 0:
                continue
            path = mod[:i]
            name = mod[i + 1 :]
            try:
                delattr(sys.modules[path], name)
            except KeyError:
                # either path is not present in sys.modules, or module is not
                # referenced from the parent package. both is fine.
                pass
    # collect removed modules
    gc.collect()


def ensure(cond: bool, msg: str = None) -> None:
    if not cond:
        if msg is None:
            raise AssertionError()
        else:
            raise AssertionError(msg)


if False:
    Chunked = TypeVar("Chunked", bound=Sequence)


def chunks(items: Chunked, size: int) -> Iterator[Chunked]:
    for i in range(0, len(items), size):
        yield items[i : i + size]  # type: ignore


def format_amount(amount: int, decimals: int) -> str:
    d = pow(10, decimals)
    s = ("%d.%0*d" % (amount // d, decimals, amount % d)).rstrip("0")
    if s.endswith("."):
        s = s[:-1]
    return s


def format_ordinal(number: int) -> str:
    return str(number) + {1: "st", 2: "nd", 3: "rd"}.get(
        4 if 10 <= number % 100 < 20 else number % 10, "th"
    )


class HashWriter:
    def __init__(self, ctx):
        self.ctx = ctx
        self.buf = bytearray(1)  # used in append()

    def extend(self, buf: bytearray) -> None:
        self.ctx.update(buf)

    def write(self, buf: bytearray) -> None:  # alias for extend()
        self.ctx.update(buf)

    async def awrite(self, buf: bytearray) -> None:  # AsyncWriter interface
        self.ctx.update(buf)

    def append(self, b: int) -> None:
        self.buf[0] = b
        self.ctx.update(self.buf)

    def get_digest(self) -> bytes:
        return self.ctx.digest()


def obj_eq(l: object, r: object) -> bool:
    """
    Compares object contents, supports __slots__.
    """
    if l.__class__ is not r.__class__:
        return False
    if hasattr(l, "__slots__"):
        return obj_slots_dict(l) == obj_slots_dict(r)
    else:
        return l.__dict__ == r.__dict__


def obj_repr(o: object) -> str:
    """
    Returns a string representation of object, supports __slots__.
    """
    if hasattr(o, "__slots__"):
        d = obj_slots_dict(o)
    else:
        d = o.__dict__
    return "<%s: %s>" % (o.__class__.__name__, d)


def obj_slots_dict(o: object) -> dict:
    """
    Builds dict for o from defined __slots__.
    """
    d = {}
    for f in o.__slots__:
        d[f] = getattr(o, f, None)
    return d
