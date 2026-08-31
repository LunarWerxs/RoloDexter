"""Translated aliases and language selection.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

from unittest.mock import patch as _mock_patch

import pytest

from rolodexter import (
    ContactMapper,
    PatternRegistry,
)


class TestI18nAliases:
    """Verify i18n aliases resolve when language data is available.

    Uses mock cached data to avoid needing deep-translator at test time.
    """

    # Fake i18n data matching what the generator would produce
    _MOCK_ES = {  # noqa: RUF012
        "language_code": "es",
        "language_name": "Spanish",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": [
                "nombre de pila",
                "nombre_de_pila",
                "nombredepila",
                "nombre-de-pila",
            ],
            "last_name": ["apellido"],
            "full_name": [
                "nombre completo",
                "nombre_completo",
                "nombrecompleto",
                "nombre-completo",
            ],
            "email": [
                "correo electronico",
                "correo_electronico",
                "correoelectronico",
                "correo-electronico",
                "correo",
            ],
            "company": ["empresa"],
            "city": ["ciudad"],
            "message": ["mensaje"],
            "subject": ["asunto"],
        },
    }
    _MOCK_DE = {  # noqa: RUF012
        "language_code": "de",
        "language_name": "German",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["vorname"],
            "last_name": ["nachname"],
            "full_name": ["vollstandiger name", "vollstandiger_name"],
            "company": ["firma"],
            "message": ["nachricht"],
            "subject": ["thema"],
        },
    }
    _MOCK_FR = {  # noqa: RUF012
        "language_code": "fr",
        "language_name": "French",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["prenom"],
            "last_name": ["nom de famille", "nom_de_famille"],
            "full_name": ["nom et prenom", "nom_et_prenom"],
            "email": ["e-mail"],
            "company": ["entreprise"],
            "subject": ["sujet"],
        },
    }
    _MOCK_RO = {  # noqa: RUF012
        "language_code": "ro",
        "language_name": "Romanian",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["prenume"],
            "last_name": ["nume"],
            "full_name": ["numele complet", "numele_complet"],
            "email": ["e-mail"],
            "company": ["companie"],
            "message": ["mesaj"],
            "subject": ["subiect"],
        },
    }
    _MOCK_PT = {  # noqa: RUF012
        "language_code": "pt",
        "language_name": "Portuguese",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "last_name": ["sobrenome"],
            "postal_code": ["codigo postal", "codigo_postal"],
        },
    }
    _MOCK_IT = {  # noqa: RUF012
        "language_code": "it",
        "language_name": "Italian",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "last_name": ["cognome"],
            "company": ["azienda"],
            "message": ["messaggio"],
        },
    }
    _MOCK_NL = {  # noqa: RUF012
        "language_code": "nl",
        "language_name": "Dutch",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["voornaam"],
            "last_name": ["achternaam"],
            "company": ["bedrijf"],
            "message": ["bericht"],
        },
    }
    _MOCK_PL = {  # noqa: RUF012
        "language_code": "pl",
        "language_name": "Polish",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["imie"],
            "last_name": ["nazwisko"],
            "message": ["wiadomosc"],
        },
    }
    _MOCK_TR = {  # noqa: RUF012
        "language_code": "tr",
        "language_name": "Turkish",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["ilk adi", "ilk_adi"],
            "last_name": ["soyisim"],
            "email": ["eposta"],
        },
    }

    _ALL_MOCKS = {  # noqa: RUF012
        "es": _MOCK_ES,
        "de": _MOCK_DE,
        "fr": _MOCK_FR,
        "ro": _MOCK_RO,
        "pt": _MOCK_PT,
        "it": _MOCK_IT,
        "nl": _MOCK_NL,
        "pl": _MOCK_PL,
        "tr": _MOCK_TR,
    }

    @staticmethod
    def _mock_load_cached(lang_code: str):
        return TestI18nAliases._ALL_MOCKS.get(lang_code)

    @pytest.mark.parametrize(
        "alias, expected",
        [
            # Romanian
            ("prenume", "first_name"),
            ("nume", "last_name"),
            ("numele_complet", "full_name"),
            ("mesaj", "message"),
            ("subiect", "subject"),
            # German
            ("vorname", "first_name"),
            ("nachname", "last_name"),
            ("firma", "company"),
            ("nachricht", "message"),
            ("thema", "subject"),
            # French
            ("nom_de_famille", "last_name"),
            ("nom_et_prenom", "full_name"),
            ("prenom", "first_name"),
            ("sujet", "subject"),
            ("entreprise", "company"),
            # Spanish
            ("nombre_de_pila", "first_name"),
            ("apellido", "last_name"),
            ("correo_electronico", "email"),
            ("empresa", "company"),
            ("ciudad", "city"),
            # Portuguese
            ("sobrenome", "last_name"),
            ("codigo_postal", "postal_code"),
            # Italian
            ("cognome", "last_name"),
            ("azienda", "company"),
            ("messaggio", "message"),
            # Dutch
            ("voornaam", "first_name"),
            ("achternaam", "last_name"),
            ("bedrijf", "company"),
            ("bericht", "message"),
            # Romanian extras
            ("companie", "company"),
            # Polish
            ("imie", "first_name"),
            ("nazwisko", "last_name"),
            ("wiadomosc", "message"),
            # Turkish
            ("ilk_adi", "first_name"),
            ("soyisim", "last_name"),
            ("eposta", "email"),
        ],
    )
    def test_i18n_alias_resolves(self, alias: str, expected: str) -> None:
        from unittest.mock import patch

        with patch("rolodexter.i18n.load_cached", side_effect=self._mock_load_cached):
            reg = PatternRegistry(
                languages=["es", "de", "fr", "ro", "pt", "it", "nl", "pl", "tr"]
            )
        assert reg.exact_lookup(alias) == expected


# Shared mock data for i18n tests
_MOCK_I18N = {
    "es": {
        "language_code": "es",
        "language_name": "Spanish",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["nombre de pila", "nombre_de_pila"],
            "last_name": ["apellido"],
            "full_name": ["nombre completo", "nombre_completo"],
            "email": ["correo electronico", "correo_electronico", "correo"],
            "company": ["empresa"],
            "city": ["ciudad"],
        },
    },
    "de": {
        "language_code": "de",
        "language_name": "German",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["vorname"],
            "last_name": ["nachname"],
            "company": ["firma"],
        },
    },
    "fr": {
        "language_code": "fr",
        "language_name": "French",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["prenom"],
            "last_name": ["nom de famille", "nom_de_famille"],
            "email": ["e-mail"],
            "company": ["entreprise"],
        },
    },
}


def _mock_load_cached(lang_code: str):
    return _MOCK_I18N.get(lang_code)


class TestI18nLanguageSelection:
    """Test the languages parameter for selective i18n loading."""

    def test_default_is_english_only(self) -> None:
        """Default (no languages) loads English only — no i18n."""
        reg = PatternRegistry()
        assert reg.loaded_languages == []
        assert reg.exact_lookup("email") == "email"
        assert reg.exact_lookup("correo") is None

    def test_english_only_with_none(self) -> None:
        reg = PatternRegistry(languages=None)
        assert reg.loaded_languages == []
        assert reg.exact_lookup("email") == "email"
        assert reg.exact_lookup("first_name") == "first_name"
        assert reg.exact_lookup("correo") is None
        assert reg.exact_lookup("vorname") is None

    def test_english_only_with_empty_list(self) -> None:
        reg = PatternRegistry(languages=[])
        assert reg.loaded_languages == []
        assert reg.exact_lookup("correo") is None

    def test_single_language_string(self) -> None:
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            reg = PatternRegistry(languages="es")
        assert reg.loaded_languages == ["es"]
        assert reg.exact_lookup("correo_electronico") == "email"
        assert reg.exact_lookup("empresa") == "company"
        assert reg.exact_lookup("vorname") is None

    def test_selective_language_list(self) -> None:
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            reg = PatternRegistry(languages=["fr", "de"])
        assert sorted(reg.loaded_languages) == ["de", "fr"]
        assert reg.exact_lookup("prenom") == "first_name"
        assert reg.exact_lookup("vorname") == "first_name"
        assert reg.exact_lookup("correo_electronico") is None

    def test_nonexistent_language_skipped(self) -> None:
        """Unknown language codes are silently skipped."""
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            reg = PatternRegistry(languages=["xx_fake", "es"])
        # xx_fake skipped, es loaded
        assert reg.loaded_languages == ["es"]
        assert reg.exact_lookup("correo_electronico") == "email"


class TestI18nAvailableLanguages:
    """Test the available_languages property (lists SUPPORTED_LANGUAGES)."""

    def test_available_languages_lists_all_supported(self) -> None:
        reg = PatternRegistry(languages=None)
        langs = reg.available_languages
        # SUPPORTED_LANGUAGES has 40 entries
        assert len(langs) >= 30
        for code in [
            "es",
            "fr",
            "de",
            "ro",
            "pt",
            "it",
            "nl",
            "ja",
            "pl",
            "tr",
            "ru",
            "zh",
            "ko",
            "ar",
            "hi",
            "sv",
            "da",
            "nb",
            "fi",
            "cs",
        ]:
            assert code in langs, f"{code} not in available_languages"

    def test_available_vs_loaded(self) -> None:
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            reg = PatternRegistry(languages=["es"])
        assert len(reg.available_languages) >= 30
        assert len(reg.loaded_languages) == 1


class TestI18nContactMapper:
    """Test that ContactMapper passes languages through."""

    def test_mapper_default_english_only(self) -> None:
        mapper = ContactMapper()
        assert mapper.registry.loaded_languages == []
        assert mapper.registry.exact_lookup("correo") is None
        m = mapper.identify("email")
        assert m.canonical == "email"

    def test_mapper_english_only_explicit(self) -> None:
        mapper = ContactMapper(languages=None)
        assert mapper.registry.loaded_languages == []
        assert mapper.registry.exact_lookup("vorname") is None
        m = mapper.identify("email")
        assert m.canonical == "email"

    def test_mapper_selective_languages(self) -> None:
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            mapper = ContactMapper(languages=["de"])
        m = mapper.identify("vorname")
        assert m.canonical == "first_name"
        assert mapper.registry.exact_lookup("correo") is None

    def test_mapper_payload_with_i18n(self) -> None:
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            mapper = ContactMapper(languages=["es", "fr"])
        result = mapper.map_payload(
            {
                "correo_electronico": "juan@example.com",
                "nombre_de_pila": "Juan",
                "apellido": "García",
                "empresa": "Acme",
                "e-mail": "duplicate@example.com",
            }
        )
        assert result.normalized["email"] == [
            "juan@example.com",
            "duplicate@example.com",
        ]
        assert result.normalized["first_name"] == "Juan"
        assert result.normalized["last_name"] == "García"
        assert result.normalized["company"] == "Acme"
