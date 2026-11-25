"""
Módulo de Processamento de Linguagem Natural (NLP) em Português do Brasil para o Silva Agent.
Exporta analisador numérico composto, normalizador de gírias/typos e roteador baseado em pontuação.
"""

try:
    from .numbers import parse_ptbr_numbers
    from .colloquial import normalize_colloquial_ptbr, CANONICAL_VOCAB
    from .router import (
        ScoredIntentRouter,
        normalize_text,
        _strip_accents,
        _prepare_texts,
        _sanitize_entity_arg,
        _format_call,
        _protect_compound_names,
        _unprotect_compound_names,
        _mask_protected_entities,
        _unmask_protected_entities,
        _strip_conversational_fillers,
        _normalize_math_expression,
        _clean_ride_destination,
        _clean_food_query,
        _clean_install_app_name,
        _clean_weather_location,
        _clean_search_query,
        _strip_leading_articles,
        ALLOWED_MATH_NAMES,
    )
except ImportError:
    from numbers import parse_ptbr_numbers
    from colloquial import normalize_colloquial_ptbr, CANONICAL_VOCAB
    from router import (
        ScoredIntentRouter,
        normalize_text,
        _strip_accents,
        _prepare_texts,
        _sanitize_entity_arg,
        _format_call,
        _protect_compound_names,
        _unprotect_compound_names,
        _mask_protected_entities,
        _unmask_protected_entities,
        _strip_conversational_fillers,
        _normalize_math_expression,
        _clean_ride_destination,
        _clean_food_query,
        _clean_install_app_name,
        _clean_weather_location,
        _clean_search_query,
        _strip_leading_articles,
        ALLOWED_MATH_NAMES,
    )

__all__ = [
    "parse_ptbr_numbers",
    "normalize_colloquial_ptbr",
    "CANONICAL_VOCAB",
    "ScoredIntentRouter",
    "normalize_text",
    "_strip_accents",
    "_prepare_texts",
    "_sanitize_entity_arg",
    "_format_call",
    "_protect_compound_names",
    "_unprotect_compound_names",
    "_normalize_math_expression",
    "_clean_ride_destination",
    "_clean_food_query",
    "_clean_install_app_name",
    "_clean_weather_location",
    "_clean_search_query",
    "_strip_leading_articles",
    "ALLOWED_MATH_NAMES",
]
