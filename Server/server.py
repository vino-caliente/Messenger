from fastapi import FastAPI, Body, Response, status, Request, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Header, HTTPException, Depends
from fastapi.responses import StreamingResponse, FileResponse
from pathlib import Path
import uvicorn
from contextlib import asynccontextmanager
from work_with_db import *
import aiomysql
import asyncio
import datetime
import json
import shutil # shell utilities
import jwt
import hashlib
import secrets

import socket
SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 8090

# ключ - id пользователя, значение - очередь новых сообщений для этого пользователя
connections = {}
# ключ - id пользователя, значение - пара ws, peer_id
# получается для каждого звонка по 2 ключа
active_calls = {}
# чтобы следить за записью в сокеты
send_locks = {}

# чтобы создать папку storage в том же каталоге где лежит файл сервера
STORAGE_DIR = Path(__file__).resolve().parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # код который выполняется до запуска приложения
    app.state.pool = await aiomysql.create_pool(**DB_CONFIG)
    try:
        # запуск приложения (app)
        yield
    finally:
        # после завершения приложения
        app.state.pool.close()
        await app.state.pool.wait_closed()

app = FastAPI(lifespan=lifespan)

SECRET_KEY = 'some_key_28728383239_super_secret_key_32_bytes!'  # минимум 32 байта
ALGORITHM = 'HS256'

def create_token(username: str, user_id: int)->str:
    expire = datetime.datetime.now() + datetime.timedelta(days=1)
    expire = expire.timestamp()

    payload = {'username': username, 'user_id': user_id, 'expire': expire}
    token = jwt.encode(payload, key=SECRET_KEY, algorithm=ALGORITHM)
    return token

# возвращает user_id
def verify_token(auth: str = Header(None, alias="Authorization"))->int:
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No bearer token")
    
    token = auth.replace("Bearer ", "")
    try:
        data = jwt.decode(token, key=SECRET_KEY, algorithms=ALGORITHM)
        return data['user_id']
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
def hash_password(password: str)->str:
    salt = secrets.token_hex(16)
    hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}:{hash}"

def verify_password(password: str, stored: str)->bool:
    salt, stored_hash = stored.split(':')
    new_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return new_hash == stored_hash

# для возможности проверки доступности сервера клиентом
@app.get("/")
def root():
    return {'message': "Server is available"}

# аутентификация пользователя, если успешно то возвращается id пользователя 
# необходимый для дальнейшей работы с бд, иначе - ошибка
# post чтобы не передавать username и password как параметр
@app.post("/sign_in", status_code=status.HTTP_200_OK)
# флаг embed если получаем отдельные значения, а не все тело целиком
async def sign_in(resp: Response,
            username: str = Body(embed=True, min_length=1, max_length=50),    
            password: str = Body(embed=True, min_length=1, max_length=50)):
    
    answ = await get_user(app.state.pool, username)
    if answ is None:
        resp.status_code = status.HTTP_401_UNAUTHORIZED
        return {'error': "Incorrect username"}
    
    password_hash, id = answ
    if not verify_password(password, password_hash):
        resp.status_code = status.HTTP_401_UNAUTHORIZED
        return {'error': "Incorrect password"}
    
    return {'token': create_token(username, id)}

# проверка существует ли пользователь username 
# возвращает bool для ключа 'exists'   
@app.get("/username_exists")
async def username_exists(username: str):
    exists = await check_if_exists(app.state.pool, username)
    return {'exists': exists}

# добавляет пользователя в бд если username свободен и возвращает его id
# иначе ошибка
@app.post("/registration", status_code=status.HTTP_200_OK)
async def registration(resp: Response,
                 username: str = Body(embed=True, min_length=1, max_length=50),    
                 password: str = Body(embed=True, min_length=1, max_length=50)):
    exists = await check_if_exists(app.state.pool, username)
    if exists:
        resp.status_code = status.HTTP_409_CONFLICT
        return {'error': "Username already exists"}
    else:
        password_hash = hash_password(password)
        id = await add_user(app.state.pool, username, password_hash)
        return {'token': create_token(username, id)}

