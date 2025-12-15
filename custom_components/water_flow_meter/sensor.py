"""Sensor platform for Water Flow Meter integration."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    RestoreEntity,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_SOURCE_SENSOR,
    CONF_PULSES_PER_LITER,
    CONF_FLOW_RATE_WINDOW,
    DEFAULT_PULSES_PER_LITER,
    DEFAULT_FLOW_RATE_WINDOW,
    ATTR_LAST_PULSE_TIME,
    ATTR_PULSE_COUNT,
    ATTR_PULSES_PER_LITER,
    MANUFACTURER,
    MODEL,
)

_LOGGER = logging.getLogger(__name__)


class WaterFlowStatistics:
    """Shared statistics tracker for all sensors."""

    def __init__(self, pulses_per_liter: float):
        """Initialize statistics."""
        self.pulses_per_liter = pulses_per_liter
        self.start_time = dt_util.utcnow()

        # Daily statistics
        self.max_flow_today: float = 0.0
        self.total_flow_duration_today: float = 0.0  # seconds
        self.flow_start_time: datetime | None = None
        self.last_reset_date: datetime = dt_util.now().date()

        # Flow state tracking
        self.is_flowing: bool = False
        self.flow_starts_today: int = 0  # Number of times flow started today

        # Flow history for average calculation
        self.flow_history: list[tuple[datetime, float]] = []

        # Pulse tracking
        self.all_pulse_times: deque = deque(maxlen=1000)  # Keep last 1000 pulses
        self.flow_pulse_times: deque = deque()  # Shared deque for flow rate window
        self.total_pulse_count: int = 0  # Total pulses since start (no limit)
        self.total_pulses: float = 0.0  # Total pulses for volume calculation
        self.last_pulse_time: datetime | None = None
        self.last_pulse_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert statistics to dictionary for persistence."""
        return {
            "max_flow_today": self.max_flow_today,
            "total_flow_duration_today": self.total_flow_duration_today,
            "flow_start_time": self.flow_start_time.isoformat() if self.flow_start_time else None,
            "last_reset_date": self.last_reset_date.isoformat(),
            "last_pulse_time": self.last_pulse_time.isoformat() if self.last_pulse_time else None,
            "start_time": self.start_time.isoformat(),
            "is_flowing": self.is_flowing,
            "flow_starts_today": self.flow_starts_today,
            "total_pulses": self.total_pulses,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore statistics from dictionary."""
        try:
            self.max_flow_today = data.get("max_flow_today", 0.0)
            self.total_flow_duration_today = data.get("total_flow_duration_today", 0.0)
            self.is_flowing = data.get("is_flowing", False)
            self.flow_starts_today = data.get("flow_starts_today", 0)
            self.total_pulses = data.get("total_pulses", 0.0)

            if flow_start := data.get("flow_start_time"):
                self.flow_start_time = dt_util.parse_datetime(flow_start)

            if last_reset := data.get("last_reset_date"):
                self.last_reset_date = dt_util.parse_date(last_reset)

            if last_pulse := data.get("last_pulse_time"):
                self.last_pulse_time = dt_util.parse_datetime(last_pulse)

            if start := data.get("start_time"):
                self.start_time = dt_util.parse_datetime(start)
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Failed to restore statistics: %s", err)

    def reset_daily_stats(self) -> None:
        """Reset daily statistics."""
        self.max_flow_today = 0.0
        self.total_flow_duration_today = 0.0
        self.flow_start_time = None
        self.flow_history.clear()
        self.flow_starts_today = 0
        self.last_reset_date = dt_util.now().date()

    def check_and_reset_daily(self) -> None:
        """Check if we need to reset daily statistics."""
        today = dt_util.now().date()
        if today > self.last_reset_date:
            self.reset_daily_stats()

    def update_flow_stats(self, current_flow: float) -> None:
        """Update flow statistics."""
        self.check_and_reset_daily()
        now = dt_util.utcnow()

        # Update max flow
        if current_flow > self.max_flow_today:
            self.max_flow_today = current_flow

        # Track flow state changes and duration (flow > 0.1 L/min)
        was_flowing = self.is_flowing
        self.is_flowing = current_flow > 0.1

        if self.is_flowing:
            if self.flow_start_time is None:
                self.flow_start_time = now
                # Count flow starts (transition from not flowing to flowing)
                if not was_flowing:
                    self.flow_starts_today += 1
        else:
            if self.flow_start_time is not None:
                duration = (now - self.flow_start_time).total_seconds()
                self.total_flow_duration_today += duration
                self.flow_start_time = None

        # Add to history for average
        self.flow_history.append((now, current_flow))

        # Keep only last 24 hours of history
        cutoff = now - timedelta(hours=24)
        self.flow_history = [(t, f) for t, f in self.flow_history if t > cutoff]

    def get_average_flow_today(self) -> float:
        """Calculate average flow for today."""
        self.check_and_reset_daily()
        today_start = dt_util.start_of_local_day()

        today_flows = [f for t, f in self.flow_history if t >= today_start and f > 0]

        if not today_flows:
            return 0.0

        return sum(today_flows) / len(today_flows)

    def add_pulse(self, pulse_time: datetime, pulse_count: int = 1) -> None:
        """Add pulse(s) to tracking."""
        for _ in range(pulse_count):
            self.all_pulse_times.append(pulse_time)
            self.flow_pulse_times.append(pulse_time)
        self.total_pulses += pulse_count
        self.last_pulse_time = pulse_time

    def clean_old_flow_pulses(self, window_seconds: int) -> None:
        """Remove pulses older than the window."""
        cutoff_time = dt_util.utcnow() - timedelta(seconds=window_seconds)
        while self.flow_pulse_times and self.flow_pulse_times[0] < cutoff_time:
            self.flow_pulse_times.popleft()

    def get_average_pulse_interval(self) -> float | None:
        """Get average interval between pulses in seconds."""
        if len(self.all_pulse_times) < 2:
            return None

        # Calculate intervals for last 100 pulses
        recent_pulses = list(self.all_pulse_times)[-100:]
        intervals = []

        for i in range(1, len(recent_pulses)):
            interval = (recent_pulses[i] - recent_pulses[i-1]).total_seconds()
            if interval > 0:
                intervals.append(interval)

        if not intervals:
            return None

        return sum(intervals) / len(intervals)

    def get_instantaneous_pulse_interval(self) -> float | None:
        """Get instantaneous interval between last few pulses in seconds."""
        if len(self.all_pulse_times) < 2:
            return None

        # Use last 3 pulses for stability (average of last 2 intervals)
        recent_pulses = list(self.all_pulse_times)[-3:]
        if len(recent_pulses) < 2:
            return None

        intervals = []
        for i in range(1, len(recent_pulses)):
            interval = (recent_pulses[i] - recent_pulses[i-1]).total_seconds()
            if interval > 0:
                intervals.append(interval)

        if not intervals:
            return None

        return sum(intervals) / len(intervals)

    def get_time_since_last_pulse(self) -> float | None:
        """Get time since last pulse in seconds."""
        if self.last_pulse_time is None:
            return None

        return (dt_util.utcnow() - self.last_pulse_time).total_seconds()

    def get_uptime(self) -> float:
        """Get uptime in seconds."""
        return (dt_util.utcnow() - self.start_time).total_seconds()




def get_device_info(source_sensor: str, entry_id: str) -> DeviceInfo:
    """Get device info for all sensors."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=f"Water Flow Meter ({source_sensor.split('.')[-1]})",
        manufacturer=MANUFACTURER,
        model=MODEL,
        configuration_url="https://github.com/yourusername/HA-Water-Flow-Sensor",
    )

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Water Flow Meter sensors."""
    source_sensor = config_entry.data[CONF_SOURCE_SENSOR]
    pulses_per_liter = config_entry.options.get(
        CONF_PULSES_PER_LITER,
        config_entry.data.get(CONF_PULSES_PER_LITER, DEFAULT_PULSES_PER_LITER),
    )
    flow_rate_window = config_entry.options.get(
        CONF_FLOW_RATE_WINDOW,
        config_entry.data.get(CONF_FLOW_RATE_WINDOW, DEFAULT_FLOW_RATE_WINDOW),
    )

    # Create shared statistics tracker
    stats = WaterFlowStatistics(pulses_per_liter)

    # Store in hass.data for potential future use
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][config_entry.entry_id] = {"stats": stats}

    entities = [
        WaterFlowRateSensor(source_sensor, pulses_per_liter, flow_rate_window, config_entry.entry_id, stats),
        WaterFlowRateHourlySensor(source_sensor, pulses_per_liter, flow_rate_window, config_entry.entry_id, stats),
        WaterFlowRateSecondarySensor(source_sensor, pulses_per_liter, flow_rate_window, config_entry.entry_id, stats),
        WaterFlowRate5SecondSensor(source_sensor, pulses_per_liter, config_entry.entry_id, stats),
        WaterPulseRateSensor(source_sensor, flow_rate_window, config_entry.entry_id, stats),
        WaterInstantaneousFlowRateSensor(source_sensor, pulses_per_liter, config_entry.entry_id, stats),
        WaterInstantaneousPulseRateSensor(source_sensor, config_entry.entry_id, stats),
        WaterTotalVolumeSensor(source_sensor, pulses_per_liter, config_entry.entry_id, stats),
        WaterTimeSinceLastPulseSensor(source_sensor, config_entry.entry_id, stats),
        WaterAveragePulseIntervalSensor(source_sensor, config_entry.entry_id, stats),
        WaterUptimeSensor(source_sensor, config_entry.entry_id, stats),
        WaterIsFlowingBinarySensor(source_sensor, config_entry.entry_id, stats),
        WaterFlowStartsTodaySensor(source_sensor, config_entry.entry_id, stats),
        WaterRunningTimeTodaySensor(source_sensor, config_entry.entry_id, stats),
    ]

    # Store entities for service calls
    hass.data[DOMAIN][config_entry.entry_id]["entities"] = entities

    async_add_entities(entities, True)


class WaterFlowRateSensor(SensorEntity):
    """Sensor for water flow rate in liters per minute."""

    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_MINUTE
    _attr_icon = "mdi:water-pump"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        flow_rate_window: int,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the flow rate sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Flow Rate ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_flow_rate"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

        # Initialize from current state
        if state := self.hass.states.get(self._source_sensor):
            try:
                self._stats.last_pulse_value = float(state.state)
            except (ValueError, TypeError):
                pass

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return

        try:
            new_value = float(new_state.state)
        except (ValueError, TypeError):
            return

        # Detect pulse (increment in value)
        if self._stats.last_pulse_value is not None and new_value > self._stats.last_pulse_value:
            pulse_count = int(new_value - self._stats.last_pulse_value)
            now = dt_util.utcnow()

            # Update shared statistics (adds to both all_pulse_times and flow_pulse_times)
            self._stats.add_pulse(now, pulse_count)

            # Update flow statistics
            current_flow = self.native_value or 0.0
            self._stats.update_flow_stats(current_flow)

        self._stats.last_pulse_value = new_value

        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the flow rate in liters per minute."""
        # If window is 0, use instantaneous calculation based on pulse interval
        if self._flow_rate_window == 0:
            interval = self._stats.get_instantaneous_pulse_interval()

            if interval is None or interval == 0:
                return 0.0

            # Calculate flow rate from pulse interval
            # Flow = (1/pulses_per_liter) / interval_seconds * 60
            liters_per_pulse = 1.0 / self._pulses_per_liter
            liters_per_second = liters_per_pulse / interval
            liters_per_minute = liters_per_second * 60

            return round(liters_per_minute, 2)

        # Clean old pulses before calculating (sliding window mode)
        self._stats.clean_old_flow_pulses(self._flow_rate_window)

        if not self._stats.flow_pulse_times:
            return 0.0

        # Calculate pulses per minute based on the time window
        pulses_in_window = len(self._stats.flow_pulse_times)
        window_minutes = self._flow_rate_window / 60.0

        pulses_per_minute = pulses_in_window / window_minutes if window_minutes > 0 else 0
        liters_per_minute = pulses_per_minute / self._pulses_per_liter

        return round(liters_per_minute, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: len(self._stats.flow_pulse_times),
            "max_flow_today": round(self._stats.max_flow_today, 2),
            "average_flow_today": round(self._stats.get_average_flow_today(), 2),
            "total_flow_duration_today": round(self._stats.total_flow_duration_today, 1),
        }

        if self._stats.last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._stats.last_pulse_time.isoformat()

        return attrs


