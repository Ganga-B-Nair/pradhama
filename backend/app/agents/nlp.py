"""spaCy `en_core_web_sm` for person names in the English narration (§3).
Loaded lazily, once; if the model isn't installed, callers fall back to regex."""
from functools import lru_cache


@lru_cache(maxsize=1)
def _nlp():
    import spacy

    return spacy.load("en_core_web_sm")


def person_names(text: str) -> list[str]:
    return [ent.text.split()[0] for ent in _nlp()(text).ents if ent.label_ == "PERSON"]
