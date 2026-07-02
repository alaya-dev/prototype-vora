import unittest

from app.benchmark.schemas import ProviderRawSource
from app.prototype.contact_enrichment import ContactEnrichmentAgent, _contacts_from_sources, _has_usable_contact
from app.prototype.schemas import PrototypeSourcingLink


class ContactEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_enrich_uses_saved_listing_evidence_before_contact_search(self) -> None:
        agent = ContactEnrichmentAgent(providers=[])
        link = PrototypeSourcingLink(
            title="MarketUnion T9 listing",
            url="https://marketunion.example/t9",
            evidence_sources=[
                {
                    "title": "MarketUnion T9 wholesale listing",
                    "url": "https://marketunion.example/t9",
                    "snippet": "Contact supplier sales@marketunion.example WhatsApp +86 138 0013 8000",
                    "region_hint": "china_sourcing",
                    "source_type": "search_result",
                }
            ],
        )

        result = await agent.enrich([link])

        self.assertEqual(result.status, "success")
        self.assertEqual(result.provider_attempts, [])
        self.assertEqual(result.provider_api_calls, 0)
        self.assertEqual(result.contacts[0].email, "sales@marketunion.example")
        self.assertEqual(result.contacts[0].whatsapp, "+86 138 0013 8000")

    def test_price_ranges_are_not_treated_as_phone_numbers(self) -> None:
        contacts = _contacts_from_sources(
            "Vintage T9 Trimmer",
            [
                ProviderRawSource(
                    title="Alibaba listing",
                    url="https://example.com/t9",
                    snippet="US$0.55-0.65 MOQ 20 pieces. Price US$2.35-3.50.",
                    content="SKU 2853726960697 without public contact details.",
                    region_hint="china_sourcing",
                )
            ],
        )

        self.assertEqual(contacts, [])

    def test_extracts_public_business_email_and_whatsapp(self) -> None:
        contacts = _contacts_from_sources(
            "CN Factory",
            [
                ProviderRawSource(
                    title="CN Factory contact",
                    url="https://example.com/contact",
                    snippet="Contact sales@cnfactory.com WhatsApp +86 138 0013 8000",
                    region_hint="china_sourcing",
                )
            ],
        )

        self.assertEqual(contacts[0].email, "sales@cnfactory.com")
        self.assertEqual(contacts[0].whatsapp, "+86 138 0013 8000")

    def test_empty_placeholder_is_not_a_usable_contact(self) -> None:
        contacts = _contacts_from_sources(
            "CN Factory",
            [
                ProviderRawSource(
                    title="CN Factory listing",
                    url="https://example.com/product",
                    snippet="Wholesale price US$2 MOQ 100. No public contact details.",
                    region_hint="china_sourcing",
                )
            ],
        )

        self.assertEqual(contacts, [])

    def test_contact_page_url_counts_as_usable_public_contact(self) -> None:
        contacts = _contacts_from_sources(
            "CN Factory",
            [
                ProviderRawSource(
                    title="CN Factory contact page",
                    url="https://cnfactory.example/contact",
                    snippet="Contact us for sales inquiries.",
                    region_hint="china_sourcing",
                )
            ],
        )

        self.assertTrue(_has_usable_contact(contacts[0]))
        self.assertEqual(contacts[0].contact_page_url, "https://cnfactory.example/contact")
