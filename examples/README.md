# Usage-tracking examples

Working configuration built on the fork's usage telemetry — the
`llmvision_token_usage` / `llmvision_call_error` events (schema 2 / 1, fork
>= 1.7.1.2) and the native per-provider sensors (fork >= 1.7.1.3). See the
[Token Usage Events](../README.md#token-usage-events) section of the main
README for the event payloads and the sensors-vs-events layering.

These files are the **user-side pricing and analytics layer** that the
integration deliberately does not ship: providers don't report pricing in
their API responses, and rates change too often to hardcode — so the
integration emits normalized token counts, and pricing lives here, where
rates can be kept current.

| File | Install location | What it does |
|---|---|---|
| [`llmvision_token_usage.yaml`](llmvision_token_usage.yaml) | `/config/packages/` | Trigger-based template sensors over the events: global token/call totals, an error counter, and a per-event **cost ledger** that stamps each call with the rates in effect at that moment (frozen history — changing a rate never reprices the past). Plus optional daily/monthly utility meters. |
| [`llmvision_rates.jinja`](llmvision_rates.jinja) | `/config/custom_templates/` | The per-model rate table the ledger prices from. **Longest-prefix matching**, because providers report dated model ids (`claude-haiku-4-5-20251001`) that bill at the base model's rate. Unknown models price at fallback helper rates and flag `rate_source: fallback` so an automation can alert. |
| [`influxdb-llmvision-snippet.yaml`](influxdb-llmvision-snippet.yaml) | merge into your `influxdb:` config | Sends the ledger rows to InfluxDB with provider/model/service/camera/finish-reason as **tags** (Grafana `GROUP BY` dimensions), in a dedicated `llm_vision` measurement. |

Requires two `input_number` helpers for the fallback rates
(`llm_vision_rate_input_per_mtok` / `llm_vision_rate_output_per_mtok`), and
`homeassistant.packages` enabled in `configuration.yaml`. After editing:
packages reload via *Developer Tools → YAML → Template entities*; the Jinja
file via the `homeassistant.reload_custom_templates` service (its own
service — easy to miss); the influx filter via a reload of the InfluxDB
config entry.

Each layer is optional and independent: the package works without InfluxDB,
the native sensors work without any of this, and everything here consumes
only the public events — no integration internals.
