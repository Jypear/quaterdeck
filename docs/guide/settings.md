# Settings

One settings page (Settings → General) covers instance-wide configuration:

- **Currency** — a single currency for the whole instance; there's no per-entry
  multi-currency support.
- **Budget window** — the view mode (weekly/monthly/yearly) and the period start day
  that the [budget engine](budget.md) normalises everything against.
- **Require login** — gates the entire app behind a session login when enabled. Leave it
  off for a private network/VPN deployment where the network boundary is the access
  control; turn it on if the instance is reachable more broadly.
- **AI provider** — provider (Anthropic / OpenAI / Ollama), API key, and model, powering
  the two on-demand [Notes AI features](notes.md#ai-features-optional-on-demand). The API
  key field never echoes the stored value — leave it blank when saving other settings and
  the existing key is kept; only fill it in when you're setting or changing it.
- **Inbound webhook signing secret** — shown here, with a regenerate button. External
  services POSTing to Quaterdeck's inbound webhook endpoint sign their payload with this
  secret.

## Webhooks

A separate page (Settings → Webhooks) manages **outbound** subscriptions: register an
endpoint URL and it receives signed `POST` requests whenever tasks, pots, notes, or
one-off outgoings change, plus a delivery log so you can see what was sent and whether it
succeeded. Each outbound endpoint has its own signing secret, separate from the inbound
one above.