# создать личный чат или группу (для группы можно передать название)
# свой юзернейм тоже нужно передавать как одного из участников    
# возвращает id чата (уникальный идентификатор)
@app.post("/new_chat")
async def new_chat(resp: Response,
             creator_id: int = Depends(verify_token),
             username_list: list[str] = Body(embed=True),
             chat_name: str| None = Body(embed=True)):
    if len(username_list) < 2:
        resp.status_code = status.HTTP_400_BAD_REQUEST
        return {'error': "At least 2 users in chat"}
    
    is_group = True if len(username_list)>2 else False
    chat_name = chat_name if is_group else None
    id, users = await create_chat(app.state.pool, username_list, chat_name, is_group)
    send_username_list = ", ".join(username_list)

    payload = {
        "event_type": "new_chat",
        "id": id,
        "name": chat_name,
        "is_group": is_group,
        "members": send_username_list
    }
    sse_formatted_msg = f"data: {json.dumps(payload)}\n\n"
    for user_id in users:
        if user_id in connections and user_id != creator_id:
            await connections[user_id].put(sse_formatted_msg)

    return {'id': id}

@app.post("/new_message")
# File(None) означает что параметр необязателен
# приходится отправлять данные не в body а в form тк
# одновременно передать и файл и данные можно только в http-запросе multipart/form-data
# причем все данные неявно конвертируются в str, поэтому None, вложенные структуры нельзя
async def new_message(resp: Response,
                    sender_id: int = Depends(verify_token),
                    chat_id: int = Form(...),
                    type: str = Form(...),
                    text: str = Form(''), # необязательный параметр, дефолт - ''
                    file: UploadFile | None = File(None)):
    if type not in ['file', 'audio', 'video', 'text']:
        resp.status_code = status.HTTP_400_BAD_REQUEST
        return {'error': "parameter 'type' should be 'file'/'audio'/'video'/'text'"}

    if type in ['file', 'audio', 'video'] and file is None:
        resp.status_code = status.HTTP_400_BAD_REQUEST
        return {'error': "Accoding to the type should contain file"}

    if type == 'file':
        text = file.filename
    # добавление сообщения в бд, возвращается id сообщения и список участников чата
    data = await send_message(app.state.pool, sender_id, chat_id, type, text)
    if data is None:
        resp.status_code = status.HTTP_400_BAD_REQUEST
        return {'error': "Incorrect sender_id or chat_id"}
    message_id, chat_members = data
    sender_username = await get_username_by_id(app.state.pool, sender_id)
    
    # если сообщение - файл, то нужно записать его
    if type in ['file', 'audio', 'video']:
        ext = Path(file.filename).suffix
        file_path = STORAGE_DIR / f"{message_id}{ext}"
        with file_path.open('wb') as storage_file:
            shutil.copyfileobj(file.file, storage_file)

    chat_members.remove(sender_id)
    # сообщение добавляется в очередь для отправки всем участникам чата которые на связи (в connections)
    payload = {
        "event_type": "message",
        "sender_username": sender_username,
        "chat_id": chat_id,
        "type": type,
        "text": text,
        "msg_id": message_id,
        "sended_at": datetime.datetime.now().strftime("%d.%m.%Y, %H:%M") # datetime нужно перевести в строку иначе json не воспринимает
    }
    sse_formatted_msg = f"data: {json.dumps(payload)}\n\n"
    for user_id in chat_members:
        if user_id in connections:
            await connections[user_id].put(sse_formatted_msg)
    return {'msg_id': message_id}

@app.get("/message_file")
async def message_file(resp: Response, msg_id: int, user_id = Depends(verify_token)):
    info = await get_message_info(app.state.pool, msg_id)

    if info is None:
        resp.status_code = status.HTTP_400_BAD_REQUEST
        return {'error': "No such message"}
    
    type = info['type']
    user_filename = info['text']
    if type == 'text':
        resp.status_code = status.HTTP_400_BAD_REQUEST
        return {'error': "Text message doesn't have file"}
    
    for file_path in STORAGE_DIR.glob(f"{msg_id}.*"):
        break
    if user_filename == "":
        user_filename = str(file_path)
    return FileResponse(file_path, filename=user_filename)

