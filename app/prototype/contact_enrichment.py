from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from pydantic import ValidationError

from app.benchmark.providers.base import ProviderAdapterError, ProviderNotConfiguredError
from app.benchmark.schemas import ProviderEvidence, ProviderRawSource
from app.prototype.schemas import ContactSellerCard, PrototypeSourcingLink
from app.schemas import ProductUnderstanding


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


@dataclass
class ContactProviderAttempt:
    provider_id: str
    status: str
    api_calls: int = 0
    raw_sources_count: int = 0
    latency_ms: int = 0


@dataclass
class ContactEnrichmentResult:
    contacts: list[ContactSellerCard] = field(default_factory=list)
    provider_attempts: list[ContactProviderAttempt] = field(default_factory=list)
    provider_api_calls: int = 0
    latency_ms: int = 0
    status: str = "not_found"
    rejected_count: int = 0
    rejection_reasons: list[str] = field(default_factory=list)


class ContactEnrichmentAgent:
    def __init__(self, providers: list[object]) -> None:
        self.providers = providers

    async def enrich(self, links: list[PrototypeSourcingLink]) -> ContactEnrichmentResult:
        started = time.perf_counter()
        contacts: list[ContactSellerCard] = []
        attempts: list[ContactProviderAttempt] = []
        api_calls = 0
        rejected_count = 0
        rejection_reasons: list[str] = []

        for link in links:
            saved_contacts = _contacts_from_sources(link.title, _sources_from_link_evidence(link))
            if saved_contacts:
                contacts.extend(saved_contacts)
                continue

            contact = _contact_from_text(link.title, link.title, "")
            if _has_usable_contact(contact):
                contacts.append(contact)
                continue

            search_result = await self._search_contact(link)
            attempts.extend(search_result.provider_attempts)
            api_calls += search_result.provider_api_calls
            if search_result.contacts:
                contacts.extend(search_result.contacts)
            else:
                rejected_count += 1
                rejection_reasons.append(f"No usable public contact found for {link.title or 'seller'}.")

        usable_contacts = [contact for contact in _dedupe_contacts(contacts) if _has_usable_contact(contact)]
        return ContactEnrichmentResult(
            contacts=usable_contacts,
            provider_attempts=attempts,
            provider_api_calls=api_calls,
            latency_ms=_elapsed_ms(started),
            status="success" if usable_contacts else "not_found",
            rejected_count=rejected_count + sum(1 for contact in contacts if not _has_usable_contact(contact)),
            rejection_reasons=list(dict.fromkeys(rejection_reasons)),
        )

    async def _search_contact(self, link: PrototypeSourcingLink) -> ContactEnrichmentResult:
        attempts: list[ContactProviderAttempt] = []
        contacts: list[ContactSellerCard] = []
        api_calls = 0
        supplier_name = link.title or "supplier"
        queries = [
            f"{supplier_name} contact email",
            f"{supplier_name} WhatsApp",
            f"{supplier_name} contact",
            f"{supplier_name} Alibaba supplier contact",
            f"{supplier_name} Made-in-China contact",
            f"{supplier_name} sales email",
        ]
        for provider in self.providers:
            provider_id = getattr(provider, "provider_id", "unknown")
            for query in queries:
                started = time.perf_counter()
                try:
                    evidence = await _provider_contact_search(provider, query)
                except (ProviderNotConfiguredError, ProviderAdapterError):
                    attempts.append(ContactProviderAttempt(provider_id, "failed", latency_ms=_elapsed_ms(started)))
                    break
                api_calls += evidence.provider_api_calls
                attempts.append(
                    ContactProviderAttempt(
                        provider_id=provider_id,
                        status="success",
                        api_calls=evidence.provider_api_calls,
                        raw_sources_count=len(evidence.sources),
                        latency_ms=_elapsed_ms(started),
                    )
                )
                contacts = _contacts_from_sources(supplier_name, evidence.sources)
                if contacts:
                    break
            if contacts:
                break
        return ContactEnrichmentResult(
            contacts=contacts,
            provider_attempts=attempts,
            provider_api_calls=api_calls,
            status="success" if contacts else "not_found",
        )


async def _provider_contact_search(provider: object, query: str) -> ProviderEvidence:
    if hasattr(provider, "search_contact"):
        return await provider.search_contact(query)
    product = ProductUnderstanding(
        original_product=query,
        normalized_product=query,
        english_search_name=query,
        french_search_name=query,
    )
    return await provider.search_group(product, "china_sourcing")


