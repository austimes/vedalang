"""VedaLang compiler - transforms VedaLang source to TableIR."""

from .compiler import (
    compile_vedalang_to_tableir,
    load_vedalang,
    validate_vedalang,
)

__all__ = [
    "compile_vedalang_to_tableir",
    "load_vedalang",
    "validate_vedalang",
]
