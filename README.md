# herdr-mod-usage

A small panel for the [Herdr](https://herdr.dev) desktop app that shows how much quota is left on
your Claude and Codex subscriptions: one bar per rate-limit window (5-hour, 7-day, per-model),
in each agent's colour. It sits in the sidebar, above the footer.

Both quota sources are undocumented and may change. macOS only (it reads the keychain).

## Install

```sh
git clone https://github.com/trapped/herdr-mod-usage ~/.config/herdr-app/mods/usage
cp ~/.config/herdr-app/mods/usage/usage.example.json ~/.config/herdr-app/usage.json   # then edit it
python3 ~/.config/herdr-app/mods/usage/sync.py
herdr-app do layout.switch '{"name":"main-mods"}'
```

The folder must be called `usage`.

## Accounts

`~/.config/herdr-app/usage.json` lists the accounts. Without it, the panel shows one Claude
account from `$CLAUDE_CONFIG_DIR` or `~/.claude`.

| Field | Meaning |
|---|---|
| `label` | the name on the row |
| `kind` | `claude` or `codex` |
| `dir` | Claude only: the config dir of that login (`CLAUDE_CONFIG_DIR`) |
| `home` | Codex only: the `CODEX_HOME` of that login |
| `on` | either provider: a herdr-core machine (`hc machine ls`) to read it on |
| `machine` | display name for the small grey machine heading (defaults to `on` or `local`) |
| `color` | optional bar colour; the default is the agent's brand colour |

Accounts are grouped by machine. The panel refreshes every 5 minutes. A bar turns red below 10% left and grey when its last read
failed (it keeps the last good value). Hover a row for the reset time.

## The layout

Herdr replaces its shipped `main` layout on every start and never updates copies of it. So
`sync.py` derives a layout instead: `layouts/main-mods.json` is Herdr's current `main` plus the
edit in every mod's `layout.json`. The mod runs `sync.py` on every start, so the layout follows
Herdr updates. If an edit no longer fits, it is skipped and the rest is still written.

## How quota is read

### Claude

Each config dir has its own login. Claude Code stores its OAuth token in the macOS keychain
under the service name `Claude Code-credentials-<first 8 hex of sha256(config dir path)>`, with
`Claude Code-credentials` as the fallback. The secret is JSON; the token is
`claudeAiOauth.accessToken`.

```sh
tok=$(security find-generic-password -s "$service" -w | jq -r .claudeAiOauth.accessToken)
curl -s https://api.anthropic.com/api/oauth/usage \
  -H "Authorization: Bearer $tok" -H "anthropic-beta: oauth-2025-04-20"
```

| Account type | Fields used |
|---|---|
| Subscription | `limits[]`: `percent` (used) and `resets_at`; `kind` is `session` (5-hour), `weekly_all` (7-day) or `weekly_scoped`, whose `scope.model.display_name` names the model. Older shape: `five_hour` and `seven_day` with `utilization` |
| Enterprise | those are empty; `extra_usage.utilization` is the percent of the monthly limit |

`fetch.py` reads the token and calls the endpoint in one process, so the token never appears on
a command line.

### Codex

`codex app-server` speaks JSON-RPC over stdio. Send `initialize`, then `initialized`, then
`account/rateLimits/read`, and read `rateLimits.primary` and `rateLimits.secondary` (either may
be null): `usedPercent`, `windowDurationMins`, `resetsAt` (unix seconds).

- It needs a ChatGPT login. With an API key it fails with "chatgpt authentication required to
  read rate limits".
- One login per `CODEX_HOME`.
With `on`, either provider is read on that machine through `hc exec -i --on <machine>`.
The reader source and account configuration travel through stdin; the remote machine needs
Python 3 and the provider's normal login, but does not need an installed copy of the mod.
Tokens stay on the machine that owns the login. An offline host produces an error for its
accounts without falling back to a different local login. Cached bars match the machine,
provider, login directory and label, so equal labels on different hosts cannot share stale data.
Requires a herdr-core version with `hc exec -i` support.

## Files

| File | What it does |
|---|---|
| `main.js` | the panel |
| `fetch.py` | reads every account and prints JSON |
| `layout.json` | where the panel goes in the window |
| `sync.py` | builds `layouts/main-mods.json` |
| `usage.example.json` | an example `usage.json` |
