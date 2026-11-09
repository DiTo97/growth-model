// Growth Model console. Auth: Supabase magic link; the Supabase access token is sent to the API,
// which maps the user (JWT `sub`) to a tenant via the `members` table.
const cfg = window.GROWTH_MODEL_CONFIG || {};
const $ = (id) => document.getElementById(id);
const status = (msg) => ($("status").textContent = msg || "");
const supabase =
  cfg.supabaseUrl && cfg.supabaseAnonKey ? window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnonKey) : null;

const RATES = ["nurr", "curr", "rurr", "surr", "iwaurr", "wau_loss", "reactivation", "mau_loss", "resurrection"];
let token = null;
let fitted = null;

async function api(path, body) {
  const res = await fetch(`${cfg.apiBaseUrl}${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      ...(cfg.tenant ? { "x-tenant": cfg.tenant } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

function cell(tag, text, cls) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (cls) el.className = cls;
  return el;
}

function table(el, header, rows) {
  el.replaceChildren();
  const tr = el.insertRow();
  header.forEach((h) => tr.appendChild(cell("th", h)));
  rows.forEach((r) => {
    const row = el.insertRow();
    r.forEach((v) => row.appendChild(cell("td", v)));
  });
}

function drawChart(series) {
  const svg = $("chart");
  svg.replaceChildren();
  if (!series.length) return;
  const max = Math.max(...series.map((d) => d.mau)) || 1;
  const x = (i) => (i / Math.max(1, series.length - 1)) * 800;
  const y = (v) => 230 - (v / max) * 220;
  for (const key of ["mau", "wau", "dau"]) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    path.setAttribute("points", series.map((d, i) => `${x(i)},${y(d[key])}`).join(" "));
    path.setAttribute("class", key);
    svg.appendChild(path);
  }
}

async function load() {
  status("Loading…");
  try {
    const metrics = await api("/v1/metrics");
    drawChart(metrics);
    fitted = await api("/v1/rates").catch(() => null);
    if (fitted) {
      $("asof").textContent = `as of ${fitted.as_of} (${fitted.window_days}-day window)`;
      table($("rates"), ["rate", "value"], Object.entries(fitted.rates).map(([k, v]) => [k, v.toFixed(4)]));
      $("overrides").replaceChildren(
        ...RATES.map((r) => {
          const label = cell("label", `${r} `);
          const input = document.createElement("input");
          Object.assign(input, { name: r, type: "number", step: "any", min: "0", max: "1", value: fitted.rates[r].toFixed(4) });
          label.appendChild(input);
          return label;
        }),
      );
    }
    status(metrics.length ? "" : "No data yet — ingest events and run the segments job.");
  } catch (e) {
    status(String(e));
  }
}

$("sim").onsubmit = async (ev) => {
  ev.preventDefault();
  const form = new FormData(ev.target);
  const overrides = {};
  for (const r of RATES) {
    const v = Number(form.get(r));
    if (fitted && Math.abs(v - fitted.rates[r]) > 1e-9) overrides[r] = v;
  }
  const horizon_days = Number(form.get("horizon"));
  try {
    const [base, scen] = await Promise.all([
      api("/v1/simulations", { horizon_days }),
      api("/v1/simulations", { horizon_days, overrides }),
    ]);
    const b = base.trajectory.at(-1).dau;
    const s = scen.trajectory.at(-1).dau;
    $("simresult").textContent = `Day ${horizon_days} DAU: ${s.toFixed(0)} vs baseline ${b.toFixed(0)} (${(((s / b) - 1) * 100).toFixed(1)}%)`;
  } catch (e) {
    status(String(e));
  }
};

$("levers").onclick = async () => {
  status("Running lever analysis…");
  try {
    const { results } = await api("/v1/levers", {});
    table(
      $("levertable"),
      ["lever", "direction", "DAU impact"],
      results.map((r) => [r.lever, r.direction, `${(r.dau_impact * 100).toFixed(1)}%`]),
    );
    status("");
  } catch (e) {
    status(String(e));
  }
};

async function init() {
  if (!supabase) {
    // Local development without Supabase: use a secret key from config.js (never do this in production).
    token = cfg.devApiKey || null;
    $("who").textContent = token ? "dev key" : "Configure config.js";
    if (token) load();
    return;
  }
  const { data } = await supabase.auth.getSession();
  const apply = (session) => {
    token = session?.access_token ?? null;
    $("login").hidden = Boolean(token);
    $("logout").hidden = !token;
    $("who").textContent = session?.user?.email ?? "";
    if (token) load();
  };
  apply(data.session);
  supabase.auth.onAuthStateChange((_e, session) => apply(session));
  $("login").onsubmit = async (ev) => {
    ev.preventDefault();
    const { error } = await supabase.auth.signInWithOtp({
      email: $("email").value,
      options: { emailRedirectTo: location.href },
    });
    status(error ? error.message : "Check your inbox for the magic link.");
  };
  $("logout").onclick = () => supabase.auth.signOut();
}

init();
