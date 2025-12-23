"""VedaLang compiler - transforms VedaLang source to TableIR."""

from .compiler import (
    SemanticValidationError,
    compile_vedalang_to_tableir,
    load_vedalang,
    validate_cross_references,
    validate_vedalang,
)
from .table_schemas import (
    TableValidationError,
    VedaFieldSchema,
    VedaTableLayout,
    VedaTableSchema,
    get_all_schemas,
    validate_tableir,
)

__all__ = [
    "SemanticValidationError",
    "TableValidationError",
    "VedaFieldSchema",
    "VedaTableLayout",
    "VedaTableSchema",
    "compile_vedalang_to_tableir",
    "get_all_schemas",
    "load_vedalang",
    "validate_cross_references",
    "validate_tableir",
    "validate_vedalang",
]
