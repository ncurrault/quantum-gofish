#!/usr/bin/env python
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser Public License for more details.
#
# You should have received a copy of the GNU Lesser Public License
# along with this program.  If not, see [http://www.gnu.org/licenses/].
#
# SEE: https://github.com/ncurrault/python-telegram-bot-postgres-persistence/

import pickle
from collections import defaultdict
from urllib.parse import urlparse
import psycopg2
from typing import (
    Any,
    Dict,
    Optional,
    Tuple,
    overload,
    cast,
    DefaultDict,
)

from telegram.ext import BasePersistence
from telegram.ext.utils.types import UD, CD, BD, ConversationDict, CDCData
from telegram.ext.contexttypes import ContextTypes

class PostgresPersistence(BasePersistence[UD, CD, BD]):
    __slots__ = (
        'postgres_url',
        'on_flush',
        'user_data',
        'chat_data',
        'bot_data',
        'callback_data',
        'conversations',
        'context_types',
    )

    @overload
    def __init__(
        self: 'PostgresPersistence[Dict, Dict, Dict]',
        postgres_url: str,
        store_user_data: bool = True,
        store_chat_data: bool = True,
        store_bot_data: bool = True,
        on_flush: bool = True,
        store_callback_data: bool = False,
    ):
        ...

    @overload
    def __init__(
        self: 'PostgresPersistence[UD, CD, BD]',
        postgres_url: str,
        store_user_data: bool = True,
        store_chat_data: bool = True,
        store_bot_data: bool = True,
        on_flush: bool = True,
        store_callback_data: bool = False,
        context_types: ContextTypes[Any, UD, CD, BD] = None,
    ):
        ...

    def __init__(
        self,
        postgres_url: str,
        store_user_data: bool = True,
        store_chat_data: bool = True,
        store_bot_data: bool = True,
        on_flush: bool = True,
        store_callback_data: bool = False,
        context_types: ContextTypes[Any, UD, CD, BD] = None,
    ):
        super().__init__(
            store_user_data=store_user_data,
            store_chat_data=store_chat_data,
            store_bot_data=store_bot_data,
            store_callback_data=store_callback_data,
        )

        parsed_url = urlparse(postgres_url)
        self.psycopg2_kwargs = {
            "dbname": parsed_url.path[1:],
            "user": parsed_url.username,
            "password": parsed_url.password,
            "host": parsed_url.hostname,
            "port": parsed_url.port,
        }

        self.on_flush = on_flush
        self.user_data: Optional[DefaultDict[int, UD]] = None
        self.chat_data: Optional[DefaultDict[int, CD]] = None
        self.bot_data: Optional[BD] = None
        self.callback_data: Optional[CDCData] = None
        self.conversations: Optional[Dict[str, Dict[Tuple, object]]] = None
        self.context_types = cast(ContextTypes[Any, UD, CD, BD], context_types or ContextTypes())

    def _load(self) -> None:
        conn = psycopg2.connect(**self.psycopg2_kwargs)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM telegram_persistence ORDER BY updated DESC LIMIT 1;")
                row = cur.fetchone()
                if row is None:
                    self.conversations = {}
                    self.user_data = defaultdict(self.context_types.user_data)
                    self.chat_data = defaultdict(self.context_types.chat_data)
                    self.bot_data = self.context_types.bot_data()
                    self.callback_data = None
                else:
                    data = pickle.loads(row[0])
                    self.user_data = defaultdict(self.context_types.user_data, data['user_data'])
                    self.chat_data = defaultdict(self.context_types.chat_data, data['chat_data'])
                    # For backwards compatibility with dumps not containing bot data
                    self.bot_data = data.get('bot_data', self.context_types.bot_data())
                    self.callback_data = data.get('callback_data', {})
                    self.conversations = data['conversations']
        except pickle.UnpicklingError as exc:
            raise TypeError(f"Database does not contain valid pickle data") from exc
        except Exception as exc:
            raise TypeError(f"Something went wrong loading from database/unpickling") from exc
        finally:
            conn.close()

    def _dump(self) -> None:
        conn = psycopg2.connect(**self.psycopg2_kwargs)
        try:
            with conn.cursor() as cur:
                data = {
                    'conversations': self.conversations,
                    'user_data': self.user_data,
                    'chat_data': self.chat_data,
                    'bot_data': self.bot_data,
                    'callback_data': self.callback_data,
                }
                data_serialized = pickle.dumps(data)
                cur.execute("INSERT INTO telegram_persistence (data) VALUES (%s);", (data_serialized,))
                conn.commit()
        finally:
            conn.close()

    def get_user_data(self) -> DefaultDict[int, UD]:
        if self.user_data:
            pass
        else:
            self._load()
        return self.user_data  # type: ignore[return-value]

    def get_chat_data(self) -> DefaultDict[int, CD]:
        if self.chat_data:
            pass
        else:
            self._load()
        return self.chat_data  # type: ignore[return-value]

    def get_bot_data(self) -> BD:
        if self.bot_data:
            pass
        else:
            self._load()
        return self.bot_data  # type: ignore[return-value]

    def get_callback_data(self) -> Optional[CDCData]:
        if self.callback_data:
            pass
        else:
            self._load()
        if self.callback_data is None:
            return None
        return self.callback_data[0], self.callback_data[1].copy()

    def get_conversations(self, name: str) -> ConversationDict:
        if self.conversations:
            pass
        else:
            self._load()
        return self.conversations.get(name, {}).copy()  # type: ignore[union-attr]

    def update_conversation(
        self, name: str, key: Tuple[int, ...], new_state: Optional[object]
    ) -> None:
        if not self.conversations:
            self.conversations = {}
        if self.conversations.setdefault(name, {}).get(key) == new_state:
            return
        self.conversations[name][key] = new_state
        if not self.on_flush:
            self._dump()

    def update_user_data(self, user_id: int, data: UD) -> None:
        if self.user_data is None:
            self.user_data = defaultdict(self.context_types.user_data)
        if self.user_data.get(user_id) == data:
            return
        self.user_data[user_id] = data
        if not self.on_flush:
            self._dump()

    def update_chat_data(self, chat_id: int, data: CD) -> None:
        if self.chat_data is None:
            self.chat_data = defaultdict(self.context_types.chat_data)
        if self.chat_data.get(chat_id) == data:
            return
        self.chat_data[chat_id] = data
        if not self.on_flush:
            self._dump()

    def update_bot_data(self, data: BD) -> None:
        if self.bot_data == data:
            return
        self.bot_data = data
        if not self.on_flush:
            self._dump()

    def update_callback_data(self, data: CDCData) -> None:
        if self.callback_data == data:
            return
        self.callback_data = (data[0], data[1].copy())
        if not self.on_flush:
            self._dump()

    def refresh_user_data(self, user_id: int, user_data: UD) -> None:
        pass # do nothing

    def refresh_chat_data(self, chat_id: int, chat_data: CD) -> None:
        pass # do nothing

    def refresh_bot_data(self, bot_data: BD) -> None:
        pass # do nothing

    def flush(self) -> None:
        if (
            self.user_data
            or self.chat_data
            or self.bot_data
            or self.callback_data
            or self.conversations
        ):
            self._dump()
