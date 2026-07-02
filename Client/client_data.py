import httpx
import datetime
import json
from collections import UserList
import pathlib

DOWNLOADS_DIR = pathlib.Path(__file__).resolve().parent / 'downloads'
DOWNLOADS_DIR.mkdir(exist_ok=True)

# вызывает заданный callback при изменениях
class ObservableList(UserList):
    def __init__(self, data=None, callback=None):
        super().__init__(data)
        self.callback = callback

    def set_callback(self, callback: callable):
        self.callback = callback

    # можно написать и для других методов
    def append(self, item):
        super().append(item)
        if self.callback:
            self.callback(self)

class Data:
    def __init__(self, token: str, username: str, server_addr: str):
        self.token = token
        self.username = username
        self.server_addr = server_addr

        self._chat_list = ObservableList() #list[dict]
        self._cb_chat_list = None # ссылка на callback который надо вызвать при изменении списка чатов

        self._selected_chat = None
        self._cb_selected_chat = None

        self._chat_messages = ObservableList() # сообщения из selected_chat
        self._cb_chat_messages = None

        base_url = f"http://{server_addr}"
        self.client = httpx.AsyncClient(base_url=base_url)
        # отдельный клиент для SSE без таймаута
        self.stream_client = httpx.AsyncClient(base_url=base_url, timeout=None)

        # понадобится в get_messages чтобы отбрасывать устаревшие запросы
        self._request_id = 0

        self._cb_call = None # когда приходит новый вызов

    @property
    def chat_list(self):
        return self._chat_list
    
    @chat_list.setter
    def chat_list(self, new_value: list):
        self._chat_list = ObservableList(new_value, self._cb_chat_list)
        # вызов callback который подписан на изменение списка чатов
        # в него также пережается измененный объект
        # планируется что это функция отображения
        if self._cb_chat_list:
            self._cb_chat_list(self._chat_list)
    
    def set_cb_chat_list(self, callback: callable):
        self._cb_chat_list = callback
        self._chat_list.set_callback(callback)


    def get_selected_chat(self):
        return self._selected_chat
    
    async def set_selected_chat(self, new_value: int):
        prev = self._selected_chat
        self._selected_chat = new_value
        # при изменении выбранного чата вызывать get_messages
        await self.get_messages()
        if self._cb_selected_chat:
            self._cb_selected_chat(prev, new_value)

    def set_cb_selected_chat(self, callback: callable):
        self._cb_selected_chat = callback


    @property
    def chat_messages(self):
        return self._chat_messages
    
    @chat_messages.setter
    def chat_messages(self, new_value: list):
        self._chat_messages = ObservableList(new_value, self._cb_chat_messages)
        # вызов callback который подписан на изменение списка чатов
        # в него также пережается измененный объект
        # планируется что это функция отображения
        if self._cb_chat_messages:
            self._cb_chat_messages(self._chat_messages)
    
    def set_cb_chat_messages(self, callback: callable):
        self._cb_chat_messages = callback
        self._chat_messages.set_callback(callback)

    def _get_auth_header(self):
        return {'Authorization': f'Bearer {self.token}'}

    async def get_chats(self):
        headers = self._get_auth_header()
        resp = await self.client.get("/chat_list", headers=headers)
        self.chat_list = resp.json()['chat_list']

    async def get_messages(self):
        headers = self._get_auth_header()
        self._request_id += 1
        req_id = self._request_id
        resp = await self.client.get("/chat_messages", params={'chat_id': self._selected_chat}, headers=headers)

        # если пользователь опять переключил чат до таго как пришел ответ,
        # то этот ответ уже устарел
        if req_id == self._request_id:
            self.chat_messages = resp.json()['chat_messages']

    async def user_exists(self, username: str)->bool:
        resp = await self.client.get("/username_exists", params={'username': username})
        return resp.json()['exists']

    async def create_chat(self, chat_name: str | None, username_list: list[str])->bool:
        headers = self._get_auth_header()
        username_list.append(self.username)
        response = await self.client.post("/new_chat", json={'chat_name': chat_name, 'username_list': username_list}, headers=headers)
        if response.status_code != 200:
            return False
        response = response.json()
        chat_id = response['id']
        members = ', '.join(username_list)
        is_group = True if len(username_list)>2 else False
        self.chat_list.append({'id': chat_id, 'name': chat_name, 'is_group': is_group, 'members': members})
        return True
    
    async def send_message(self, type: str, text: str = "", filepath: str | None = None)->bool:
        if self._selected_chat is None:
            return False
        
        data = {'chat_id': self._selected_chat, 'text': text, 'type': type}
        headers = self._get_auth_header()
        resp = None
        if filepath:
            with open(filepath, 'rb') as f:
                files = {'file': f}
                resp = await self.client.post('/new_message', data=data, files=files, headers=headers)
        else:
            resp = await self.client.post('/new_message', data=data, headers=headers)

        if resp.status_code != 200:
            return False
        time = datetime.datetime.now().strftime("%d.%m.%Y, %H:%M")
        self.chat_messages.append({'text': text, 'sended_at': time, 'username': self.username, 'type': type, 'id': resp.json()['msg_id']})
        return True
    
    async def get_file(self, msg_id: int)->str | None:
        # если ранее уже скачивался
        for file_path in DOWNLOADS_DIR.glob(f"{msg_id}.*"):
            return str(file_path)

        headers = self._get_auth_header()
        async with self.client.stream('GET', F"http://{self.server_addr}/message_file", params={'msg_id': msg_id}, headers=headers) as resp:
            if resp.status_code != 200:
                return None
            # content-disposition: attachment; filename="text.txt"
            filename = str(resp.headers.get('content-disposition'))
            ext = filename[filename.rfind("."):]
            file_path = DOWNLOADS_DIR / f"{msg_id}{ext}"
            with file_path.open('wb') as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
            return str(file_path)
        
    def set_cb_call(self, callback: callable):
        self._cb_call = callback

    async def get_updates(self):
        headers = self._get_auth_header()
        try:
            async with self.stream_client.stream('GET', '/event_stream', headers=headers) as resp:
                async for line in resp.aiter_lines():
                    # SSE-поток может присылать пустые строки между событиями
                    if not line.startswith("data:"):
                        continue
                    # Отрезаем префикс "data: " и выводим сообщение
                    message = line[5:].strip() 
                    print(f'New message: {message}')
                    message = json.loads(message)

                    if message['event_type'] == 'message':
                        chat_id = message['chat_id']
                        if chat_id == self._selected_chat:
                            self.chat_messages.append({'text': message['text'], 'sended_at': message['sended_at'], 'username': message['sender_username'], 'type': message['type'], 'id': message['msg_id']})

                    elif message['event_type'] == 'call':
                        if self._cb_call:
                            self._cb_call(message['chat_id'])

                    elif message['event_type'] == 'new_chat':
                        self.chat_list.append({'id': message['id'], 'name': message["name"], 'is_group': message["is_group"], 'members': message['members']})
        except (httpx.ReadError, httpx.RemoteProtocolError):
            pass  # соединение закрыто при выходе из приложения

    def get_chat_info(self, chat_id: int):
        for chat in self._chat_list:
            if chat['id'] == chat_id:
                return chat
            
    async def decline_call(self, chat_id: int):
        headers = self._get_auth_header()
        await self.client.get("/decline_call", params={'chat_id': chat_id}, headers=headers)
    
    async def close(self):
        await self.client.aclose()
        await self.stream_client.aclose()