def _contacts_from_sources(supplier_name: str, sources: list[ProviderRawSource]) -> list[ContactSellerCard]:
    contacts: list[ContactSellerCard] = []
    for source in sources:
        source_host = _source_host(source.url)
        contact = _contact_from_text(
            supplier_name,
            source.title,
            " ".join([source.snippet, source.content or ""]),
            source_host=source_host,
            source_url=source.url,
        )
        if not _has_usable_contact(contact) and _looks_like_contact_page(source):
            parsed = urlparse(source.url)
            website = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
            contact = contact.model_copy(
                update={
                    "website": website,
                    "website_source": source_host,
                    "contact_page_url": source.url,
                    "contact_page_source": source_host,
                    "contact_confidence": "medium",
                    "contact_notes": "Official contact page found from public search evidence.",
                }
            )
        if _has_usable_contact(contact):
            contacts.append(contact)
    return contacts


def _sources_from_link_evidence(link: PrototypeSourcingLink) -> list[ProviderRawSource]:
    sources: list[ProviderRawSource] = []
    for source in link.evidence_sources:
        try:
            sources.append(ProviderRawSource.model_validate(source))
        except ValidationError:
            continue
    return sources


def _contact_from_text(
    seller_name: str,
    title: str,
    text: str,
    *,
    source_host: str | None = None,
    source_url: str | None = None,
) -> ContactSellerCard:
    haystack = " ".join([title, text])
    email = _first_match(EMAIL_RE, haystack)
    phones = [
        match.group(0).strip()
        for match in PHONE_RE.finditer(haystack)
        if _looks_like_public_phone(match.group(0), haystack, match.start(), match.end())
    ]
    phone = phones[0] if phones else None
    whatsapp = None
    lowered = haystack.lower()
    if "whatsapp" in lowered and phone:
        whatsapp = phone
    website = None
    if source_url and (email or phone or whatsapp):
        parsed = urlparse(source_url)
        if parsed.scheme and parsed.netloc:
            website = f"{parsed.scheme}://{parsed.netloc}"
    return ContactSellerCard(
        seller_name=seller_name,
        company_name=seller_name,
        email=email,
        email_source=source_host if email else None,
        phone=phone,
        phone_source=source_host if phone else None,
        whatsapp=whatsapp,
        whatsapp_source=source_host if whatsapp else None,
        website=website,
        website_source=source_host if website else None,
        contact_confidence="medium" if email or whatsapp else "low",
        contact_notes="Contact extracted from public supplier/product evidence." if email or phone else "",
    )


def _has_direct_contact(contact: ContactSellerCard) -> bool:
    return bool(contact.email or contact.phone or contact.whatsapp)


def _has_usable_contact(contact: ContactSellerCard) -> bool:
    return bool(
        contact.email
        or contact.phone
        or contact.whatsapp
        or contact.contact_page_url
        or contact.website
    )


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match else None


def _source_host(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host or None


def _looks_like_public_phone(candidate: str, text: str, start: int, end: int) -> bool:
    if "." in candidate:
        return False
    digits = re.sub(r"\D", "", candidate)
    if len(digits) < 8 or len(digits) > 15:
        return False
    context = text[max(0, start - 40): min(len(text), end + 40)].lower()
    contact_signal = any(signal in context for signal in ("phone", "tel", "call", "whatsapp", "mobile", "contact"))
    if any(signal in context for signal in ("sku", "model", "t9", "item no", "item#", "tracking")):
        return False
    price_signal = any(signal in context for signal in ("us$", "$", "usd", "price", "moq", "piece", "pieces"))
    if price_signal and not contact_signal:
        return False
    if "-" in candidate and not contact_signal:
        return False
    return True


def _dedupe_contacts(contacts: list[ContactSellerCard]) -> list[ContactSellerCard]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[ContactSellerCard] = []
    for contact in contacts:
        key = (
            contact.seller_name.lower(),
            (contact.email or "").lower(),
            contact.whatsapp or contact.phone or contact.contact_page_url or contact.website or "",
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(contact)
    return deduped


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _looks_like_contact_page(source: ProviderRawSource) -> bool:
    parsed = urlparse(source.url)
    path = (parsed.path or "").lower()
    text = " ".join([source.title, source.snippet, source.content or ""]).lower()
    lowered = f"{path} {text}"
    if "no-contact" in lowered:
        return False
    return any(
        signal in lowered
        for signal in (
            "/contact",
            "contact/",
            "contact us",
            "contact supplier",
            "contactez",
            "sales inquiries",
            "supplier contact",
        )
    )
