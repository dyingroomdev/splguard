from __future__ import annotations

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "help.intro": (
            "Need help? Our support team is here to assist you!\n\n"
            "Available commands:\n"
            "/team - view the core contributors\n"
            "/contract - display token details\n"
            "/presale - presale status and information\n"
            "/links - official resources\n\n"
            "For direct support, contact our support bot below."
        ),
        "start.intro": (
            "Welcome to SPL Shield\\! Choose an option below to learn more about the project."
        ),
        "team.title": "Team",
        "team.no_data": "Team details are not available yet.",
        "contract.title": "Token Contract",
        "contract.no_data": "No contract information is available.",
        "presale.title": "Presale",
        "presale.no_data": "No presale information has been published.",
        "links.title": "Official Links",
        "links.no_data": "No official links are currently configured.",
        "status.upcoming": "Upcoming",
        "status.active": "Active",
        "status.ended": "Ended",
        "error.generic": "Something went wrong. Please try again later.",
    }
}


def gettext(key: str, locale: str = "en") -> str:
    translations = _TRANSLATIONS.get(locale, {})
    return translations.get(key) or _TRANSLATIONS["en"].get(key, key)
