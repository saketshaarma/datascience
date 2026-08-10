# Auth Testing Playbook

## Credentials
Admin: admin@infraforge.io / Admin@12345 (role admin)

## API
```
# login
curl -c cookies.txt -X POST $URL/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@infraforge.io","password":"Admin@12345"}'
# me (bearer or cookie)
curl -b cookies.txt $URL/api/auth/me
```
Login returns { user, access_token } and sets access_token + refresh_token cookies.
Protected routes (/api/instances, /api/stats, /api/terraform/*) return 401 without a token.
Frontend stores access_token in localStorage `if_token` and sends Authorization: Bearer.
Only admin can POST /api/auth/register and DELETE /api/auth/users/{id}.
Brute force: 5 failed logins per ip:email -> 15 min lockout (429).
