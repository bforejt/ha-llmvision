# Token Usage Event v2 — payload design (fork v1.7.1.2)

Design for extending the `llmvision_token_usage` event and adding a companion
error event. Grounded in the 2026-08-17 research pass (5 agents over the fork
code, the live HA system, and OTel GenAI / LangFuse conventions); every capture
point below was verified in-reach with file:line evidence before being included.

Scope: **fork release v1.7.1.2 only.** Outcome chaining (cost-per-ALERT,
timeline uid joins, structured_parse_ok) is Phase 2 and deliberately absent —
it requires restructuring when events fire relative to response parsing.

---

## Design principles (carried from v1, plus two new)

1. **The event measures; the package prices.** No rates, no cost in the event.
2. **Normalize at the source.** Provider-specific shapes (finish reasons,
   response ids) are normalized in the fork with tested helpers, mirroring
   `extract_token_usage`.
3. **Purely additive.** Every v1 field keeps its exact meaning. `service:
   "validate"` is retained even though `request_type` supersedes it —
   consumers built against v1 must not break.
4. **NEW — durability rule:** anything wanted in a 6-month report must be in
   the event payload (→ InfluxDB, permanent). Recorder joins die at ~10 days,
   `events.db` at retention_time. Query-time joins are for dimensions already
   flowing to Influx as their own series (presence, vacation, weather).
5. **NEW — cardinality rule:** payload fields destined to become Influx tags
   must be bounded sets (cameras, request types, finish reasons). Unbounded
   values (ids, paths, hashes) stay fields. The package decides tag vs field;
   the fork just emits.

---

## Event: `llmvision_token_usage` — v2 payload

Existing v1 fields (unchanged semantics): `provider`, `config_entry_id`,
`model`, `service`, `input_tokens`, `output_tokens`, `total_tokens`,
`cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`.

### New fields

| Field | Type | Values / shape | Capture point |
|---|---|---|---|
| `schema` | int | `2` | constant |
| `request_type` | str | `vision` \| `title` \| `validate` | `vision_request` / `title_request` / `validate()` |
| `source` | str\|null | camera entity_id, or path stem for file-based calls | `_adopt_usage_attribution` |
| `source_kind` | str | `entity` \| `path` \| `frigate_event` \| `none` | " |
| `media` | str\|null | first raw input as given (entity/path) — debug/join aid | " |
| `frigate_event_id` | str\|null | first `event_id` when the call analyzes a Frigate event | " |
| `target_entity` | str\|null | `sensor_entity` — the entity a data_analyzer call writes | " |
| `frame_count` | int\|null | `len(call.base64_images)`; **0 for title requests** | " (see hazards) |
| `target_width` | int\|null | requested downscale width | " |
| `request_max_tokens` | int\|null | requested output cap (OTel `gen_ai.request.max_tokens`); title rows show the 4096 override | " |
| `prompt_hash` | str\|null | `sha256(message)[:12]`; **vision/data rows only, null on title** | " (see hazards) |
| `prompt_chars` | int\|null | message length; same capture rule as hash | " |
| `use_memory` | bool | memory feature engaged (token-variance explainer) | " |
| `generate_title` | bool | on vision rows: a title call will follow | " |
| `response_format` | str\|null | `text` \| `json`; null on validate rows (no service call) | " |
| `latency_ms` | int\|null | wall-clock around the HTTP call, request→body parsed | `_post` / `invoke_bedrock` |
| `finish_reason` | str\|null | normalized: `stop` \| `length` \| `tool_use` \| `safety` \| `other` | `_fire_usage_event` via new helper |
| `response_id` | str\|null | provider's response id from the body | " |
| `fallback_from` | str\|null | original provider name when served by the fallback | `Request.call` → call attr |

### Source resolution (the device dimension)

Resolution order, first match wins:

1. `image_entities[0]` → `source_kind: entity`, `source` = entity_id
2. `image_paths[0]` → `source_kind: path`, `source` = **basename stem**
   (no directory, no extension — `/config/www/blink/front_door_current.jpg`
   → `front_door_current`)
3. `video_paths[0]` → `source_kind: path`, stem
4. `event_id[0]` → `source_kind: frigate_event`, `source: null`,
   `frigate_event_id` = the id (unbounded → never a tag)
5. none → `source_kind: none`, `source: null` (validate, pure-text data calls)

