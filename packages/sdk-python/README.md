# growth-model-sdk (Python)

```python
import growth_model_sdk as gm

gm.init(api_key="gm_pub_...", base_url="https://growth.example.com")  # or GROWTH_MODEL_API_KEY / GROWTH_MODEL_URL
gm.active("user-123", metadata={"platform": "ios", "app_version": "2.4.1"})
```

Non-blocking (background thread), batched, retried, deduplicated per user per UTC day, and never
raises into your code. Call `gm.flush()` before exiting short-lived scripts. Use a publishable
(`gm_pub_`) key: it can only ingest.
