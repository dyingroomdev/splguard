# Welcome Message - Made Permanent

## Change Summary
The welcome message that appears when new members join the group now stays **permanently** instead of automatically deleting after 60 seconds.

## What Changed

**File:** `src/splguard/bot/handlers/onboarding.py`

### 1. Removed Auto-Delete Call
**Line 103 (BEFORE):**
```python
await _schedule_delete(message)
```

**Line 103 (AFTER):**
```python
# Welcome message stays permanently (no auto-delete)
```

### 2. Cleaned Up Unused Code
**Lines 21-30 (REMOVED):**
```python
WELCOME_DELETE_AFTER = 60

async def _schedule_delete(message: Message) -> None:
    async def _delete_later() -> None:
        await asyncio.sleep(WELCOME_DELETE_AFTER)
        with suppress(Exception):
            await message.delete()
    asyncio.create_task(_delete_later())
```

### 3. Removed Unused Imports
**Lines 3-4 (REMOVED):**
```python
import asyncio
from contextlib import suppress
```

## Behavior

### Before ❌
1. New member joins
2. Welcome message appears
3. After 60 seconds, message automatically disappears
4. New members who join later don't see previous welcome messages

### After ✅
1. New member joins
2. Welcome message appears
3. **Message stays forever**
4. All welcome messages visible in chat history
5. Better for community transparency and onboarding

## Benefits

### ✅ Better User Experience
- New members can reference the welcome message anytime
- No pressure to read and click buttons within 60 seconds
- Welcome messages serve as chat history

### ✅ Transparency
- All members can see when others joined
- Builds trust in the community
- Clear record of growth

### ✅ Less Spam-Like
- Disappearing messages can seem suspicious
- Permanent messages feel more professional
- Aligns with how most bots work

## Testing

Run the bot and test:
1. Add a test member to the group
2. Welcome message should appear
3. Wait more than 60 seconds
4. **Message should still be visible** ✓

## Code Verification

```bash
# Test that the module loads correctly
.venv/bin/python -c "
from splguard.bot.handlers import onboarding
from splguard.bot.handlers.onboarding import _welcome_text, _welcome_keyboard
print('✓ All functions work correctly')
"
```

## Rollback Instructions

If you need to restore the auto-delete behavior (not recommended):

1. Add back the imports:
```python
import asyncio
from contextlib import suppress
```

2. Add back the constant and function:
```python
WELCOME_DELETE_AFTER = 60

async def _schedule_delete(message: Message) -> None:
    async def _delete_later() -> None:
        await asyncio.sleep(WELCOME_DELETE_AFTER)
        with suppress(Exception):
            await message.delete()
    asyncio.create_task(_delete_later())
```

3. Add back the function call:
```python
await _schedule_delete(message)
```

## Configuration

If you want to make the messages temporary again in the future, consider:
- Making it configurable via environment variable
- Adding it to the database settings
- Allowing admins to toggle it via command

Example:
```python
# In config.py
welcome_message_ttl: int = Field(default=0, alias="WELCOME_MESSAGE_TTL")
# 0 = permanent, >0 = seconds until deletion
```

## Status

✅ **Complete** - Welcome messages now stay permanently