Rationale, from the live-traffic finding that would have sunk a naive design:
the **highest-volume caller passes file paths, not entities** (Blink
automation, 7 cameras; also garage_close_gate). Path stems are stable and
bounded per caller, so they work as tags. The fork does **not** prettify
stems (no `_current`-stripping — that is Blink-specific convention); the
package or Grafana can alias display names. Multi-source calls: first entry
wins for `source`; real traffic today has exactly one distinct source per
call, and `media` preserves the raw value.

### Normalized finish reasons (new helper, mirrors `extract_token_usage`)

| Provider | Raw location | → normalized |
|---|---|---|
| Anthropic | `stop_reason`: end_turn/max_tokens/tool_use | stop / length / tool_use |
| OpenAI-compat | `choices[0].finish_reason`: stop/length/tool_calls/content_filter | stop / length / tool_use / safety |
| Google | `candidates[0].finishReason`: STOP/MAX_TOKENS/SAFETY | stop / length / safety |
| Bedrock | `stopReason`: end_turn/max_tokens/tool_use | stop / length / tool_use |
| Ollama | `done_reason`: stop/length | stop / length |

Anything unrecognized → `other`; absent → `null`. `length` is the actionable
value: output truncated at `request_max_tokens`.

Response ids: Anthropic `id`, OpenAI `id`, Google `responseId`, Bedrock
`ResponseMetadata.RequestId` (boto3 path). Absent → null. All are already in
the response body handed to `_fire_usage_event` — no header plumbing needed.

---

## New event: `llmvision_call_error`

A **separate event type**, not a status field on the usage event. Rationale:
the usage event's contract is "a billed call happened; here are its tokens."
Zero-token error rows inside it would corrupt the accumulator, the call
counter, and every existing consumer's semantics. Errors get their own stream;
the package gets an error counter next to the call counter. (This also
delivers, fork-side, what upstream ideas #306/#356 ask for.)

| Field | Notes |
|---|---|
| `schema` | 1 |
| `provider`, `config_entry_id`, `model`, `service`, `request_type`, `source`, `source_kind`, `fallback_from` | same semantics as the usage event |
| `status_code` | HTTP status, or null for transport exceptions |
| `error_type` | normalized: `auth` (401/403) \| `not_found` (404) \| `bad_request` (400) \| `rate_limit` (429) \| `overloaded` (529) \| `server` (5xx) \| `network` (transport exceptions incl. timeout and failed body reads) \| `other` (any other status, e.g. 402; also a boto3 ClientError without a usable status) |
| `latency_ms` | time to failure |

Fired from `_post`'s two failure paths (non-200 → before the
ServiceValidationError raise; request-exception catch) and the Bedrock
equivalents. **No token counts** (unknown on failure), **no message content**
(size/privacy), **no response body excerpt** (may contain provider error text
with request fragments). Same best-effort try/except wrapper as the usage
event — telemetry can never break a request.

Scope note: provider-level post-parse failures (`invalid_response`,
`empty_response` in `_make_request`) are NOT covered in v1.7.1.2 — the HTTP
call succeeded and billed, so a usage event already fired; classifying the
parse failure belongs to Phase 2 alongside `structured_parse_ok`.

### What error events + context_id make visible

Automation-level retries (3 live callers re-bill up to 3× on empty structured
responses — live data shows identical 1188/57 pairs 30-80s apart) are separate
service calls sharing a parent context. The fork cannot number them. The
package therefore stores **`context_id`** (the event's own context id — the
service-call run) alongside the existing `context_parent`:
`count(distinct context_id) GROUP BY context_parent` = attempts per automation
run. Retry visibility needs no fork field beyond what v2 already carries.

---

## Capture mechanics (implementation map)

| Code site | Change |
|---|---|
| `_adopt_usage_attribution` | Extend to capture the source bundle, request params, flags, prompt hash/chars, `request_type='vision'`. All from the `call` object it already receives. |
| `title_request` | After adopting: override `request_type='title'`, `frame_count=0`, `prompt_hash=None`, `prompt_chars=None`. Captured AFTER the existing `max_tokens=4096` overwrite so the row shows the real cap. |
| `validate()` (6 methods) | Existing one-line pattern gains `request_type='validate'`; `service='validate'` retained for v1 compat. |
| `Request.call` | Before each fallback recursion (vision-failure path providers.py:336-345; title-failure path 394-404): `call._fallback_of = <original provider name>`. `_adopt` reads it via getattr. |
| `_post` | `perf_counter()` around post→json; fire `llmvision_call_error` on both failure paths; pass latency into `_fire_usage_event`. |
| `invoke_bedrock` | Same wall-clock timing, started AT the converse call (client construction excluded). **boto3 raises `ClientError` for every non-2xx** — it never returns an error-status dict — so classification reads the exception's `ResponseMetadata.HTTPStatusCode`; the dict-status branch is defensive only. `metrics.latencyMs` stays a debug log. |
| `_fire_usage_event` | Emit new fields; call new `extract_finish_reason()` / `extract_response_id()` helpers. |
| `const.py` | `EVENT_CALL_ERROR = "llmvision_call_error"`. |