class WaterFlowRateHourlySensor(SensorEntity):
    """Sensor for water flow rate in liters per hour."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "L/h"
    _attr_icon = "mdi:water-pump"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        flow_rate_window: int,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the flow rate sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Flow Rate Hourly ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_flow_rate_hourly"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the flow rate in liters per hour."""
        # If window is 0, use instantaneous calculation based on pulse interval
        if self._flow_rate_window == 0:
            interval = self._stats.get_instantaneous_pulse_interval()

            if interval is None or interval == 0:
                return 0.0

            # Calculate flow rate from pulse interval
            liters_per_pulse = 1.0 / self._pulses_per_liter
            liters_per_second = liters_per_pulse / interval
            liters_per_minute = liters_per_second * 60
            liters_per_hour = liters_per_minute * 60

            return round(liters_per_hour, 2)

        # Clean old pulses before calculating (sliding window mode)
        self._stats.clean_old_flow_pulses(self._flow_rate_window)

        if not self._stats.flow_pulse_times:
            return 0.0

        # Calculate liters per minute first
        pulses_in_window = len(self._stats.flow_pulse_times)
        window_minutes = self._flow_rate_window / 60.0

        pulses_per_minute = pulses_in_window / window_minutes if window_minutes > 0 else 0
        liters_per_minute = pulses_per_minute / self._pulses_per_liter

        # Convert to liters per hour (L/min × 60)
        liters_per_hour = liters_per_minute * 60

        return round(liters_per_hour, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: len(self._stats.flow_pulse_times),
        }


