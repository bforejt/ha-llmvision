<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./logos/dark_logo@2x.png">
  <img alt="LLM Vision Logo" src="./logos/logo@2x.png" width="512">
</picture>
</p>
<p align=center>
<img src=https://img.shields.io/badge/HACS-Default-orange.svg>
<img src="https://img.shields.io/maintenance/yes/2026.svg">
<img src=https://img.shields.io/badge/version-1.7.1-blue>
<img alt="Issues" src="https://img.shields.io/github/issues/valentinfrlch/ha-llmvision?color=0088ff">
<img alt="Static Badge" src="https://img.shields.io/badge/support-buymeacoffee?logo=buymeacoffee&logoColor=black&color=%23FFDD00&link=https%3A%2F%2Fbuymeacoffee.com%2Fllmvision">
    <h2 align=center style="font-weight:bold">
      Visual intelligence for your home.
    </h2>
</p>

  <p align="center">
    <a href="#features">🌟 Features </a>
    ·
    <a href="#quick-start-guide">⬇️ Quick Start Guide</a>
    ·
    <a href="#resources">📖 Resources</a>
    ·
    <a href="#how-to-report-a-bug-or-request-a-feature">🪲 How to report Bugs</a>
    ·
    <a href="#support">☕ Support</a>    
  </p>
<p align="center">
  <a href="https://llmvision.org"> Visit Website →</a>
    </p>
<br>
<br>
<p align="center">
    <strong>LLM Vision</strong> is a Home Assistant integration that uses multimodal large language models to analyze images, videos, live camera feeds, and Frigate events. It can also keep track of analyzed events in a timeline, with an optional Timeline Card for your dashboard.
</p>

