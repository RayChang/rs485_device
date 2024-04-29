"""RS485 Sensor component."""
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_SLAVE,
    CONF_STATE,
    PERCENTAGE,
    UnitOfLength,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SENSORS_MODEL

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=3)


@dataclass(frozen=True, kw_only=True)
class RS485SensorEntityDescription(SensorEntityDescription):
    """針對 RS485 的感應器擴充屬性."""

    address: int | None = None


SENSOR_TYPES: Final = {
    "SD123-HPR05": (
        RS485SensorEntityDescription(
            key="human_radar",
            name="Human Radar Detection",
            device_class="motion",
            address=12,
            icon="mdi:radar",
            native_unit_of_measurement="",
        ),
        RS485SensorEntityDescription(
            key="human_motion",
            name="Human Motion",
            device_class="motion",
            address=13,
            icon="mdi:motion-sensor",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RS485SensorEntityDescription(
            key="presence_detection",
            name="Presence Detection Sensitivity",
            device_class="motion",
            address=21,
            icon="mdi:leak",
            native_unit_of_measurement="",
        ),
        RS485SensorEntityDescription(
            key="state_detection",
            name="State Detection Sensitivity",
            device_class="motion",
            address=22,
            icon="mdi:leak",
            native_unit_of_measurement="",
        ),
        RS485SensorEntityDescription(
            key="presence_detection_range",
            name="Presence Detection Range",
            device_class=SensorDeviceClass.DISTANCE,
            address=23,
            icon="mdi:ruler",
            native_unit_of_measurement=UnitOfLength.METERS,
        ),
        RS485SensorEntityDescription(
            key="motion_state_detection_range",
            name="Motion State Detection Range",
            device_class=SensorDeviceClass.DISTANCE,
            address=25,
            icon="mdi:ruler",
            native_unit_of_measurement=UnitOfLength.METERS,
        ),
        RS485SensorEntityDescription(
            key="delay_for_motion_state_trigger",
            name="Delay for Motion State Trigger",
            device_class=SensorDeviceClass.DURATION,
            address=28,
            icon="mdi:timer-sand-complete",
            native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        ),
        RS485SensorEntityDescription(
            key="delay_from_motion_to_stationary_state",
            name="Delay from Motion to Stationary State",
            device_class=SensorDeviceClass.DURATION,
            address=32,
            icon="mdi:timer-pause-outline",
            native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        ),
        RS485SensorEntityDescription(
            key="delay_from_stationary_to_unoccupied_state",
            name="Delay from Stationary to Unoccupied State",
            device_class=SensorDeviceClass.DURATION,
            address=36,
            icon="mdi:timer-play-outline",
            native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        ),
    ),
    "SD123-HPR06": ["temperature", "humidity"],
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """通過配置條目設置感應器."""
    # 從 entry.data 中獲取配置數據
    config = {
        **entry.data,
        "entry_id": entry.entry_id,
    }

    sensor_model: str = entry.data.get(SENSORS_MODEL, "SD123-HPR05")
    sensors = []
    for description in SENSOR_TYPES[sensor_model]:
        sensors.append(RS485Sensor(hass, config, description))
    async_add_entities(sensors, True)


class RS485Sensor(SensorEntity):
    """RS485 Sensor entity."""

    _attr_has_entity_name = True
    entity_description: RS485SensorEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        description: RS485SensorEntityDescription,
    ) -> None:
        """Initialize the RS485Sensor."""
        self.hass = hass
        self.entity_description = description
        self._state = None
        self._slave: int = config.get(CONF_SLAVE, 0)
        self._entry_id: str = config.get("entry_id", "")
        self._unique_id: str = (
            f"{self._entry_id}_{self.entity_description.key}_{self._slave}"
        )
        self.coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=self.entity_description.name,
            update_method=self.async_update,
            update_interval=timedelta(seconds=5),
        )

    @property
    def unique_id(self) -> str:
        """返回實體的唯一 ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """返回實體的名稱."""
        return self.entity_description.name

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self.entity_description.device_class

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self.entity_description.native_unit_of_measurement

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this entity."""
        device = self.hass.data[DOMAIN][self._entry_id]["device"]
        return {
            "identifiers": device.identifiers,
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "connections": device.connections,
        }

    @property
    def native_value(self) -> StateType:
        """更新實體的狀態."""
        return self._state

    @property
    def state(self) -> dict[str, Any]:
        """返回传感器的当前状态，映射为具体描述."""
        if self.entity_description.key == "human_radar":
            return {0: "無人", 1: "靜止", 2: "活動"}.get(self._state, "未知")

        return self._state

    @property
    def device_state_attributes(self) -> dict[str, Any]:
        """返回設備的其他狀態屬性."""
        if self.entity_description.key == "human_radar":
            return {
                "description": {0: "無人", 1: "靜止", 2: "活動"}.get(
                    self._state, "未知"
                )
            }
        return {}

    async def async_added_to_hass(self):
        """當實體添加到 Home Assistant 時，設置狀態更新的計劃."""
        await super().async_added_to_hass()
        await self.coordinator.async_refresh()

    async def async_will_remove_from_hass(self):
        """當實體從 Home Assistant 中移除時，取消計劃."""

    async def async_update(self):
        """更新狀態."""
        if self.hass.data[DOMAIN][self._entry_id][CONF_STATE] is not None:
            self._state = self.hass.data[DOMAIN][self._entry_id][CONF_STATE][
                self.entity_description.address - 11
            ]
            self.schedule_update_ha_state()