class WaterFlowRateSecondarySensor(SensorEntity):
    """Sensor for water flow rate in liters per second."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "L/s"
    _attr_icon = "mdi:water-pump"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        flow_rate_window: int,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the flow rate sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Flow Rate Secondary ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_flow_rate_secondary"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the flow rate in liters per second."""
        # If window is 0, use instantaneous calculation based on pulse interval
        if self._flow_rate_window == 0:
            interval = self._stats.get_instantaneous_pulse_interval()

            if interval is None or interval == 0:
                return 0.0

            # Calculate flow rate from pulse interval
            liters_per_pulse = 1.0 / self._pulses_per_liter
            liters_per_second = liters_per_pulse / interval

            return round(liters_per_second, 3)

        # Clean old pulses before calculating (sliding window mode)
        self._stats.clean_old_flow_pulses(self._flow_rate_window)

        if not self._stats.flow_pulse_times:
            return 0.0

        # Calculate liters per minute first
        pulses_in_window = len(self._stats.flow_pulse_times)
        window_minutes = self._flow_rate_window / 60.0

        pulses_per_minute = pulses_in_window / window_minutes if window_minutes > 0 else 0
        liters_per_minute = pulses_per_minute / self._pulses_per_liter

        # Convert to liters per second (L/min ÷ 60)
        liters_per_second = liters_per_minute / 60

        return round(liters_per_second, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: len(self._stats.flow_pulse_times),
        }


