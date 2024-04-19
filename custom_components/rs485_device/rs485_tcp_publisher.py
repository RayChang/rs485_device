"""RS485 TCP Publisher."""
import asyncio
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class RS485TcpPublisher:
    """RS485 TCP Publisher."""

    def __init__(
        self,
        host: str,
        port: int,
        byte_length: int = 12,
        max_retry_delay: int = 60,
        connect_timeout: int = 10,
    ) -> None:
        """初始化 RS485 TCP Publisher 服務."""

        self.host = host
        self.port = port
        self.max_retry_delay = max_retry_delay  # 最大重試間隔，單位為秒
        self.connect_timeout = connect_timeout  # 連接超時時間，單位為秒
        self.byte_length = byte_length  # 用於存儲接收數據的字節長度
        self.connection_task = None  # 用於存儲連接任務的引用
        self.subscribers: dict[str, Any] = {}
        self.lock = asyncio.Lock()  # 增加一個鎖來控制對訂閱者列表的訪問
        self._running = False  # 增加一個運行狀態標誌
        self.is_running = False
        self.writer = None  # 用於存儲當前連接的StreamWriter對象

    @property
    def subscribers_length(self) -> int:
        """返回 self.subscribers 的長度作为属性."""
        return len(self.subscribers)

    # def _construct_modbus_message(
    #     self,
    #     slave: int,
    #     function_code: int,
    #     register: int,
    #     value: int | None = None,
    #     length: int | None = None,
    # ) -> bytes:
    #     """Modbus TCP Message."""
    #     header = b"\x00\x00\x00\x00\x00\x06" + bytes([slave])
    #     func_code = bytes([function_code])
    #     register_high = register >> 8
    #     register_low = register & 0xFF

    #     if function_code in (3, 4) and length is not None:  # 讀取寄存器，需要長度參數
    #         length_high = length >> 8
    #         length_low = length & 0xFF
    #         message = (
    #             header
    #             + func_code
    #             + bytes([register_high, register_low, length_high, length_low])
    #         )
    #     elif function_code == 6 and value is not None:  # 寫單個寄存器，需要值參數
    #         value_high = value >> 8
    #         value_low = value & 0xFF
    #         message = (
    #             header
    #             + func_code
    #             + bytes([register_high, register_low, value_high, value_low])
    #         )
    #     return message

    async def subscribe(self, callback, callback_id=None) -> None:
        """訂閱數據，必須提供 ID."""
        if callback_id is None:
            _LOGGER.error("訂閱必須包括一個唯一的ID。")
            return
        async with self.lock:  # 使用異步鎖來保護訂閱者列表的修改
            self.subscribers[callback_id] = callback
            _LOGGER.info("訂閱者: %s 已添加", callback_id)

    async def unsubscribe(self, callback_id):
        """取消訂閱，使用 ID 進行."""
        async with self.lock:
            if callback_id in self.subscribers:
                del self.subscribers[callback_id]
                _LOGGER.info("訂閱者: %s 已移除", callback_id)
            else:
                _LOGGER.info('沒有找到 ID 為"%s"的訂閱者', callback_id)

    async def send_message(self, message: bytes) -> None:
        """向 RS-485 伺服器發送訊息."""

        _LOGGER.info("💬 Message: %s 💬", message)
        if self.writer is None or self.writer.is_closing():
            _LOGGER.error("⛔️ 無有效連線，無法發送訊息。⛔️")
            return

        async with self.lock:
            try:
                self.writer.write(message)
                await self.writer.drain()
                _LOGGER.info("🚀 訊息已成功發送。 🚀")
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.error("🚧 發送訊息時出錯: %s 🚧", e)

    # async def read_register(self, slave: int, register: int, length: int) -> None:
    #     """讀取寄存器。構造並發送Modbus TCP請求讀取保持寄存器的消息."""
    #     message = self._construct_modbus_message(slave, 3, register, length=length)
    #     await self._send_message(message)

    # async def write_register(self, slave: int, register: int, value: int) -> None:
    #     """寫入寄存器。構造並發送 Modbus TCP 請求寫入保持寄存器的消息."""
    #     message = self._construct_modbus_message(slave, 6, register, value=value)
    #     await self._send_message(message)

    async def _publish(self, data):
        """發布數據給所有訂閱者，並返回他們的 ID."""
        tasks = []
        async with self.lock:
            for callback_id, callback in self.subscribers.items():
                task = asyncio.create_task(callback(sub_id=callback_id, data=data))
                tasks.append(task)
        # results = await asyncio.gather(*tasks, return_exceptions=True)
        # for task, result in zip(tasks, results):
        #     if isinstance(result, Exception):
        #         _LOGGER.error(
        #             "Exception in subscriber %s: %s", task.callback_id, result
        #         )

    async def _handle_connection(self):
        retry_delay = 1  # 初始重試間隔為1秒
        while self._running:
            try:
                reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=self.connect_timeout,
                )
                _LOGGER.info("成功連接到 %s:%i", self.host, self.port)
                self.is_running = True
                retry_delay = 1  # 連接成功，重置重試間隔
                await self._manage_connection(reader)
            except TimeoutError:
                _LOGGER.warning("連接到 %s:%i 超時", self.host, self.port)
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.error("連線錯誤: %s", e)
            finally:
                if self._running:  # 只有在運行狀態下才輸出重連信息
                    _LOGGER.info(
                        "嘗試重新連接到 %s:%i，等待 %i 秒…",
                        self.host,
                        self.port,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, self.max_retry_delay)
                if self.writer:
                    await self._close_writer()

    async def _manage_connection(self, reader):
        try:
            while True:
                data = await reader.read(self.byte_length)
                if not data:
                    _LOGGER.warning("連線被關閉，準備重新連接…")
                    break
                await self._publish(tuple(data))
        except asyncio.CancelledError:
            _LOGGER.info("連線被取消")

    async def _close_writer(self):
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            await self.writer.wait_closed()
            self.is_running = False

    async def start(self):
        """建立連線並開始接收數據."""
        if not self._running:
            self._running = True
            # 創建並啟動一個異步任務進行連接和數據接收
            self.connection_task = asyncio.create_task(self._handle_connection())
        else:
            _LOGGER.warning("連接已經建立，無需再次建立")

    async def close(self):
        """關閉當前連接並停止嘗試重連."""
        self._running = False  # 設置運行狀態為False以停止重連嘗試
        if self.connection_task and not self.connection_task.done():
            self.connection_task.cancel()
            try:
                await self.connection_task
            except asyncio.CancelledError:
                _LOGGER.info("Connection task cancelled")

        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
                _LOGGER.info("連接已關閉")
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.error("關閉連接時發生錯誤: %s", e)
        self.writer = None
