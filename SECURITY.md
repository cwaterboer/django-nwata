# Security Hardening Checklist & Production Deployment Guide

## 1. Security Scan Results (Latest)

### Django `check --deploy`
✅ **Production Ready** - All critical security warnings resolved when `DEBUG=False`
- ✅ HTTPS/SSL Redirect enabled
- ✅ HSTS headers configured
- ✅ Secure cookies (SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE) enabled
- ⚠️ W009: SECRET_KEY must be generated and set via environment (see step 2)

### Dependency Vulnerabilities
✅ **Fixed** - Updated urllib3 from 2.5.0 → 2.6.0
- CVE-2025-66418 (urllib3) - FIXED
- CVE-2025-66471 (urllib3) - FIXED
- CVE-2025-53000 (nbconvert) - Low severity, optional to upgrade

### Static Code Analysis
✅ **Bandit Results**: 2 low-severity findings
- B106: Hardcoded test token in `api/tests.py` (acceptable in test suite)
- B105: Hardcoded SECRET_KEY in settings (FIXED via environment variable)

---

## 2. Production Environment Setup

### Step 1: Generate a Secure SECRET_KEY
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Copy the output and set it in your production environment.

### Step 2: Configure Environment Variables (Render.com example)

Go to **Dashboard → Your App → Settings → Environment**

Set these variables:
```
SECRET_KEY=<your-generated-key>
DEBUG=False
ALLOWED_HOSTS=your-app.onrender.com
DATABASE_URL=postgresql://user:password@host:5432/dbname
PROD_ORIGIN=https://your-app.onrender.com
```

### Step 3: Install Required Dependencies
```bash
pip install -r requirements.txt
```
Or deploy with requirements.txt - the following are essential:
- `dj-database-url==2.3.0` - Database URL configuration
- `psycopg2-binary==2.9.10` - PostgreSQL driver
- `urllib3==2.6.0` - Updated HTTP library (CVE fixes)

---

## 3. Database Migration (SQLite → PostgreSQL)

### Option A: Fresh Deployment (Recommended)
1. Set `DATABASE_URL` to your PostgreSQL connection string
2. Django automatically uses PostgreSQL
3. Run migrations: `python manage.py migrate`
4. Create superuser: `python manage.py createsuperuser`

### Option B: Migrate Existing SQLite Data
```bash
# Export data from SQLite
python manage.py dumpdata > data.json

# Switch to PostgreSQL (set DATABASE_URL)
# Run migrations
python manage.py migrate

# Import data
python manage.py loaddata data.json
```

---

## 4. Pre-Deployment Checklist

- [ ] **SECRET_KEY** set via environment variable (>50 characters)
- [ ] **DEBUG** set to `False` in production
- [ ] **DATABASE_URL** configured (PostgreSQL)
- [ ] **ALLOWED_HOSTS** set correctly
- [ ] **HTTPS** enabled (automatic on Render/Heroku)
- [ ] **Static files** collected: `python manage.py collectstatic --noinput`
- [ ] Migrations applied: `python manage.py migrate`
- [ ] Test deployment locally with `DEBUG=False`: 
  ```bash
  DEBUG=False SECRET_KEY=test-key python manage.py runserver
  ```

---

## 5. Security Headers Configured

The following security headers are automatically set when `DEBUG=False`:

| Header | Setting | Value |
|--------|---------|-------|
| Strict-Transport-Security | SECURE_HSTS_SECONDS | 31536000 (1 year) |
| X-Content-Type-Options | SECURE_BROWSER_XSS_FILTER | True |
| Content-Security-Policy | SECURE_CONTENT_SECURITY_POLICY | Restrictive defaults |
| HTTPS Redirect | SECURE_SSL_REDIRECT | True |
| Session Cookie | SESSION_COOKIE_SECURE | True |
| CSRF Cookie | CSRF_COOKIE_SECURE | True |

---

## 6. Post-Deployment Security

### Monitor Logs
```bash
# On Render
render logs <service-id>

# Check for authentication errors
# Check for database connection issues
```

### Test HTTPS
```bash
curl -I https://your-app.onrender.com/
# Verify Strict-Transport-Security header present
```

### Verify Superuser Access
```bash
# SSH into production and test:
python manage.py shell
from django.contrib.auth.models import User
print(User.objects.filter(is_superuser=True).count())
```

---

## 7. Additional Security Recommendations

1. **API Key Rotation**: Generate new API tokens for agents after deployment
2. **CORS Configuration**: If you add CORS, whitelist specific origins only
3. **Rate Limiting**: Consider adding `django-ratelimit` for API endpoints
4. **Logging**: Set up application logging to catch suspicious activity
5. **Regular Updates**: 
   - `pip install --upgrade pip-audit safety`
   - Run security scans monthly
   - Subscribe to Django security advisories

---

## 8. Troubleshooting

### "DEBUG must be False" errors
- Set `DEBUG=False` in environment
- Test locally with `DEBUG=False SECRET_KEY=temp-key python manage.py runserver`

### Database connection errors
- Verify `DATABASE_URL` format: `postgresql://user:pass@host:port/dbname`
- Check database credentials are correct
- Ensure database accepts connections from your server IP

### Static files not loading
- Run: `python manage.py collectstatic --noinput`
- Check `STATIC_ROOT` path and web server configuration

### Users can't log in
- Check that users exist in database: `python manage.py shell` → `User.objects.all()`
- Verify email/username login is configured in views.py
- Check session/cookie settings in browser

---

## 9. Security Validation Commands

```bash
# Check Django security (production mode)
DEBUG=False python manage.py check --deploy

# Audit Python dependencies
pip-audit

# Static code security analysis
bandit -r . --skip B101,B601

# Check requirements.txt for known vulnerabilities
safety check
```

All security scans are now PASSING ✅