class WaterFlowRate5SecondSensor(SensorEntity):
    """Sensor for water flow rate with 5-second window in liters per minute."""

    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_MINUTE
    _attr_icon = "mdi:water-pump"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the 5-second flow rate sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._entry_id = entry_id
        self._stats = stats
        self._flow_rate_window = 5  # Fixed 5-second window

        self._attr_name = f"Water Flow Rate 5 Second ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_flow_rate_5_second"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the flow rate in liters per minute (5-second window)."""
        # Create a temporary deque for 5-second window
        from collections import deque
        window_pulses = deque()

        # Get all pulses from the last 5 seconds
        cutoff_time = dt_util.utcnow() - timedelta(seconds=5)
        for pulse_time in self._stats.all_pulse_times:
            if pulse_time > cutoff_time:
                window_pulses.append(pulse_time)

        if not window_pulses:
            return 0.0

        # Calculate pulses per minute based on 5-second window
        pulses_in_window = len(window_pulses)
        window_minutes = 5.0 / 60.0  # 5 seconds in minutes

        pulses_per_minute = pulses_in_window / window_minutes
        liters_per_minute = pulses_per_minute / self._pulses_per_liter

        return round(liters_per_minute, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        # Count pulses in last 5 seconds
        cutoff_time = dt_util.utcnow() - timedelta(seconds=5)
        pulse_count = sum(1 for pt in self._stats.all_pulse_times if pt > cutoff_time)

        return {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: pulse_count,
            "window_seconds": 5,
        }


class WaterPulseRateSensor(SensorEntity):
    """Sensor for pulse rate per minute."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "pulses/min"
    _attr_icon = "mdi:counter"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        flow_rate_window: int,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the pulse rate sensor."""
        self._source_sensor = source_sensor
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Pulse Rate ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_pulse_rate"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the pulse rate per minute."""
        # If window is 0, use instantaneous calculation based on pulse interval
        if self._flow_rate_window == 0:
            interval = self._stats.get_instantaneous_pulse_interval()

            if interval is None or interval == 0:
                return 0.0

            # Calculate pulse rate: 60 seconds / interval
            pulses_per_minute = 60.0 / interval

            return round(pulses_per_minute, 2)

        # Clean old pulses before calculating (sliding window mode)
        self._stats.clean_old_flow_pulses(self._flow_rate_window)

        if not self._stats.flow_pulse_times:
            return 0.0

        # Calculate pulses per minute based on the time window
        pulses_in_window = len(self._stats.flow_pulse_times)
        window_minutes = self._flow_rate_window / 60.0

        pulses_per_minute = pulses_in_window / window_minutes if window_minutes > 0 else 0

        return round(pulses_per_minute, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_PULSE_COUNT: len(self._stats.flow_pulse_times),
        }

        if self._stats.last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._stats.last_pulse_time.isoformat()

        return attrs


