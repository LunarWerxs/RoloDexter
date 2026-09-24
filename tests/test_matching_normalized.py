"""The normalized match strategy: CamelCase, dot paths, separators.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

import pytest

from rolodexter import (
    NormalizedMatchStrategy,
    PatternRegistry,
)


class TestNormalizedMatchStrategy:
    """NormalizedMatchStrategy: smart header normalization → exact lookup."""

    def test_camel_first_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("FirstName")
        assert (
            m is not None
            and m.canonical == "first_name"
            and m.confidence == 0.95
            and m.strategy == "normalized"
        )

    @pytest.mark.parametrize(
        "header, expected",
        [
            # CamelCase
            ("MobilePhone", "phone"),
            ("MailingStreet", "address_line1"),
            ("MailingPostalCode", "postal_code"),
            ("AnnualRevenue", "revenue"),
            ("CreatedDate", "created_at"),
            ("LastModifiedDate", "updated_at"),
            ("LeadSource", "source"),
            ("countryCode", "country"),
            ("modifiedAt", "updated_at"),
            # Space → underscore
            ("First Name", "first_name"),
            ("Email Address", "email"),
            ("Last Modified", "updated_at"),
            # Dot paths; a company-like object's .name is the company
            ("fields.last_name", "last_name"),
            ("Account.Name", "company"),
            ("companies.name", "company"),
            ("Account.FirstName", "first_name"),
            # Indexed pattern (Google Contacts style)
            ("E-mail 1 - Value", "email"),
            ("Phone 1 - Value", "phone"),
            ("Organization 1 - Name", "company"),
            ("Organization 1 - Title", "job_title"),
            ("Organization 1 - Department", "department"),
            ("Address 1 - Street", "address_line1"),
            ("Address 1 - City", "city"),
            ("Address 1 - Region", "state"),
            ("Address 1 - Postal Code", "postal_code"),
            ("Address 1 - Country", "country"),
            ("Website 1 - Value", "website"),
            # Vendor prefix stripping
            ("hs_lead_status", "lead_status"),
            ("hubspot_owner_id", "owner"),
            # Address prefix stripping
            ("Business City", "city"),
            ("Business Street", "address_line1"),
            ("Business Country/Region", "country"),
            ("billing_city", "city"),
            # _id suffix stripping
            ("OwnerId", "owner"),
            ("owner_id", "owner"),
            # Number stripping
            ("E-mail 2 Address", "email"),
            ("phone_2", "phone"),
            # Hyphen → underscore (W3C tokens)
            ("given-name", "first_name"),
            ("family-name", "last_name"),
            ("additional-name", "middle_name"),
            ("honorific-prefix", "prefix"),
            ("honorific-suffix", "suffix"),
            ("country-name", "country"),
            # DOUBLE_OPT-IN (Brevo) — hyphen mid-word → subscribed (affirmative)
            ("DOUBLE_OPT-IN", "subscribed"),
        ],
    )
    def test_header_resolves(
        self, registry: PatternRegistry, header: str, expected: str
    ) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match(header)
        assert m is not None and m.canonical == expected

    def test_no_match_garbage(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        assert strat.match("xyzzy_garbage_nonsense") is None

    def test_empty_header_returns_none(self) -> None:
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        assert strat.match("") is None
        assert strat.match("   ") is None
