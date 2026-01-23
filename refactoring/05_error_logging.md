# P1-5: Add Error Logging to Empty Catch Blocks

## Problem
- Empty catch blocks silently swallow errors
- Makes debugging difficult when issues occur
- `stasis_app/app.js` had multiple `catch (e) { // Ignore }` patterns

## Solution
Add appropriate logging to catch blocks:
- Use `console.debug()` for expected errors (cleanup after call end)
- Filter out expected "not found" errors to reduce noise
- Provide context in log messages

## Changes

### Before
```javascript
} catch (e) {
    // Ignore cleanup errors
}
```

### After
```javascript
} catch (e) {
    if (!e.message?.includes('not found')) {
        console.debug(`[DEBUG] External channel cleanup: ${e.message}`);
    }
}
```

## Modified Files
- `stasis_app/app.js` - 4 catch blocks updated

## Logging Levels Used
| Level | Use Case |
|-------|----------|
| `console.error` | Fatal errors, setup failures |
| `console.warn` | Unexpected but recoverable errors |
| `console.debug` | Expected errors during cleanup/shutdown |
| `console.log` | Normal operation info |

## Status
- [x] Completed
