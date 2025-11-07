from __future__ import annotations

import re
from urllib.parse import urlparse

from aiogram.enums import ContentType, MessageEntityType
from aiogram.types import Message

LINK_REGEX = re.compile(
    r"(?P<url>(?:https?://|www\.)[\w\-\._~:/?#\[\]@!\$&'\(\)\*\+,;=%]+)",
    flags=re.IGNORECASE,
)

AD_KEYWORDS = [
    "airdrop",
    "buy my token",
    "free mint",
    "pump",
    "referral",
    "invite link",
    "promo",
    "earn passive income",
    "giveaway",
]

WHITELISTED_AD_KEYWORDS = {
    "airdrop",
    "buy my token",
    "free mint",
    "pump",
    "referral",
    "invite link",
    "promo",
    "earn passive income",
    "giveaway",
}

WHITELISTED_KEYWORDS = {
    "airdrop": ["spl shield"],
    "promo": ["spl shield"],
}

TG_INVITE_PATTERNS = [
    "t.me/joinchat",
    "t.me/+",
    "telegram.me/joinchat",
]


def extract_links(message: Message) -> set[str]:
    """Return distinct domains extracted from the message text/entities."""
    domains: set[str] = set()

    def _add(url: str) -> None:
        parsed = urlparse(url if url.startswith(("http://", "https://")) else f"http://{url}")
        if parsed.hostname:
            domains.add(parsed.hostname.lower())

    text = message.text or ""
    for match in LINK_REGEX.finditer(text):
        _add(match.group("url"))

    for entity in message.entities or []:
        if entity.type in (MessageEntityType.TEXT_LINK, MessageEntityType.URL):
            url = entity.url or entity.extract_from(text)
            if url:
                _add(url)

    caption = message.caption or ""
    for match in LINK_REGEX.finditer(caption):
        _add(match.group("url"))

    for entity in message.caption_entities or []:
        if entity.type in (MessageEntityType.TEXT_LINK, MessageEntityType.URL):
            url = entity.url or entity.extract_from(caption)
            if url:
                _add(url)

    return domains


def contains_media(message: Message) -> bool:
    media_types = {
        ContentType.ANIMATION,
        ContentType.AUDIO,
        ContentType.DOCUMENT,
        ContentType.PHOTO,
        ContentType.VIDEO,
        ContentType.VOICE,
        ContentType.VIDEO_NOTE,
        ContentType.STICKER,
    }
    return any(message.content_type == media for media in media_types)


def count_mentions(message: Message) -> int:
    count = 0
    for entity in (message.entities or []) + (message.caption_entities or []):
        if entity.type in (MessageEntityType.MENTION, MessageEntityType.TEXT_MENTION):
            count += 1
    return count


def ad_keyword_score(text: str) -> int:
    normalized = text.lower()
    score = 0
    for keyword in AD_KEYWORDS:
        if keyword in normalized:
            if keyword in WHITELISTED_AD_KEYWORDS:
                continue
            blockers = WHITELISTED_KEYWORDS.get(keyword, [])
            if blockers:
                if any(blocker in normalized for blocker in blockers):
                    continue
            score += 1
    for pattern in TG_INVITE_PATTERNS:
        if pattern in normalized:
            score += 2
    return score


def domain_in_allowlist(domain: str, allowlist: set[str]) -> bool:
    domain = domain.lower()
    if domain in allowlist:
        return True
    labels = domain.split(".")
    for i in range(1, len(labels)):
        candidate = ".".join(labels[i:])
        if candidate in allowlist:
            return True
    for allowed in allowlist:
        if allowed.startswith("*.") and domain.endswith(allowed[1:]):
            return True
    return False
