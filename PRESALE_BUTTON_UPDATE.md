# Presale Button - Information Added

## Summary

Added detailed presale information to the **💰 Presale** button callback. When users click the Presale button in the welcome message, they will see complete presale details.

## Changes Made

### Updated Presale Button Callback ✅

**File:** `src/splguard/bot/handlers/onboarding.py`
**Function:** `_send_presale_block()` (lines 178-214)

### Presale Information Display

When users click the **💰 Presale** button, they see:

```
🛡️ SPL Shield Presale

💰 Presale Details
📅 Start: 6 PM UTC (00+), 26th Oct 2025
💵 Price: $0.002 per TDL
📊 Supply: 1B TDL

Join early to secure your position before the whitelist ends!
```

## How It Works

### Smart Fallback Logic:

1. **Database Check** - Bot first checks if presale info exists in database
2. **Use Database** - If found, displays info from database (customizable)
3. **Use Default** - If not found, displays hardcoded presale details above
4. **Always Works** - Users always get presale info, even with empty database

### Code Implementation:

```python
async def _send_presale_block(callback, session, redis):
    # Try database first
    summary = await presale_service.get_summary(refresh_external=False)
    
    if summary is not None:
        # Use database info
        text = render_presale_block(...)
    else:
        # Use default hardcoded info
        text = "🛡️ SPL Shield Presale\n..."
    
    await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN_V2)
```

## Presale Details

### 📅 Start Time
- **Date:** October 26, 2025
- **Time:** 6 PM UTC (00+)
- **Timezone:** Universal Coordinated Time (UTC+0)

### 💵 Price
- **Cost:** $0.002 per TDL token
- **Token Symbol:** TDL
- **Entry Point:** Early investor pricing

### 📊 Supply
- **Total Supply:** 1 Billion (1B) TDL tokens
- **Transparency:** Clear supply cap stated upfront

### 🎯 Call to Action
- "Join early to secure your position before the whitelist ends!"
- Creates urgency
- Encourages participation

## User Experience

### Welcome Message Flow:

1. **New member joins group**
2. **Sees welcome message** with 8 buttons
3. **Clicks 💰 Presale button**
4. **Instantly sees** complete presale details
5. **No need to ask** "when presale?" or "what price?"

### Benefits:

✅ **Instant Information** - No waiting, no asking
✅ **Always Available** - Works even without database
✅ **Clear Details** - Start time, price, supply in one place
✅ **Professional** - Well-formatted, easy to read
✅ **Reduces Questions** - Common questions answered immediately

## Testing Results

```
✓ Presale text generated: 192 characters
✓ All special characters escaped correctly
✓ Markdown formatting working
✓ Bot loads successfully
✓ Database fallback working
✅ Ready for production!
```

### Preview:

```
When user clicks Presale button:
┌──────────────────────────────────────┐
│ 🛡️ SPL Shield Presale               │
│                                      │
│ 💰 Presale Details                  │
│ 📅 Start: 6 PM UTC, 26th Oct 2025   │
│ 💵 Price: $0.002 per TDL            │
│ 📊 Supply: 1B TDL                   │
│                                      │
│ Join early to secure your position  │
│ before the whitelist ends!          │
└──────────────────────────────────────┘
```

## Comparison

### Before ❌
- Clicking Presale button → "Presale information is not available."
- Users confused about presale details
- Many questions in chat

### After ✅
- Clicking Presale button → Complete presale details
- Users informed immediately
- Questions answered proactively

## Technical Details

### Formatting:
- **Bold headers:** "🛡️ SPL Shield Presale", "💰 Presale Details"
- **Emoji icons:** Visual clarity for each detail
- **Escaped characters:** All special chars properly escaped
- **Parse mode:** MarkdownV2 for rich formatting

### Characters Used:
- Total: 192 characters (well within Telegram limit)
- Efficient and concise
- Easy to read on mobile

## Future Updates

### To Change Presale Details:

1. Open: `src/splguard/bot/handlers/onboarding.py`
2. Find: `_send_presale_block()` function
3. Update: Lines 208-210 (date, price, supply)
4. Save and restart bot

### Example Update:

```python
# Update start date
f"{md.escape_md('📅 Start:')} {md.escape_md('6 PM UTC (00+), 27th Oct 2025')}",

# Update price
f"{md.escape_md('💵 Price:')} {md.escape_md('$0.003 per TDL')}",

# Update supply
f"{md.escape_md('📊 Supply:')} {md.escape_md('500M TDL')}",
```

## Deployment

Restart the bot to apply changes:

```bash
# Local
.venv/bin/splguard-bot

# Docker
docker-compose restart bot
```

## Status

✅ **Complete** - Presale information added to button callback!

### What Users Get:
1. ✅ Presale start: 6 PM UTC, 26th Oct 2025
2. ✅ Price: $0.002 per TDL
3. ✅ Supply: 1B TDL
4. ✅ Call to action
5. ✅ Professional formatting
6. ✅ Works without database config

---

**Ready for production!** Users can now click the Presale button to see all details instantly. 🚀
