# P1-7: Add Error Handling for Async Tasks

## Problem
- `asyncio.create_task()` used without error handling
- Exceptions in tasks silently disappear
- No visibility into async failures

## Solution
Create `_safe_task()` helper that wraps coroutines with error handling:

```python
def _safe_task(coro, name: str = "task"):
    """Create an asyncio task with error handling."""
    async def wrapper():
        try:
            return await coro
        except Exception as e:
            logger.error(f"Async task '{name}' failed: {e}")
    return asyncio.create_task(wrapper())
```

## Changes

### Before
```python
asyncio.create_task(self._finalize_turn())
```

### After
```python
_safe_task(self._finalize_turn(), "finalize_turn")
```

## Modified Locations
- `core/pipeline.py:178` - `_finalize_turn()` task
- `core/pipeline.py:297` - `send_metadata_start` task
- `core/pipeline.py:328,335` - `on_turn` callbacks

## Benefits
- All async errors are logged with context
- Task name helps identify which operation failed
- No silent failures

## Status
- [x] Completed