@app.get("/event_stream")
async def event_stream(request: Request, user_id: int = Depends(verify_token)):
    # отдельная очередь для этого подключения
    queue = asyncio.Queue()
    connections[user_id] = queue

    async def event_generator():
        try:
            while True:
                # это сработает, когда клиент закроет соединение
                if await request.is_disconnected():
                    break

                data = await queue.get()
                yield data
        finally:
            if user_id in connections:
                del connections[user_id]

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/chat_list")
async def chat_list(resp: Response, user_id: int = Depends(verify_token)):
    data = await get_chat_list(app.state.pool, user_id)
    if data is None:
        resp.status_code = status.HTTP_404_NOT_FOUND
        return {'error': 'user_id does not exist'}
    return {'chat_list': data}

@app.get("/chat_messages")
async def chat_messages(resp: Response, chat_id: int, user_id: int = Depends(verify_token)):
    data = await get_chat_messages(app.state.pool, chat_id)
    if data is None:
        resp.status_code = status.HTTP_404_NOT_FOUND
        return {'error': 'chat_id does not exist'}
    for msg in data:
        # предполагается что msg['sended_at'] формата datetime
        msg['sended_at'] = msg['sended_at'].strftime("%d.%m.%Y, %H:%M")
    return {'chat_messages': data}

@app.websocket("/call")
# чат может быть только из двух пользователей
async def call(ws: WebSocket, chat_id: int, user_id: int = Depends(verify_token)):
    await ws.accept()

    if user_id in active_calls:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="You are already talking")
        return

    peer_id = await get_peer_id(app.state.pool, user_id, chat_id)
    if not peer_id:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Incorrect chat_id or caller_id")
        return
    if peer_id not in connections:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="User is not active")
        return
    
    send_locks[user_id] = asyncio.Lock()

    try:
        active_calls[user_id] = ws
        # если user_id инициатор звонка
        if peer_id not in active_calls:
            await ws.send_text("Waiting for peer")
            payload = {
            "event_type": "call",
            "chat_id": chat_id
            }
            sse_formatted_msg = f"data: {json.dumps(payload)}\n\n"
            await connections[peer_id].put(sse_formatted_msg)
        # это ответ собеседника
        else:
            peer_ws = active_calls[peer_id]
            await peer_ws.send_text("Connection established")
            await ws.send_text("Connection established")

        # подразумевается что если user_id отправил данные,
        # то ему уже пришло подтверждение, а значит active_calls[peer_id] уже существует 
        while True:
            try:
                data = await ws.receive_bytes()
                if peer_id in active_calls:
                    async with send_locks.get(user_id):
                        await active_calls[peer_id].send_bytes(data)
                else:
                    break
            except WebSocketDisconnect:  # нормальное завершение звонка
                break

    except WebSocketDisconnect:
        pass
    finally:
        if peer_id in active_calls:
            async with send_locks.get(user_id):
                await active_calls[peer_id].send_bytes(b'END') 
        send_locks.pop(user_id, None)
        sock = active_calls.pop(user_id, None)
        try:
            await sock.close()
        except:
            pass

# это вообще не get но я не знаю как иначе сделать эту отмену
@app.get('/decline_call')
async def decline_call(chat_id: int, user_id: int = Depends(verify_token)):
    peer_id = await get_peer_id(app.state.pool, user_id, chat_id)
    if peer_id in active_calls:
        try:
            await active_calls[peer_id].send_text("Call Declined")
        except:
            pass
        finally:
            # await asyncio.sleep(0.1)
            try:
                await active_calls[peer_id].close()
            except:
                pass
        send_locks.pop(peer_id, None)
        sock = active_calls.pop(peer_id, None)

if __name__=='__main__':
    # запуск сервера
    # в первом параметре указывается имя файла:объект приложение если флаг reload 
    # (перезагрузка при изменениях) если флага нет, просто объект
    uvicorn.run('server:app', host=SERVER_IP, port=SERVER_PORT)
    # uvicorn сам контролирует eventloop