"""Tests for the native token-usage sensor platform (sensor.py)."""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch

from homeassistant.components.sensor import RestoreSensor, SensorStateClass
from homeassistant.config_entries import ConfigEntry

from custom_components.llmvision.const import (
    DOMAIN,
    SIGNAL_TOKEN_USAGE,
    SIGNAL_CALL_ERROR,
)
from custom_components.llmvision.sensor import (
    async_setup_entry,
    TokenCounterSensor,
    CallCounterSensor,
    ErrorCounterSensor,
    LastLatencySensor,
)


ENTRY_ID = "entry_anthropic_1"


def make_entry(provider="Anthropic", title="Anthropic Claude"):
    entry = Mock(spec=ConfigEntry)
    entry.entry_id = ENTRY_ID
    entry.title = title
    entry.data = {"provider": provider} if provider is not None else {}
    return entry


def usage_payload(**overrides):
    payload = {
        "schema": 2,
        "provider": "Anthropic",
        "config_entry_id": ENTRY_ID,
        "model": "claude-sonnet-5",
        "service": "image_analyzer",
        "input_tokens": 1200,
        "output_tokens": 80,
        "total_tokens": 1280,
        "cache_read_tokens": 100,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "latency_ms": 2382,
    }
    payload.update(overrides)
    return payload


class TestSetupEntry:
    """async_setup_entry creates entities for provider entries only."""

    @pytest.mark.asyncio
    async def test_provider_entry_creates_six_sensors(self, mock_hass):
        entry = make_entry()
        added = Mock()
        await async_setup_entry(mock_hass, entry, added)
        added.assert_called_once()
        entities = added.call_args[0][0]
        assert len(entities) == 6
        types = {type(e) for e in entities}
        assert types == {
            TokenCounterSensor,
            CallCounterSensor,
            ErrorCounterSensor,
            LastLatencySensor,
        }
        # Three token counters, one each of the rest
        assert sum(isinstance(e, TokenCounterSensor) for e in entities) == 3

    @pytest.mark.asyncio
    async def test_settings_entry_creates_nothing(self, mock_hass):
        entry = make_entry(provider="Settings", title="Settings")
        added = Mock()
        await async_setup_entry(mock_hass, entry, added)
        added.assert_not_called()

    @pytest.mark.asyncio
    async def test_entry_without_provider_creates_nothing(self, mock_hass):
        entry = make_entry(provider=None)
        added = Mock()
        await async_setup_entry(mock_hass, entry, added)
        added.assert_not_called()

    @pytest.mark.asyncio
    async def test_unique_ids_are_entry_scoped(self, mock_hass):
        entry = make_entry()
        added = Mock()
        await async_setup_entry(mock_hass, entry, added)
        unique_ids = {e.unique_id for e in added.call_args[0][0]}
        assert unique_ids == {
            f"{ENTRY_ID}_input_tokens",
            f"{ENTRY_ID}_output_tokens",
            f"{ENTRY_ID}_cache_read_tokens",
            f"{ENTRY_ID}_api_calls",
            f"{ENTRY_ID}_api_errors",
            f"{ENTRY_ID}_last_latency",
        }

    @pytest.mark.asyncio
    async def test_device_groups_sensors_under_entry(self, mock_hass):
        entry = make_entry()
        added = Mock()
        await async_setup_entry(mock_hass, entry, added)
        for entity in added.call_args[0][0]:
            info = entity.device_info
            assert info["identifiers"] == {(DOMAIN, ENTRY_ID)}
            assert info["name"] == "Anthropic Claude"
            assert info["model"] == "Anthropic"


