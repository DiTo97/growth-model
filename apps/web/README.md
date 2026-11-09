# Web console

Static, build-free console (Supabase magic-link auth → API with the Supabase JWT).

```bash
cp config.example.js config.js   # fill in apiBaseUrl + Supabase project URL / anon key
python -m http.server 5173       # then open http://localhost:5173
```

The API must allow the console origin (`CORS_ORIGINS=http://localhost:5173`) and know
how to verify Supabase tokens (`SUPABASE_URL` for JWKS, or legacy `SUPABASE_JWT_SECRET`).
Map Supabase users to tenants with `POST /v1/admin/members`.
