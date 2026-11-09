# ADR 0002 — Tenant is derived from the credential

**Status:** accepted

**Context.** The first scaffold accepted `company_id` as a request parameter and returned data for
any company to any valid key, a cross-tenant data leak. SDK keys also had full read access although
they ship inside client apps.

**Decision.** Every key is bound to one `(company_id, product_id)` and has a kind: publishable
(ingest only) or secret (read and jobs). Endpoints never accept tenant identifiers. Keys are stored hashed.

**Consequences.** The SDK payload no longer carries tenant fields. Analysing several products together
needs one key per product, or a future org-level key.
