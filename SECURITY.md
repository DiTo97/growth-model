# Security

Please report vulnerabilities privately through GitHub Security Advisories
("Report a vulnerability" on the repository's Security tab) instead of public issues.

Security model in brief:
- API keys are stored as SHA-256 hashes; raw keys are shown once at creation.
- Publishable keys (`gm_pub_`) can only ingest; secret keys (`gm_sk_`) read one tenant.
- The tenant is always derived from the credential, never from request input.
- Admin endpoints are disabled unless `GROWTH_MODEL_ADMIN_TOKEN` is set.
