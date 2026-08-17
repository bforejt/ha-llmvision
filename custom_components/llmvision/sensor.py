"""Native token-usage sensors for LLM Vision.

Each provider config entry gets a device with token/call/error counters and a
last-latency sensor — the zero-configuration counterpart of the
`llmvision_token_usage` / `llmvision_call_error` bus events. The transport
layer (providers.py) dispatches an entry-scoped signal alongside each event;
sensors here subscribe to their own entry's signal only, so counts are
per-provider by construction.

Deliberately NOT here: cost. Pricing is not reported by upstream providers
and churns too often to maintain in code — cost stays in user-side YAML built
on the bus events (see README "Token Usage Events"). The events remain the
public API; these sensors are a convenience layer on the same data.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_PROVIDER,
    SIGNAL_TOKEN_USAGE,
    SIGNAL_CALL_ERROR,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up usage sensors for one provider config entry.

    __init__.py only forwards the sensor platform for provider entries (never
    Settings), but keep the guard here so a stray forward is a no-op.
    """
    if entry.data.get(CONF_PROVIDER) in (None, "Settings"):
        return

    async_add_entities(
        [
            TokenCounterSensor(entry, "input_tokens", "Input tokens", "mdi:import"),
            TokenCounterSensor(entry, "output_tokens", "Output tokens", "mdi:export"),
            TokenCounterSensor(
                entry,
                "cache_read_tokens",
                "Cached tokens",
                "mdi:database-arrow-down",
                # Subset of input tokens (billed at a discount) — tracked
                # separately, never added on top of the input total.
            ),
            CallCounterSensor(entry),
            ErrorCounterSensor(entry),
            LastLatencySensor(entry),
        ]
    )


class LLMVisionUsageSensor(RestoreSensor):
    """Base: entry-scoped, push-only, restores its value across restarts."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, key: str, name: str, icon: str) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="LLM Vision",
            model=entry.data.get(CONF_PROVIDER),
        )

    @property
    def _signal(self) -> str:
        """Entry-scoped dispatcher signal this sensor listens on."""
        raise NotImplementedError

    @callback
    def _handle_signal(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (
            last := await self.async_get_last_sensor_data()
        ) is not None and last.native_value is not None:
            self._restore_value(last.native_value)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._signal, self._handle_signal)
        )

    def _restore_value(self, value: Any) -> None:
        self._attr_native_value = value


class CounterSensorBase(LLMVisionUsageSensor):
    """A monotonically increasing counter; long-term statistics from install."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def _restore_value(self, value: Any) -> None:
        # Stored native values round-trip as Decimal/float; counters are ints.
        try:
            self._attr_native_value = int(value)
        except (TypeError, ValueError):
            self._attr_native_value = 0

    def _increment(self, amount: int) -> None:
        self._attr_native_value = int(self._attr_native_value or 0) + amount
        self.async_write_ha_state()


class TokenCounterSensor(CounterSensorBase):
    """Running total of one token field from the usage payload."""

    _attr_native_unit_of_measurement = "tokens"

    def __init__(self, entry: ConfigEntry, key: str, name: str, icon: str) -> None:
        super().__init__(entry, key, name, icon)
        self._key = key

    @property
    def _signal(self) -> str:
        return f"{SIGNAL_TOKEN_USAGE}_{self._entry.entry_id}"

    @callback
    def _handle_signal(self, payload: dict[str, Any]) -> None:
        try:
            delta = int(payload.get(self._key) or 0)
        except (TypeError, ValueError):
            return
        if delta:
            self._increment(delta)


class CallCounterSensor(CounterSensorBase):
    """Billed successful API calls (one usage event = one call).

    Errors are counted separately — this stays "billed successes only", the
    same contract as the bus events.
    """

    _attr_native_unit_of_measurement = "calls"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "api_calls", "API calls", "mdi:counter")

    @property
    def _signal(self) -> str:
        return f"{SIGNAL_TOKEN_USAGE}_{self._entry.entry_id}"

    @callback
    def _handle_signal(self, payload: dict[str, Any]) -> None:
        self._increment(1)


class ErrorCounterSensor(CounterSensorBase):
    """Failed API calls (transport failures: non-200, network, body read)."""

    _attr_native_unit_of_measurement = "errors"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "api_errors", "API errors", "mdi:alert-circle-outline")

    @property
    def _signal(self) -> str:
        return f"{SIGNAL_CALL_ERROR}_{self._entry.entry_id}"

    @callback
    def _handle_signal(self, payload: dict[str, Any]) -> None:
        self._increment(1)


class LastLatencySensor(LLMVisionUsageSensor):
    """Round-trip latency of the most recent successful call."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "ms"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "last_latency", "Last latency", "mdi:timer-outline")

    @property
    def _signal(self) -> str:
        return f"{SIGNAL_TOKEN_USAGE}_{self._entry.entry_id}"

    @callback
    def _handle_signal(self, payload: dict[str, Any]) -> None:
        latency = payload.get("latency_ms")
        # None on paths without timing (e.g. Bedrock client construction
        # failures never reach here; validate-only latency gaps) — keep the
        # last real measurement rather than blanking it.
        if latency is None:
            return
        try:
            self._attr_native_value = int(latency)
        except (TypeError, ValueError):
            return
        self.async_write_ha_state()