### Known hazards, designed around

- **Title mutates the prompt** (providers.py:386-390 overwrites `call.message`
  with title_prompt + full response text before `title_request` re-adopts). A
  naive hash would be unique per title call. Hence: hash captured at
  vision-adopt, title rows carry null. A regression test pins this.
- **`camera_entity` is a false lead** — populated only by the `create_event`
  service (no LLM call). Source identity comes from the resolution chain
  above; `camera_entity` must not appear in the implementation.
- **`frame_count` at title time** — `call.base64_images` is still attached
  from the vision request; without the title override the title row would
  falsely claim frames were sent.
- **Multiple events per context** — vision + title + fallbacks share one
  context. Consumers aggregate per `context_id`, never assume 1:1.

---

## Package / InfluxDB follow-on (separate change, after fork release)

- Ledger sensor: map event fields to attributes with the established `llm_`
  prefix where they become tags — `llm_source`, `llm_request_type`,
  `llm_finish_reason` (all bounded) → add to `tags_attributes`.
  `latency_ms`, `response_id`, `media`, `prompt_hash`, `frame_count`,
  `context_id` → attributes that stay Influx fields.
- New error counter sensor (trigger: `llmvision_call_error`) +
  `sensor.llm_vision_api_calls` semantics unchanged (billed successes only).
- Error-rate alert automation (supersedes the rejected rate-limit-headroom
  idea: a 429 shows up as `error_type: rate_limit` the moment it matters).
- Unknown-model pricing alert continues to work unchanged.

## Upstream (#714) implications

Propose for the upstream schema: `source`, `request_type`, `latency_ms`,
`finish_reason`, `response_id`, `schema`. `fallback_from` is upstream-relevant
(it's their fallback feature). The error event maps to their open ideas
#306/#356 and should be raised as its own suggestion. Fork-only until then:
`prompt_hash`/`prompt_chars`, `media`, `use_memory` flags (fine to offer,
likely to be trimmed by a maintainer).

## Explicitly cut from v2 (with reasons)

| Candidate | Why cut |
|---|---|
| Rate-limit headroom headers | Provider-specific header zoo; `error_type: rate_limit` rows answer the actionable question |
| `key_frame` path | Requires re-ordering event fire vs response handling; dominated by the Phase-2 timeline-uid join |
| `server.address` | Constant per provider entry; `config_entry_id` already identifies it |
| Billing tier (standard/batch) | Integration has no batch path; a constant column |
| `structured_parse_ok`, outcome category, timeline uid | Phase 2 — all require post-parse capture |
| Automation *name* resolution | Query-time recorder join; live-state trick rejected (parallel-mode automations mis-attribute) |
| Presence / weather / sun / hour | Query-time joins on series already in InfluxDB (sun not included — add only if wanted) |

## Test plan (mirrors v1 discipline)

- `extract_finish_reason` across all five provider shapes + unknown + absent
- `extract_response_id` across the four id locations
- Source resolution: entity, path-stem, frigate, none, multi-source-first-wins
- Title override: `request_type`, `frame_count=0`, null hash, 4096 cap visible
- Prompt-hash mutation hazard regression (hash unchanged by title flow)
- Fallback marker: `fallback_from` set on the retry, null on primary
- Error event: fired on non-200 and on exception, correct `error_type` map,
  never raises, no token/message fields
- v1 compat: every v1 field byte-identical for a v1-style consumer

## Sizing

~15 payload additions + one new event + two extract helpers + timing. All
capture points verified in-reach. Estimated diff on the order of the v1
feature (smaller: no normalization convention to invent). Same release
process: branch → adversarial review → tests → `v1.7.1.2` tag + release →
HACS update → HA restart.
