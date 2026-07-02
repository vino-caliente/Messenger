import sounddevice as sd
import asyncio
import numpy as np
from scipy.io.wavfile import write
import soundfile as sf

import cv2
from moviepy.editor import VideoFileClip, AudioFileClip
import moviepy.video.fx.all as vfx

import websockets as ws
import socket
import zlib

# Настройки
FS = 44100
CHANNELS = 1
CHUNK = 512

def mic_exists()->bool:
    devices = sd.query_devices()
    return any(d['max_input_channels']>0 for d in devices)

def cam_exists()->bool:
    cap = cv2.VideoCapture(0)
    res = True if cap.isOpened() else False
    cap.release()
    return res

async def record_audio(record_event: asyncio.Event, save_path: str):
    recording = []

    def callback(indata, frames, time, status):
        recording.append(indata.copy())

    # callback вызывается когда дописывается каждый небольшой кусочек (секунда)
    # для проверки нужно ли еще записывать, await asyncio.sleep(0.1) тоже необходим
    # иначе управление бы не возвращалось в основной поток пока идет запись
    # то есть запись шла бы бесконечно
    stream = sd.InputStream(samplerate=FS, channels=CHANNELS, callback=callback)
    stream.start()        
    while record_event.is_set():
        await asyncio.sleep(0.1)
    stream.stop()
    stream.close()

    # склеиваем и сохраняем
    full_recording = np.concatenate(recording, axis=0)
    write(save_path, FS, full_recording)

def init_video(fps: float, save_path: str)->tuple:
    cap = cv2.VideoCapture(0) # 0 - фронтальная камера
    # берём размер кадра
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(save_path, fourcc, fps, (w, h))
    return cap, out

async def record_video(init_pair, record_event: asyncio.Event, fps: float):
    cap, out = init_pair

    standard_pause = 1/fps
    while record_event.is_set():
        start = asyncio.get_event_loop().time()
        ret, frame = cap.read()
        if ret:
            out.write(frame)
        time_left = asyncio.get_event_loop().time() - start
        # обязательно пауза, чтобы работали другие задачи (аудио)
        await asyncio.sleep(max(0, standard_pause - time_left)) 

    cap.release()
    out.release()

def merge_audio_video(video_path, audio_path, output_path):
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)
        
    # вычисляем коэффициент ускорения/замедления
    # если видео короче аудио, коэффициент будет < 1 (замедление)
    speed_factor = video.duration / audio.duration
        
    # равномерно меняем скорость видеоряда
    # пересчитает тайминги всех кадров под новую длительность
    final_video = video.fx(vfx.speedx, speed_factor)
        
    # накладываем звук и сохраняем
    final_video = final_video.set_audio(audio)
    final_video.write_videofile(output_path, codec='libx264', audio_codec='aac')

async def play_audio(audio_path: str):
    data, fs = sf.read(audio_path)  # читаем файл
    sd.play(data, fs)
        
    # ждём окончания, не блокируя event loop
    while sd.get_stream().active:
        await asyncio.sleep(0.1)


# для звонков
async def record_and_send_audio(sock: ws.ClientConnection, record_event: asyncio.Event):
    loop = asyncio.get_running_loop()

    def callback(indata, frames, time, status):
        if status:
            return
        
        if record_event.is_set():
            asyncio.run_coroutine_threadsafe(sock.send(zlib.compress(indata)), loop)

    with sd.RawInputStream(samplerate=FS, blocksize=CHUNK, channels=CHANNELS, dtype='int16', callback=callback):
        while record_event.is_set():
            await asyncio.sleep(0.1)
    record_event.clear()

async def receive_and_play_audio(sock: ws.ClientConnection, play_event: asyncio.Event):
    with sd.RawOutputStream(samplerate=FS, blocksize=CHUNK, channels=CHANNELS, dtype='int16') as stream:
        try:
            async for data in sock:
                if not play_event.is_set() or data == b'END':
                    break
                stream.write(zlib.decompress(data))
        except ws.ConnectionClosed:
            pass
    play_event.clear()

async def call(chat_id: int, my_token: str, call_event: asyncio.Event, server_addr: str):
    headers = {'Authorization': f'Bearer {my_token}'}
    URL = f"ws://{server_addr}/call?chat_id={chat_id}"
    async with ws.connect(URL, additional_headers=headers) as sock:
        try:
            sock.transport.get_extra_info('socket').setsockopt(
                socket.IPPROTO_TCP, socket.TCP_NODELAY, 1
            )
            data = await asyncio.wait_for(sock.recv(), timeout=30)
            
            # это условие если звонок инициируется
            if str(data) == "Waiting for peer":
                data = await asyncio.wait_for(sock.recv(), timeout=30)

            if str(data) == "Connection established":
                await asyncio.gather(
                    record_and_send_audio(sock, call_event),
                    receive_and_play_audio(sock, call_event)
                )
            
            if str(data) == "Call Declined":
                return {'status': 'call declined'}
        except TimeoutError:
            return {'status': 'no answer'}
        except ws.ConnectionClosed:
            return {'status': 'end call'}
        
        return {'status': 'end'}