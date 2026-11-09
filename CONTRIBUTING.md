# Contributing

1. Install [uv](https://docs.astral.sh/uv/), Node 22 and (optionally) [just](https://just.systems).
2. `just setup` then `just check`. CI runs exactly the same checks.
3. Read [AGENTS.md](AGENTS.md) for layout and rules (it applies to humans too) and
   [docs/model.md](docs/model.md) before touching model semantics.
4. Record significant design decisions as an ADR in `docs/adr/`.
5. Keep PRs focused; describe how you verified the change.