class WaterInstantaneousFlowRateSensor(SensorEntity):
    """Sensor for instantaneous water flow rate in liters per minute (calculated from pulse interval)."""

    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_MINUTE
    _attr_icon = "mdi:water-pump"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the instantaneous flow rate sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Instantaneous Flow Rate ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_instantaneous_flow_rate"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the instantaneous flow rate in liters per minute."""
        # Get average interval between last few pulses
        interval = self._stats.get_instantaneous_pulse_interval()

        if interval is None or interval == 0:
            return 0.0

        # Calculate flow rate from pulse interval
        # Flow = (1/pulses_per_liter) / interval_seconds * 60
        liters_per_pulse = 1.0 / self._pulses_per_liter
        liters_per_second = liters_per_pulse / interval
        liters_per_minute = liters_per_second * 60

        return round(liters_per_minute, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            "pulse_interval": self._stats.get_instantaneous_pulse_interval(),
        }

        if self._stats.last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._stats.last_pulse_time.isoformat()

        return attrs


class WaterInstantaneousPulseRateSensor(SensorEntity):
    """Sensor for instantaneous pulse rate per minute (calculated from pulse interval)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "pulses/min"
    _attr_icon = "mdi:counter"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the instantaneous pulse rate sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Instantaneous Pulse Rate ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_instantaneous_pulse_rate"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the instantaneous pulse rate per minute."""
        # Get average interval between last few pulses
        interval = self._stats.get_instantaneous_pulse_interval()

        if interval is None or interval == 0:
            return 0.0

        # Calculate pulse rate: 60 seconds / interval
        pulses_per_minute = 60.0 / interval

        return round(pulses_per_minute, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "pulse_interval": self._stats.get_instantaneous_pulse_interval(),
        }

        if self._stats.last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._stats.last_pulse_time.isoformat()

        return attrs