class TestTokenCounter:
    def _sensor(self, key="input_tokens"):
        s = TokenCounterSensor(make_entry(), key, "Input tokens", "mdi:import")
        s.async_write_ha_state = Mock()
        return s

    def test_accumulates_from_none(self):
        s = self._sensor()
        s._handle_signal(usage_payload())
        assert s.native_value == 1200
        s.async_write_ha_state.assert_called_once()

    def test_accumulates_across_events(self):
        s = self._sensor()
        s._handle_signal(usage_payload())
        s._handle_signal(usage_payload(input_tokens=800))
        assert s.native_value == 2000

    def test_output_counter_reads_its_own_key(self):
        s = self._sensor(key="output_tokens")
        s._handle_signal(usage_payload())
        assert s.native_value == 80

    def test_starts_at_zero_not_unknown(self):
        assert self._sensor().native_value == 0

    def test_zero_delta_writes_no_state(self):
        s = self._sensor(key="cache_read_tokens")
        s._handle_signal(usage_payload(cache_read_tokens=0))
        assert s.native_value == 0
        s.async_write_ha_state.assert_not_called()

    def test_missing_and_garbage_values_ignored(self):
        s = self._sensor()
        s._handle_signal({})  # missing key
        s._handle_signal(usage_payload(input_tokens="not-a-number"))
        assert s.native_value == 0
        s.async_write_ha_state.assert_not_called()

    def test_state_class_is_total_increasing(self):
        assert self._sensor().state_class == SensorStateClass.TOTAL_INCREASING

    def test_signal_is_entry_scoped(self):
        assert self._sensor()._signal == f"{SIGNAL_TOKEN_USAGE}_{ENTRY_ID}"


class TestCallAndErrorCounters:
    def test_call_counter_increments_once_per_event(self):
        s = CallCounterSensor(make_entry())
        s.async_write_ha_state = Mock()
        s._handle_signal(usage_payload())
        s._handle_signal(usage_payload())
        assert s.native_value == 2

    def test_error_counter_listens_on_error_signal(self):
        s = ErrorCounterSensor(make_entry())
        s.async_write_ha_state = Mock()
        assert s._signal == f"{SIGNAL_CALL_ERROR}_{ENTRY_ID}"
        s._handle_signal({"error_type": "rate_limit"})
        assert s.native_value == 1


class TestLastLatency:
    def _sensor(self):
        s = LastLatencySensor(make_entry())
        s.async_write_ha_state = Mock()
        return s

    def test_records_latency(self):
        s = self._sensor()
        s._handle_signal(usage_payload())
        assert s.native_value == 2382
        assert s.state_class == SensorStateClass.MEASUREMENT

    def test_none_latency_keeps_last_measurement(self):
        s = self._sensor()
        s._handle_signal(usage_payload())
        s._handle_signal(usage_payload(latency_ms=None))
        assert s.native_value == 2382
        assert s.async_write_ha_state.call_count == 1

    def test_garbage_latency_ignored(self):
        s = self._sensor()
        s._handle_signal(usage_payload(latency_ms="fast"))
        assert s.native_value is None


class TestRestore:
    """Counters restore their prior total when re-added after a restart."""

    async def _add(self, sensor, stored_value, mock_hass):
        sensor.hass = mock_hass
        sensor.async_on_remove = Mock()
        stored = (
            None
            if stored_value is _NO_DATA
            else Mock(native_value=stored_value)
        )
        with patch.object(
            RestoreSensor, "async_added_to_hass", new=AsyncMock()
        ), patch.object(
            sensor, "async_get_last_sensor_data", new=AsyncMock(return_value=stored)
        ), patch(
            "custom_components.llmvision.sensor.async_dispatcher_connect",
            return_value=Mock(),
        ) as connect:
            await sensor.async_added_to_hass()
        return connect

    @pytest.mark.asyncio
    async def test_counter_restores_int(self, mock_hass):
        s = TokenCounterSensor(make_entry(), "input_tokens", "Input tokens", "mdi:import")
        await self._add(s, 12345.0, mock_hass)
        assert s.native_value == 12345
        # and continues accumulating on top of the restored value
        s.async_write_ha_state = Mock()
        s._handle_signal(usage_payload(input_tokens=5))
        assert s.native_value == 12350

    @pytest.mark.asyncio
    async def test_no_stored_data_keeps_zero_start(self, mock_hass):
        s = CallCounterSensor(make_entry())
        await self._add(s, _NO_DATA, mock_hass)
        assert s.native_value == 0

    @pytest.mark.asyncio
    async def test_stored_none_keeps_zero_start(self, mock_hass):
        s = CallCounterSensor(make_entry())
        await self._add(s, None, mock_hass)
        assert s.native_value == 0

    @pytest.mark.asyncio
    async def test_garbage_stored_value_resets_to_zero(self, mock_hass):
        s = CallCounterSensor(make_entry())
        await self._add(s, "corrupt", mock_hass)
        assert s.native_value == 0

    @pytest.mark.asyncio
    async def test_connects_to_entry_scoped_signal(self, mock_hass):
        s = ErrorCounterSensor(make_entry())
        connect = await self._add(s, 3, mock_hass)
        connect.assert_called_once_with(
            mock_hass, f"{SIGNAL_CALL_ERROR}_{ENTRY_ID}", s._handle_signal
        )

    @pytest.mark.asyncio
    async def test_latency_restores_value(self, mock_hass):
        s = LastLatencySensor(make_entry())
        await self._add(s, 1500, mock_hass)
        assert s.native_value == 1500


