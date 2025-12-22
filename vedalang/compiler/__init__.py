"""VedaLang compiler - transforms VedaLang source to TableIR."""

from .compiler import (
    SemanticValidationError,
    compile_vedalang_to_tableir,
    load_vedalang,
    validate_cross_references,
    validate_vedalang,
)

__all__ = [
    "SemanticValidationError",
    "compile_vedalang_to_tableir",
    "load_vedalang",
    "validate_cross_references",
    "validate_vedalang",
]
