# @growth-model/sdk (JavaScript / TypeScript)

```ts
import { createClient } from "@growth-model/sdk";

const gm = createClient({ apiKey: "gm_pub_...", baseUrl: "https://growth.example.com" });
gm.active(user.id, { platform: "web", app_version: "2.4.1" });
```

Zero dependencies; works in browsers, Node ≥ 18, React Native, Deno, Bun and edge runtimes.
Batched, deduplicated per user per UTC day, flushed on `pagehide`, and never throws.
Publishable (`gm_pub_`) keys can only ingest, so they are safe to ship in client bundles.