_NO_DATA = object()


class TestProviderDispatch:
    """providers.py sends entry-scoped signals alongside the bus events."""

    def _provider(self, mock_hass, entry_id=ENTRY_ID):
        from custom_components.llmvision.providers import OpenAI

        with patch(
            "custom_components.llmvision.providers.async_get_clientsession",
            return_value=Mock(),
        ):
            provider = OpenAI(hass=mock_hass, api_key="k", model="gpt-4o")
        provider._usage_entry_id = entry_id
        provider._usage_service = "image_analyzer"
        mock_hass.bus = Mock()
        return provider

    def test_usage_event_dispatches_entry_signal_with_bus_payload(self, mock_hass):
        provider = self._provider(mock_hass)
        response = {
            "model": "gpt-4o",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        with patch(
            "custom_components.llmvision.providers.async_dispatcher_send"
        ) as send, patch(
            "custom_components.llmvision.providers.Request.get_provider",
            return_value="OpenAI",
        ):
            provider._fire_usage_event(response, latency_ms=42)
        send.assert_called_once()
        hass_arg, signal, payload = send.call_args[0]
        assert hass_arg is mock_hass
        assert signal == f"{SIGNAL_TOKEN_USAGE}_{ENTRY_ID}"
        # Same payload object as the bus event — one source of truth
        assert payload is mock_hass.bus.async_fire.call_args[0][1]
        assert payload["input_tokens"] == 10
        assert payload["latency_ms"] == 42

    def test_usage_event_without_entry_id_does_not_dispatch(self, mock_hass):
        """Config-flow validation has no entry yet — no sensor to update."""
        provider = self._provider(mock_hass, entry_id=None)
        response = {"usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        with patch(
            "custom_components.llmvision.providers.async_dispatcher_send"
        ) as send:
            provider._fire_usage_event(response)
        mock_hass.bus.async_fire.assert_called_once()  # bus event still fires
        send.assert_not_called()

    def test_error_event_dispatches_entry_signal(self, mock_hass):
        provider = self._provider(mock_hass)
        with patch(
            "custom_components.llmvision.providers.async_dispatcher_send"
        ) as send, patch(
            "custom_components.llmvision.providers.Request.get_provider",
            return_value="OpenAI",
        ):
            provider._fire_error_event(429, "rate_limit", latency_ms=100)
        send.assert_called_once()
        _, signal, payload = send.call_args[0]
        assert signal == f"{SIGNAL_CALL_ERROR}_{ENTRY_ID}"
        assert payload is mock_hass.bus.async_fire.call_args[0][1]
        assert payload["error_type"] == "rate_limit"

    def test_error_event_without_entry_id_does_not_dispatch(self, mock_hass):
        provider = self._provider(mock_hass, entry_id=None)
        with patch(
            "custom_components.llmvision.providers.async_dispatcher_send"
        ) as send:
            provider._fire_error_event(None, "network")
        mock_hass.bus.async_fire.assert_called_once()
        send.assert_not_called()

    def test_dispatch_failure_cannot_break_the_request(self, mock_hass):
        """Telemetry contract: a raising dispatcher must be swallowed."""
        provider = self._provider(mock_hass)
        response = {"usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        with patch(
            "custom_components.llmvision.providers.async_dispatcher_send",
            side_effect=RuntimeError("no listeners"),
        ), patch(
            "custom_components.llmvision.providers.Request.get_provider",
            return_value="OpenAI",
        ):
            provider._fire_usage_event(response)  # must not raise
