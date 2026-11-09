// Copy to config.js (git-ignored) and fill in.
window.GROWTH_MODEL_CONFIG = {
  apiBaseUrl: "http://localhost:8000",
  supabaseUrl: "", // e.g. https://xyzcompany.supabase.co
  supabaseAnonKey: "",
  tenant: "", // "company/product" — only needed if the user belongs to several tenants
  devApiKey: "", // local dev only, when Supabase is not configured: a gm_sk_ key
};
