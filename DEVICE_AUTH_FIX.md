# Device Auth Alignment Fix

## Issue
When testing device registration with the local agent (`nwata_min.py`), both admin and user accounts failed with:
```
[AUTH ERROR] Registration failed: 'org'
Failed to authenticate device. Exiting.
```

## Root Cause
**Key mismatch between server and agent:**
- **Django API** (`api/views.py` DeviceRegister): Returns response with `"organization"` key
- **Local Agent** (`nwata_min.py` DeviceAuth): Expected response with `"org"` key

When agent tried to access `data["org"]`, it got a `KeyError` because the key was actually `data["organization"]`.

## Server Response (Correct)
```json
{
  "token": "...",
  "token_expires_at": "2026-02-03T09:12:58.264604+00:00",
  "user": {
    "email": "admin@nwata.local",
    "id": 3
  },
  "organization": {
    "id": 1,
    "subdomain": "default",
    "name": "Default Org"
  }
}
```

## Fix Applied
Updated two methods in `nwata_min.py`:

### 1. `register_device()` (lines 115-131)
**Before:**
```python
"org": data["org"]  # ❌ KeyError
```

**After:**
```python
"organization": data["organization"]  # ✅ Correct
```

### 2. `refresh_token()` (lines 133-150)
**Before:**
```python
"org": self.token_data.get("org")  # ❌ Would fetch None
```

**After:**
```python
"organization": data.get("organization", self.token_data.get("organization"))  # ✅ Correct
```

## Verification Results
✅ **Device registration test 1** (admin): Success  
✅ **Device registration test 2** (user): Success  
✅ **Activity ingest with admin token**: 1 log processed  
✅ **Activity ingest with user token**: 1 log processed  

Both users can now successfully:
1. Register device with email/password
2. Receive valid auth token
3. Ingest activity logs tagged to their organization

## Alignment Summary

| Component | Endpoint | Response Field | Agent Access | Status |
|-----------|----------|-----------------|---------------|--------|
| DeviceRegister | `/api/device/register/` | `"organization"` | `data["organization"]` | ✅ Aligned |
| DeviceAuth | `/api/device/auth/` | `"organization"` | `data.get("organization", ...)` | ✅ Aligned |
| ActivityIngest | `/api/activity/` | (token in header) | `Bearer {token}` | ✅ Aligned |
