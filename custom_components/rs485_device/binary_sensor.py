"""RS485 Sensor component."""

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Final

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SLAVE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SENSORS_MODEL
from .modbus_client import ModbusClient
from .rs485_tcp_publisher import RS485TcpPublisher

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=3)


@dataclass(frozen=True, kw_only=True)
class RS485BinarySensorEntityDescription(BinarySensorEntityDescription):
    """針對 RS485 的感應器擴充屬性."""

    address: int | None = None


BINARY_SENSOR_TYPES: Final = {
    "SD123-HPR05": [
        RS485BinarySensorEntityDescription(
            key="human_sensor",
            name="Human Sensor Detection",
            device_class="presence",
            address=11,
        )
    ],
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
    BinarySensorEntity = (
        sensor_model == "SD123-HPR05" and RS485ModbusBinarySensor or RS485BinarySensor
    )
    for description in BINARY_SENSOR_TYPES[sensor_model]:
        sensors.append(BinarySensorEntity(hass, config, description))
    async_add_entities(sensors, True)


class RS485ModbusBinarySensor(BinarySensorEntity):
    """RS485 Modbus Binary Sensor entity."""

    _attr_has_entity_name = True
    entity_description: RS485BinarySensorEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        description: RS485BinarySensorEntityDescription,
    ) -> None:
        """Initialize the RS485ModbusBinarySensor."""
        self.hass = hass
        self.entity_description = description
        self._state = False
        self._slave: int = config.get(CONF_SLAVE, 0)
        self._entry_id: str = config.get("entry_id", "")
        self._unique_id: str = (
            f"{self._entry_id}_{self.entity_description.key}_{self._slave}"
        )
        self._modbus_client: ModbusClient = self.hass.data[DOMAIN]["modbus_client"]
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
    def is_on(self) -> bool | None:
        """如果有人就返回 True."""
        return self._state

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

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        await super().async_added_to_hass()
        await self.coordinator.async_refresh()

    async def async_update(self):
        """更新狀態."""
        self._state = await self.hass.async_add_executor_job(
            self._modbus_client.read_holding_registers,
            self._slave,
            self.entity_description.address,
            1,
        )
        if self._state is not None:
            self._state = bool(self._state[0])
            _LOGGER.info("🚧 Binary Sensor Update 🚧 %s", self._state)


class RS485BinarySensor(BinarySensorEntity):
    """RS485 Switch entity."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any], type: str) -> None:
        """Initialize the RS485Switch."""
        self.hass = hass
        self._type = type
        self._entry_id: str = config.get("entry_id", "")
        self._unique_id: str = f"{self._entry_id}_{self._type}"
        self._name: str = f"Sensor {self._type}"
        self._publisher: RS485TcpPublisher = self.hass.data[DOMAIN][
            "rs485_tcp_publisher"
        ]

    @property
    def unique_id(self) -> str:
        """返回實體的唯一 ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """返回實體的名稱."""
        return self._name

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
