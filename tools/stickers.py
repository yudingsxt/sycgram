import asyncio
from math import floor
from typing import Optional

import emoji
from loguru import logger
from PIL import Image, UnidentifiedImageError
from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import Message

from .constants import STICKER_BOT, STICKER_IMG
from .helpers import Parameters, delete_this


class StickerLocker:
    """è´´çº¸æä»¤ð"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    def get_lock(self) -> None:
        return self._lock


sticker_locker = StickerLocker()


class StickerEvent:
    """è´´çº¸å¯¹è¯äºä»¶"""

    def __init__(self) -> None:
        self._cond = asyncio.Condition()

    def get_response(self) -> asyncio.Condition:
        return self._cond

    def wait(self):
        return self._cond.wait()

    def notify(self):
        return self._cond.notify()


sticker_cond = StickerEvent()


class StickerAdder:
    """
    æ°å¢è´´çº¸çæä»¤`-s`å®ç°è¯¦ç»æ­¥éª¤ï¼
    1ãè§£ç¦æºå¨äºº(`@Stickers`)
    2ãåé/cancel
    3ãæ£æµç®æ æ¶æ¯æ¯å¦ä¸ºè´´çº¸
        æ¯ï¼
            3-1ãè½¬åè´´çº¸å°@Stickerss
            3-2ãè·åå¹¶åéemoji
            3-3ãåé/done
            3-4ãç»ææä»¤
    4ãè¥ä¸æ¯ï¼åæ£æµæ¯å¦ä¸ºå¾çæå¾çæ ¼å¼çæä»¶
        1ãè½¬åå¾ç

    """

    def __init__(self, cli: Client, msg: Message) -> None:
        self._cli = cli
        self._msg = msg
        self._bot_id = STICKER_BOT
        self._count = 0

    def is_finished(self, pkg_existed: bool) -> bool:
        return (pkg_existed and self._count == 6) or \
            (not pkg_existed and self._count == 8)

    async def do_cancel(self) -> None:
        """åæ¶åæä»¤æ®çææ"""
        self._count = 0
        await self.send_message('/cancel')

    async def send_message(self, text: str) -> None:
        """åéæä»¤(æ`emoji`)ç»è´´çº¸"""

        try:
            await self._cli.send_message(
                self._bot_id, text,
                disable_notification=True)
        except FloodWait as e:
            await asyncio.sleep(e.x)
            await self._cli.send_message(
                self._bot_id, text,
                disable_notification=True)
        except RPCError as e:
            logger.warning(e)
        else:
            await self.__wait_for()

    async def send_emoji(self) -> None:
        _, arg = Parameters.get(self._msg)
        if emoji.is_emoji(arg):
            an_emoji = arg
        elif self._msg.reply_to_message.sticker:
            an_emoji = self._msg.reply_to_message.sticker.emoji
        else:
            an_emoji = 'â¡ï¸'
        await self.send_message(an_emoji)

    async def send_retries(self, n: int) -> None:
        try:
            retry_text = f"â ï¸ Retrying {n+1} times ..."
            await self._msg.edit_text(retry_text)
            logger.warning(retry_text)
        except RPCError as e:
            logger.warning(e)
        finally:
            await logger.complete()

    async def upload_photo(self) -> Optional[bool]:
        """ä¸è½½å¾ç/å¾çæä»¶ï¼ä¿®åªååéè³@Stickers"""
        img = await self._msg.reply_to_message.download(STICKER_IMG)
        if not img:
            return True
        try:
            resize_image(img)
        except UnidentifiedImageError as e:
            logger.warning(e)
            return True

        try:
            await self._cli.send_document(
                self._bot_id, document=img)
        except FloodWait as e:
            await asyncio.sleep(e.x)
            await self._cli.send_document(
                self._bot_id, document=img)
        except RPCError as e:
            logger.warning(e)
        else:
            await self.__wait_for()

    async def edit_text(self, text, parse_mode: Optional[str] = None) -> None:
        """ç¼è¾æ¶æ¯"""
        try:
            await self._msg.edit_text(text, parse_mode=parse_mode)
        except FloodWait as e:
            await asyncio.sleep(e.x)
            await self._msg.edit_text(text, parse_mode=parse_mode)
        except RPCError as e:
            logger.warning(e)

    async def done(self, text: str, parse_mode: Optional[str] = None) -> None:
        try:
            await self.edit_text(text, parse_mode=parse_mode)
            await asyncio.sleep(3.5)
            await delete_this(self._msg)
        except FloodWait as e:
            await asyncio.sleep(e.x)
            await self.edit_text(text, parse_mode=parse_mode)
            await asyncio.sleep(3.5)
            await delete_this(self._msg)
        except RPCError as e:
            logger.warning(e)

    async def mark_as_read(self) -> None:
        """èªå¨å·²è¯»æºå¨äººçæ¶æ¯"""
        try:
            await self._cli.get_chat_history(self._bot_id)
        except FloodWait as e:
            await asyncio.sleep(e.x)
            await self._cli.get_chat_history(self._bot_id)
        except RPCError as e:
            logger.warning(e)
        except Exception as e:
            logger.error(e)

    async def __wait_for(self) -> None:
        """ç­å¾è´´çº¸æºå¨äºº(`@Stickers`)çååº"""
        async with sticker_cond.get_response():
            await asyncio.wait_for(sticker_cond.wait(), timeout=5)
            logger.debug(
                f"Counter of response from @Stickers is {self._count}"
            )
            self._count = self._count + 1
            await self.mark_as_read()


def resize_image(photo: str):
    with Image.open(photo) as img:
        maxsize = (512, 512)
        if img.width < 512 or img.height < 512:
            w = img.width
            h = img.height
            if w > h:
                scale = 512 / w
                size1new = 512
                size2new = h * scale
            else:
                scale = 512 / h
                size1new = w * scale
                size2new = 512
            size_new = (floor(size1new), floor(size2new))
            img = img.resize(size_new)
        else:
            img.thumbnail(maxsize)
        img.save(photo, format='png')
        return


def isEmoji(content):
    if not content:
        return False
    if u"\U0001F600" <= content <= u"\U0001F64F":
        return True
    elif u"\U0001F300" <= content <= u"\U0001F5FF":
        return True
    elif u"\U0001F680" <= content <= u"\U0001F6FF":
        return True
    elif u"\U0001F1E0" <= content <= u"\U0001F1FF":
        return True
    else:
        return False
