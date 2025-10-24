# Bug Fix: MarkdownV2 Character Escaping

## Issue Identified
When the bot received new member events, it was crashing with the following error:
```
TelegramBadRequest: Telegram server says - Bad Request: can't parse entities: 
Character '!' is reserved and must be escaped with the preceding '\'
```

## Root Cause
In `src/splguard/bot/handlers/onboarding.py`, the `_welcome_text()` function was generating messages with unescaped special characters that are reserved in Telegram's MarkdownV2 format.

**Problem lines (56-65):**
```python
f"👋 Welcome to {md.bold('SPL Shield')}, {md.escape_md(greeting_name)}!",  # Unescaped !
"",
"We are building the first AI powered Solana risk scanner 🛡️",  # Contains special chars
"",
md.bold("Quick actions"),
"💰 Presale · join while spots remain",  # Unescaped ·
"🧾 Contract · verify before you trade",  # Unescaped ·
"🌐 Links · stay on official channels",  # Unescaped ·
"",
"Please avoid unsolicited links or ads — spam gets removed instantly.",  # Unescaped — and .
```

## MarkdownV2 Special Characters
In Telegram's MarkdownV2 format, these characters must be escaped with `\`:
```
_ * [ ] ( ) ~ ` > # + - = | { } . !
```

## Solution Applied
Wrapped all plain text strings in `md.escape_md()` to properly escape special characters:

```python
def _welcome_text(username: str | None) -> str:
    greeting_name = username or "friend"
    return md.join_lines(
        [
            f"👋 Welcome to {md.bold('SPL Shield')}, {md.escape_md(greeting_name)}{md.escape_md('!')}",
            "",
            md.escape_md("We are building the first AI powered Solana risk scanner 🛡️"),
            "",
            md.bold("Quick actions"),
            md.escape_md("💰 Presale · join while spots remain"),
            md.escape_md("🧾 Contract · verify before you trade"),
            md.escape_md("🌐 Links · stay on official channels"),
            "",
            md.escape_md("Please avoid unsolicited links or ads — spam gets removed instantly."),
        ]
    )
```

## Files Modified
- `src/splguard/bot/handlers/onboarding.py` - Lines 52-67

## Testing Performed
1. ✅ Welcome text generation with various usernames
2. ✅ Bot startup test (no errors)
3. ✅ Verified other handlers use proper escaping
4. ✅ Template files already properly escaped

## Prevention
The codebase has a utility module `src/splguard/utils/markdown.py` that provides:
- `escape_md(text)` - Escapes all special characters
- `bold(text)` - Bold text (auto-escapes)
- `italic(text)` - Italic text (auto-escapes)
- `link(label, url)` - Hyperlink (auto-escapes)
- `inline_code(text)` - Code blocks (auto-escapes)

**Best Practice:** Always use these utilities when building messages with `ParseMode.MARKDOWN_V2`.

## Impact
- **Before:** Bot crashed when new members joined groups
- **After:** Welcome messages sent successfully with proper formatting

## Related Issues
No similar issues found in other handlers:
- `src/splguard/bot/handlers/info.py` - ✅ Properly escaped
- `src/splguard/bot/handlers/admin.py` - ✅ Properly escaped
- `src/splguard/templates/messages.py` - ✅ Properly escaped
