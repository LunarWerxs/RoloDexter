"""End-to-end ingestion of real export formats.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

from rolodexter import (
    ContactMapper,
)

# ═══════════════════════════════════════════════════════════════
#  INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════


class TestSalesforceIngestion:
    """Salesforce CamelCase headers resolve via normalizer (no service param)."""

    def test_lead(self, mapper: ContactMapper) -> None:
        payload = {
            "FirstName": "Akiko",
            "LastName": "Tanaka",
            "Email": "AKIKO@example.jp",
            "Phone": "+81-3-1234-5678",
            "Company": "Tokyo Tech",
            "Title": "CTO",
            "MailingCity": "tokyo",
            "MailingCountry": "JP",
            "LeadSource": "Website",
            "Industry": "Technology",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["first_name"] == "Akiko"
        assert result.normalized["last_name"] == "Tanaka"
        assert result.normalized["email"] == "akiko@example.jp"
        assert result.normalized["company"] == "Tokyo Tech"
        assert result.normalized["job_title"] == "CTO"
        assert result.normalized["source"] == "Website"


class TestGoogleContactsCSV:
    def test_csv_row(self, mapper: ContactMapper) -> None:
        payload = {
            "Given Name": "Carlos",
            "Family Name": "Rivera",
            "E-mail 1 - Value": "CARLOS@MAIL.COM",
            "Phone 1 - Value": "+52-55-1234-5678",
            "Organization 1 - Name": "Rivera & Sons",
            "Organization 1 - Title": "Partner",
            "Address 1 - City": "mexico city",
            "Birthday": "1985-03-22",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["first_name"] == "Carlos"
        assert result.normalized["last_name"] == "Rivera"
        assert result.normalized["email"] == "carlos@mail.com"
        assert result.normalized["company"] == "Rivera & Sons"
        assert result.normalized["birthday"] == "1985-03-22"


class TestOutlookCSV:
    def test_contact(self, mapper: ContactMapper) -> None:
        payload = {
            "First Name": "Emma",
            "Last Name": "Wilson",
            "E-mail Address": "emma@work.com",
            "Business Phone": "+44 20 7946 0958",
            "Mobile Phone": "+44 7700 900000",
            "Company": "London Ltd",
            "Job Title": "Director",
            "Business City": "london",
            "Business Postal Code": "SW1A 1AA",
            "Birthday": "12/25/1990",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["first_name"] == "Emma"
        assert result.normalized["work_phone"] == "+442079460958"
        assert result.normalized["city"] == "London"
        assert result.normalized["postal_code"] == "SW1A 1AA"


class TestHubSpotIngestion:
    def test_full_contact(self, mapper: ContactMapper) -> None:
        payload = {
            "firstname": "Maria",
            "lastname": "Garcia",
            "email": "  Maria.GARCIA@corp.com  ",
            "phone": "+1-555-234-5678",
            "mobilephone": "+1-555-999-0000",
            "company": "Acme Inc",
            "jobtitle": "VP of Sales",
            "address": "123 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "country": "US",
            "website": "https://acme.com",
            "lifecyclestage": "customer",
            "hs_lead_status": "Open",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["first_name"] == "Maria"
        assert result.normalized["last_name"] == "Garcia"
        assert result.normalized["email"] == "maria.garcia@corp.com"
        assert result.normalized["company"] == "Acme Inc"
        assert result.normalized["job_title"] == "VP of Sales"
        assert result.normalized["city"] == "Austin"
        assert result.normalized["postal_code"] == "78701"
        assert result.normalized["lifecycle_stage"] == "customer"
        assert result.unmatched_count == 0


class TestMailchimpIngestion:
    def test_subscriber(self, mapper: ContactMapper) -> None:
        payload = {
            "EMAIL": "bob@example.com",
            "FNAME": "bob",
            "LNAME": "smith",
            "PHONE": "(555) 321-0000",
            "COMPANY": "Widgets LLC",
            "BIRTHDAY": "05/15",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["email"] == "bob@example.com"
        assert result.normalized["first_name"] == "Bob"
        assert result.normalized["last_name"] == "Smith"
        assert result.normalized["company"] == "Widgets LLC"
        assert result.match_rate >= 0.8