## Features
- Supports OpenRouter, OpenAI, Anthropic, Google Gemini, AWS Bedrock, Azure, Groq, [Ollama](https://ollama.com/), [Open WebUI](https://github.com/open-webui/open-webui), [LocalAI](https://github.com/mudler/LocalAI) and any provider with OpenAI compatible endpoints.
- Answers questions and provides descriptions of images, video files, live camera feeds, and Frigate events based on your prompt.
- Remembers people, pets and objects
- Keeps a timeline of camera events, so you can display them on your dashboard or ask Assist about them.
- Seamlessly updates sensors based on data extracted from camera streams, images or videos
- Reports token usage for every provider call, so you can track and budget your AI spend from Home Assistant

<br>

See the [website](https://llmvision.org) for the latest features and examples.
<img width="1027" alt="Bentoboard" src="https://github.com/user-attachments/assets/68af19b0-7000-4e5f-a3d3-c180ec2905f2" />




<br>

## Quick Start Guide
>[!TIP]
>LLM Vision is available in the default HACS repository. You can install it directly through HACS or click the button below to open it there.

[![Open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=valentinfrlch&repository=ha-llmvision&category=Integration)
1. **Install `LLM Vision`** from HACS
2. **Restart** Home Assistant
3. **Search for `LLM Vision`** in Home Assistant Settings/Devices & services
4. **Press submit** to continue setup with default settings
5. **Set up the media folder** LLM Vision uses the more secure `/media` folder for storing snapshots. If you're running Home Assistant Container, you may need to mount a folder to `/media` in your container settings. See the docs for more details.
6. **Return to the LLM Vision Integration Page** 
7. **Press 'Add Entry'** to add your first AI Provider

Detailed setup instructions and documentation is available here: [LLM Vision Documentation](https://llm-vision.gitbook.io/getting-started/setup/providers)

## Blueprint
With the easy to use blueprint, you'll get camera event notifications intelligently summarized by AI. LLM Vision can also store events in a timeline, so you can see what happened on your dashboard.
<br>
<p float="left">
    <img src="https://github.com/user-attachments/assets/621dacc0-7f9b-4c7a-b490-94286dd19e86" width="400" />
    <img src="https://github.com/user-attachments/assets/8174c3cd-6314-4bfd-9fbe-d66316f93923" width="400" />
</p>

[Learn how to install the blueprint](https://llm-vision.gitbook.io/getting-started/setup/blueprint)

## Token Usage Events
LLM Vision fires a `llmvision_token_usage` event on the Home Assistant event bus once per provider API call, so you can meter and budget your AI spend without touching any of your existing automations.

| Field | Description |
|---|---|
| `provider` | Provider as configured, e.g. `Anthropic`, `OpenRouter`, `Custom OpenAI` |
| `config_entry_id` | Which provider entry made the call; `null` during setup validation |
| `model` | Model reported by the provider, or the configured default |
| `service` | `image_analyzer`, `video_analyzer`, `stream_analyzer`, `data_analyzer`, or `validate` |
| `input_tokens` | All billed input tokens, cached tokens included |
| `output_tokens` | All billed output tokens, reasoning/thinking included |
| `total_tokens` | Reported by the provider, or `input_tokens + output_tokens` |
| `cache_read_tokens` | Cached portion of `input_tokens` (`0` if unsupported) |
| `cache_write_tokens` | Cache-write portion of `input_tokens` (`0` if unsupported) |
| `reasoning_tokens` | Reasoning portion of `output_tokens` (`0` if unsupported) |

>[!IMPORTANT]
>`input_tokens` and `output_tokens` are always the full billed counts. `cache_read_tokens`, `cache_write_tokens` and `reasoning_tokens` are **subsets** of those totals, reported separately because they are usually billed at a different rate — never add them on top.

Providers report usage in incompatible formats, so these counts are normalized: values are comparable across OpenAI, Anthropic, Google, AWS Bedrock, Ollama and the OpenAI-compatible providers.

Since schema 2 (fork build 1.7.1.2), each event also carries the request's identity and shape — `request_type` (`vision`/`title`/`validate`), `source` + `source_kind` (the camera entity or file stem that was analyzed), `frigate_event_id`, `target_entity` (data_analyzer's target), `frame_count`, `target_width`, `request_max_tokens`, `prompt_hash`/`prompt_chars` (vision requests only), `media` (the raw input path/entity), `use_memory`, `generate_title`, `response_format`, `fallback_from` (the original provider when served by the fallback) — plus response metadata: `latency_ms`, `finish_reason` (normalized `stop`/`length`/`tool_use`/`safety`/`other`; `length` means the output was truncated), and the provider's `response_id`. A `schema` field versions the payload.

Failed calls fire a separate `llmvision_call_error` event (transport-level: non-200 or network failure) (its own `schema: 1`) with `status_code`, a normalized `error_type` (`auth`/`not_found`/`bad_request`/`rate_limit`/`overloaded`/`server`/`network`/`other`), `latency_ms`, and the same identity fields — but never token counts or message content. Successful billed calls and failures are deliberately separate streams so usage totals stay clean.

Note that events also fire when you save a provider in the setup flow (`service: validate`), because that performs a real API call, and that `generate_title` produces a second event for the title request (`request_type: title`).

### Native sensors

Since fork build 1.7.1.3, every provider config entry creates a **device** with six sensors — zero configuration, visible under *Settings → Devices & Services → LLM Vision* from the moment the integration loads:

| Sensor | State class | What it tracks |
|---|---|---|
| **Input tokens** | `total_increasing` | All billed input tokens, cached included |
| **Output tokens** | `total_increasing` | All billed output tokens, reasoning included |
| **Cached tokens** | `total_increasing` | Cache-read subset of input tokens — informational, never added on top |
| **API calls** | `total_increasing` | Billed successful calls only |
| **API errors** | `total_increasing` | Transport failures (non-200, network, failed body read) |
| **Last latency** | `measurement` | Round-trip ms of the most recent successful call |

Entity ids derive from the entry title: an entry named *Anthropic Claude* produces `sensor.anthropic_claude_input_tokens`, and so on.

Design notes:

- **Per-provider by construction.** Each entry's sensors are updated only by that entry's own API calls — the transport layer addresses them per config entry, it doesn't filter after the fact. Two accounts of the same provider stay separate.
- **Counters start at `0` and survive restarts.** `total_increasing` with restore means long-term statistics accrue from install, with no template tricks and no reset on reboot.
- **Same contract as the events.** API calls counts billed successes only; failures land in API errors. A validation call made from the setup flow before the entry exists is counted nowhere.
- **Cost is deliberately not a sensor.** Providers do not report pricing in their API responses, and rates change too often to maintain in integration code — a stale hardcoded rate table would silently corrupt everyone's cost history. The events below carry everything needed (normalized token counts, model, provider), so pricing stays in user configuration where rates can be kept current.

The sensors and the events are two layers over the same data, and they are complementary: sensors are the zero-config surface for dashboards and long-term statistics; the events are the full-fidelity hook — per-call payloads with request identity, latency, and context chaining — for automations, cost ledgers, and external databases like InfluxDB.

A trigger-based template sensor is the simplest way to accumulate totals across all providers (or to enrich events with pricing):

```yaml
template:
  - triggers:
      - trigger: event
        event_type: llmvision_token_usage
    sensor:
      - name: "LLM Vision Input Tokens"
        unique_id: llmvision_input_tokens_total
        state: "{{ (this.state | int(0)) + (trigger.event.data.input_tokens | int(0)) }}"
        state_class: total_increasing
        unit_of_measurement: tokens
      - name: "LLM Vision Output Tokens"
        unique_id: llmvision_output_tokens_total
        state: "{{ (this.state | int(0)) + (trigger.event.data.output_tokens | int(0)) }}"
        state_class: total_increasing
        unit_of_measurement: tokens
```

Point a [Utility Meter helper](https://www.home-assistant.io/integrations/utility_meter/) at these sensors for daily or monthly cycles. Each event also carries the context of the automation or script that triggered the call, so usage can be traced back to its caller.

>[!TIP]
>If you build a per-model rate table on top of these events, match the `model` field by **prefix**, not equality: providers frequently report dated variants (`claude-haiku-4-5-20251001`, `gpt-4o-2024-08-06`) that bill at the base model's rate but won't hit an exact-match table entry.

## Resources
Check the docs for detailed instructions on how to set up LLM Vision and each of the supported providers, get inspiration from examples or join the discussion on the Home Assistant Community and Discord.

<a href="https://llmvision.org"><img alt="Static Badge" src="https://img.shields.io/badge/website-teal?style=for-the-badge&&logoColor=white&link=https%3A%2F%2Fvalentinfrlch.github.io%2Fllmvision%2F"></a>
<a href="https://llm-vision.gitbook.io/getting-started"><img src="https://img.shields.io/badge/Documentation-blue?style=for-the-badge&logo=gitbook&logoColor=white&color=18bcf2"/> </a><a href="https://llmvision.org/gallery/"><img src="https://img.shields.io/badge/Examples-blue?style=for-the-badge&logo=gitbook&logoColor=black&color=39ffc2"/></a> </a>
<a href="https://discord.gg/wuFeMfCMRB"><img src="https://img.shields.io/badge/Discord-blue?style=for-the-badge&logo=discord&logoColor=white&color=7289da"/> </a>
<a href="https://community.home-assistant.io/t/llm-vision-let-home-assistant-see/729241"><img src="https://img.shields.io/badge/Community-blue?style=for-the-badge&logo=homeassistant&logoColor=white&color=03a9f4"/></a>


For technical questions see the discussions tab.


## How to report a bug or request a feature
> [!IMPORTANT]
> **Bugs:** If you encounter any bugs and have followed the instructions carefully, file a bug report. Please check open issues first and include debug logs in your report. Debugging can be enabled on the integration's settings page.
> **Feature Requests:** If you have an idea for a feature, create a feature request.
><div align = left>
>
>[<kbd> <br> Create new Issue <br> </kbd>][KBD]
>
></div>
>
>[KBD]: https://github.com/valentinfrlch/ha-llmvision/issues/new/choose


## Support
You can support this project by starring this GitHub repository. If you want, you can also buy me a coffee here:  
<br>
<img alt="Static Badge" src="https://img.shields.io/badge/support-buymeacoffee?logo=buymeacoffee&logoColor=black&color=%23FFDD00&link=https%3A%2F%2Fbuymeacoffee.com%2Fllmvision">