class WaterTotalVolumeSensor(RestoreEntity, SensorEntity):
    """Sensor for total water volume in liters."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_icon = "mdi:water"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the total volume sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Total Volume ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_total_volume"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Restore state and register state listener."""
        await super().async_added_to_hass()

        # Restore previous state
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                # Restore statistics (including total_pulses)
                if "statistics" in last_state.attributes:
                    self._stats.from_dict(last_state.attributes["statistics"])

            except (ValueError, TypeError) as err:
                _LOGGER.warning("Failed to restore state: %s", err)

        # Register state change listener
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

        # Initialize from current state
        if state := self.hass.states.get(self._source_sensor):
            try:
                self._stats.last_pulse_value = float(state.state)
            except (ValueError, TypeError):
                pass

    async def async_reset_total_volume(self) -> None:
        """Reset total volume to zero."""
        self._stats.total_pulses = 0.0
        self.async_write_ha_state()

    async def async_set_total_volume(self, volume: float) -> None:
        """Set total volume to a specific value."""
        self._stats.total_pulses = volume * self._pulses_per_liter
        self.async_write_ha_state()

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        # Just update state - pulse counting is done in WaterFlowRateSensor
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the total volume in liters."""
        total_liters = self._stats.total_pulses / self._pulses_per_liter
        return round(total_liters, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: self._stats.total_pulses,
            "statistics": self._stats.to_dict(),
        }

    async def async_reset_daily_statistics(self) -> None:
        """Reset daily statistics."""
        self._stats.reset_daily_stats()
        self.async_write_ha_state()


class WaterTimeSinceLastPulseSensor(SensorEntity):
    """Sensor for time since last pulse."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-outline"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Time Since Last Pulse ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_time_since_last_pulse"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return time since last pulse in seconds."""
        time_since = self._stats.get_time_since_last_pulse()
        if time_since is None:
            return None
        return round(time_since, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {}
        if self._stats.last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._stats.last_pulse_time.isoformat()
        return attrs


class WaterAveragePulseIntervalSensor(SensorEntity):
    """Sensor for average pulse interval."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Average Pulse Interval ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_average_pulse_interval"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return average pulse interval in seconds."""
        avg_interval = self._stats.get_average_pulse_interval()
        if avg_interval is None:
            return None
        return round(avg_interval, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "pulse_count": len(self._stats.all_pulse_times),
        }


class WaterUptimeSensor(SensorEntity):
    """Sensor for component uptime."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:clock-outline"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Meter Uptime ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_uptime"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return uptime in seconds."""
        return round(self._stats.get_uptime(), 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        uptime = self._stats.get_uptime()
        days = int(uptime // 86400)
        hours = int((uptime % 86400) // 3600)
        minutes = int((uptime % 3600) // 60)

        return {
            "start_time": self._stats.start_time.isoformat(),
            "uptime_formatted": f"{days}d {hours}h {minutes}m",
        }


class WaterIsFlowingBinarySensor(BinarySensorEntity):
    """Binary sensor indicating if water is flowing."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Is Flowing ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_is_flowing"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if water is flowing."""
        return self._stats.is_flowing

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {}
        if self._stats.flow_start_time:
            current_flow_duration = (dt_util.utcnow() - self._stats.flow_start_time).total_seconds()
            attrs["current_flow_duration"] = round(current_flow_duration, 1)
        return attrs


class WaterFlowStartsTodaySensor(SensorEntity):
    """Sensor for number of flow starts today."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "starts"
    _attr_icon = "mdi:restart"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Flow Starts Today ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_flow_starts_today"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Return the number of flow starts today."""
        self._stats.check_and_reset_daily()
        return self._stats.flow_starts_today


class WaterRunningTimeTodaySensor(SensorEntity):
    """Sensor for total running time today."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Running Time Today ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_running_time_today"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return total running time today in seconds."""
        self._stats.check_and_reset_daily()

        # Add current flow duration if flowing
        total_duration = self._stats.total_flow_duration_today
        if self._stats.flow_start_time is not None:
            current_duration = (dt_util.utcnow() - self._stats.flow_start_time).total_seconds()
            total_duration += current_duration

        return round(total_duration, 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        total_seconds = self.native_value or 0
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)

        return {
            "formatted": f"{hours}h {minutes}m",
            "hours": round(hours + (minutes / 60), 2),
        }
