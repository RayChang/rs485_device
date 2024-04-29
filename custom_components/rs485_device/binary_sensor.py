"""RS485 Sensor component."""
import asyncio
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, getcontext
import logging
from typing import Any, Final

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SLAVE, CONF_STATE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SENSORS_MODEL
from .rs485_tcp_publisher import RS485TcpPublisher

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=3)
getcontext().prec = 10


@dataclass(frozen=True, kw_only=True)
class RS485BinarySensorEntityDescription(BinarySensorEntityDescription):
    """針對 RS485 的感應器擴充屬性."""

    address: int | None = None


BINARY_SENSOR_TYPES: Final = {
    "SD123-HPR05": [
        RS485BinarySensorEntityDescription(
            key="human_sensor",
            name="Human Sensor Detection",
            device_class=BinarySensorDeviceClass.PRESENCE,
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
    for description in BINARY_SENSOR_TYPES[sensor_model]:
        sensors.append(RS485BinarySensor(hass, config, description))
    async_add_entities(sensors, True)


class RS485BinarySensor(BinarySensorEntity):
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
        self._identify = self._slave + self.entity_description.address
        self._entry_id: str = config.get("entry_id", "")
        self._unique_id: str = (
            f"{self._entry_id}_{self.entity_description.key}_{self._slave}"
        )
        self._publisher: RS485TcpPublisher = self.hass.data[DOMAIN][
            "rs485_tcp_publisher"
        ]
        self._delay = Decimal(str(self._slave / 10))
        self._identify_set: set[int] = self.hass.data[DOMAIN]["identify"]
        self._slaves_set: set[int] = self.hass.data[DOMAIN]["slaves"]
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

    async def _subscribe_callback(self, sub_id: str, data: tuple[int]) -> None:
        """訂閱回調函數."""
        if data[1] == self._identify and self._slave == data[6]:
            data_tuple = data[9:]
            data_tuple = tuple(
                (data_tuple[i] * 256 + data_tuple[i + 1])
                for i in range(0, len(data_tuple), 2)
            )
            self.hass.data[DOMAIN][self._entry_id][CONF_STATE] = data_tuple

            self._state = data_tuple[self.entity_description.address - 11]
            self.async_write_ha_state()

    async def async_added_to_hass(self):
        """當實體添加到 Home Assistant 時，設置狀態更新的計劃."""
        await super().async_added_to_hass()
        await self._publisher.start()
        # 訂閱數據
        await self._publisher.subscribe(
            self._subscribe_callback, self.entity_description.key
        )
        await self.coordinator.async_refresh()
        self._identify_set.add(self._identify)
        self._slaves_set.add(self._slave)

    async def async_will_remove_from_hass(self):
        """當實體從 Home Assistant 中移除時，取消計劃."""
        await self._publisher.unsubscribe(self._unique_id)
        sub_length = self._publisher.subscribers_length

        # 如果沒有訂閱者，則關閉 rs-485 伺服器的連接
        if sub_length == 0:
            await self._publisher.close()
            _LOGGER.info("🚧 Close publisher connect 🚧")

    async def async_update(self):
        """更新狀態."""
        message = self._publisher.construct_modbus_message(
            self._slave,
            3,
            self.entity_description.address,
            length=26,
            identify=self._identify,
        )
        delay = self._delay - int(self._delay)
        await asyncio.sleep(0.1 + float(delay))
        await self._publisher.send_message(message)
        self.schedule_update_ha_state()
