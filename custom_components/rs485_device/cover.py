"""RS485 Curtain component."""
import asyncio
from datetime import timedelta
import logging
from typing import Any, Final

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SLAVE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .rs485_tcp_publisher import RS485TcpPublisher

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)

START_CODE: Final = 0x55  # 起始碼
READ_CMD: Final = 0x01  # 讀命令
WRITE_CMD: Final = 0x02  # 寫命令
CONTROL_CMD: Final = 0x03  # 控制命令
OPEN_CODE: Final = 0x01  # 開啟碼
CLOSE_CODE: Final = 0x02  # 關閉碼
STOP_CODE: Final = 0x03  # 停止碼
PERCENTAGE_CODE: Final = 0x04  # 百分比碼


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """通過配置條目設置開關實體."""

    # 從 entry.data 中獲取配置數據
    config = {
        **entry.data,
        "entry_id": entry.entry_id,
    }

    async_add_entities([RS485CurtainCover(hass, config)], True)


class RS485CurtainCover(CoverEntity):
    """表示一个窗帘类的 cover 设备."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.CURTAIN

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """初始化窗帘 cover 实体."""
        self.hass = hass
        self._is_open: bool = False
        self._slave: int = config.get(CONF_SLAVE, 0)
        self._slave_bytes: bytes = self._slave.to_bytes(2, byteorder="big")
        self._entry_id: str = config.get("entry_id", "")
        self._moving: bool = False
        self._unique_id: str = f"{self._entry_id}"
        self._position: int = 100
        self._destination: int = 100
        self._watching: bool = True
        self._publisher: RS485TcpPublisher = self.hass.data[DOMAIN][
            "rs485_tcp_publisher"
        ]
        self._watchdog_task = self.hass.data[DOMAIN][self._entry_id]["watchdog_task"]

    @property
    def name(self) -> str:
        """返回实体的名字."""
        return ""

    @property
    def unique_id(self) -> str:
        """返回實體的唯一 ID."""
        return self._unique_id

    @property
    def is_closed(self) -> bool:
        """如果窗帘关闭返回 True."""
        return self._position == 0

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
    def supported_features(self) -> CoverEntityFeature:
        """返回该实体支持的功能."""
        supported_features = CoverEntityFeature(0)
        if self.current_cover_position is not None:
            supported_features |= (
                CoverEntityFeature.OPEN
                | CoverEntityFeature.CLOSE
                | CoverEntityFeature.STOP
                | CoverEntityFeature.SET_POSITION
            )

        return supported_features

    @property
    def current_cover_position(self) -> int | None:
        """返回当前窗帘的位置."""
        return self._position

    async def _watchdogs(self):
        """監控 Publisher 是否運行."""
        try:
            while True:
                if self._publisher.is_running and self._watching:
                    await asyncio.wait_for(
                        self._publisher.send_message(
                            b"\x00\x8C\x00\x00\x00\x06\x55"
                            + self._slave_bytes
                            + b"\x01\x02\x01"
                        ),
                        timeout=1,
                    )
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            _LOGGER.info("Watchdog task was cancelled")
            return

    async def _subscribe_callback(self, sub_id: str, data: tuple[int]) -> None:
        if sub_id != self._unique_id:
            return

        # 确保数据长度足够
        if len(data) < 12:
            _LOGGER.error("Received data too short: %s", data)
            return

        if data[1] != 140:  # type: ignore[misc]
            _LOGGER.error("Unexpected data format: %s", data)
            return

        high_byte, low_byte = data[7:9][::-1]  # type: ignore[misc]
        _slave = (high_byte << 8) | low_byte

        _LOGGER.info("📡 Curtain Received data: %s %s 📡", data, self._moving)
        if _slave == self._slave:
            data_length = data[5]  # type: ignore[misc]
            position = self._position
            if data_length == 6:
                position = 100 - data[-1:][0]
            if data_length > 10:
                position = data[-1:][0]

            if position != self._position:
                if self._moving:
                    self._position = self._destination
                else:
                    self._position = position
            else:
                self._watching = False
                self._moving = False

            self.async_write_ha_state()

    async def async_added_to_hass(self):
        """當實體添加到 Home Assistant 時，設置狀態更新的計劃."""
        await self._publisher.start()
        # 訂閱數據
        await self._publisher.subscribe(self._subscribe_callback, self._unique_id)
        # 設置 watchdog 任務
        if self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._watchdogs())

    async def async_will_remove_from_hass(self):
        """當實體從 Home Assistant 中移除時，取消計劃."""
        self._watchdog_task.cancel()
        await self._publisher.unsubscribe(self._unique_id)
        sub_length = self._publisher.subscribers_length

        # 如果沒有訂閱者，則關閉 rs-485 伺服器的連接
        if sub_length == 0:
            await self._publisher.close()
            _LOGGER.info("🚧 Close publisher connect 🚧")

    async def async_update(self):
        """更新窗帘的状态."""
        if not self._watching:
            _LOGGER.info("Updating the curtain %s")
            await self._publisher.send_message(
                b"\x00\x8C\x00\x00\x00\x06\x55" + self._slave_bytes + b"\x01\x02\x01"
            )
            self.schedule_update_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """停止窗簾."""
        _LOGGER.info("Stopping the curtain")
        await self._publisher.send_message(
            b"\x00\x8C\x00\x00\x00\x05\x55" + self._slave_bytes + b"\x03\x03"
        )
        await asyncio.sleep(1)
        self._moving = False
        self._watching = True
        self.schedule_update_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """關閉窗簾."""
        _LOGGER.info("Closing the curtain")
        await self._publisher.send_message(
            b"\x00\x8C\x00\x00\x00\x05\x55" + self._slave_bytes + b"\x03\x01"
        )
        await asyncio.sleep(1)
        self._is_open = True
        self._moving = False
        self._position = 0
        self.schedule_update_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """打開窗簾."""
        _LOGGER.info("Opening the curtain")
        await self._publisher.send_message(
            b"\x00\x8C\x00\x00\x00\x05\x55" + self._slave_bytes + b"\x03\x02"
        )
        await asyncio.sleep(1)
        self._is_open = False
        self._moving = False
        self._position = 100
        self.schedule_update_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """设置窗帘的位置."""
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            _LOGGER.info("Setting the curtain position to %s", position)
            await self._publisher.send_message(
                b"\x00\x8C\x00\x00\x00\x06\x55"
                + self._slave_bytes
                + b"\x03\x04"
                + bytes([100 - position])
            )
            await asyncio.sleep(1)
            self._moving = True
            self._position = position
            self._destination = position
            self._is_open = position > 0
            self.schedule_update_ha_state()
