from client_data import Data, ObservableList
import work_with_audio_video as my_player
from entrance import Entrance

import customtkinter as ctk
import asyncio
from async_tkinter_loop import async_handler, async_mainloop
from CTkMessagebox import CTkMessagebox

import vlc
import platform

from pathlib import Path
import os
import sys

class CallWindow(ctk.CTkToplevel):
    def __init__(self, master, data: Data, chat_id: int, call_type: str):
        super().__init__(master)
        self.title("call")
        self.geometry("200x200")
        self.data = data
        self.call_event = asyncio.Event()
        self.chat_id = chat_id
        self.call_type = call_type
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._closed = False

        self.lift()  
        self.focus_force()
        self.update()
        self.attributes("-topmost", True)
        self.columnconfigure((0, 1), weight=1)
        self.rowconfigure((0, 1), weight=1)

        memb = data.get_chat_info(chat_id)['members']
        self.memb_lbl = ctk.CTkLabel(self, text=memb)
        self.memb_lbl.grid(column=0, row=0, columnspan=2, sticky='nsew')

        if call_type == 'answer':
            self.accept_btn = ctk.CTkButton(self, text='accept', command=async_handler(self.on_accept), fg_color='green', height=50)
            self.accept_btn.grid(column=0, row=1, sticky='ew', padx=(10, 5), pady=(10, 10))

            self.reject_btn = ctk.CTkButton(self, text='reject', command=async_handler(self.on_reject), fg_color='red', height=50)
            self.reject_btn.grid(column=1, row=1, sticky='ew', padx=(5, 10), pady=(10, 10))
        # это не ответ, а звонок инициирован мной
        else:
            self.after(10, async_handler(self.on_accept)) # без этого не находит loop

    async def on_accept(self):
        if self.call_type == 'answer':
            self.accept_btn.destroy()
            self.reject_btn.destroy()

        self.status_lbl = ctk.CTkLabel(self, text='call')
        self.status_lbl.grid(column=0, row=1, columnspan=2, sticky='nsew')

        self.call_event.set()
        res = await my_player.call(self.chat_id, self.data.token, self.call_event, self.data.server_addr)
        if not self._closed:   # если конец звонка инициирован нами то это не нужно
            self.status_lbl.configure(text=res['status'])

    async def on_reject(self):
        await self.data.decline_call(self.chat_id)
        self.on_close()
    
    def on_close(self):
        self._closed = True
        self.call_event.clear()
        self.destroy()

class VideoWindow(ctk.CTkToplevel):
    VIDEO_W = 640
    VIDEO_H = 480

    def __init__(self, master, video_path: str, call_on_destroy: callable = None):
        super().__init__(master)
        self.geometry(f"{self.VIDEO_W}x{self.VIDEO_H}")
        self.title("video message")
        self.configure(fg_color="black") 
        self.call_on_destroy = call_on_destroy

        # окно на передний план
        self.lift()  
        # фокус окну
        self.focus_force()
        # принудительно обновляем окно, чтобы оно успело получить системный ID
        self.update()
        # окно "всегда сверху"
        self.attributes("-topmost", True)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._closed = False

        # инициализируем VLC
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()

        # привязываем плеер к ID нового окна
        win_id = self.winfo_id()
        if platform.system() == "Windows":
            self.player.set_hwnd(win_id)
        else:
            self.player.set_xwindow(win_id)

        # запуск видео
        media = self.instance.media_new(video_path)
        self.player.set_media(media)
        self.player.play()

        # следим за окончанием
        self.check_video_end()

    def on_close(self):
        if self._closed:
            return
        
        self.player.stop()
        if self.call_on_destroy:
            self.call_on_destroy()
        self.destroy()

    def check_video_end(self):
        # если окно закрыли вручную раньше времени
        if self._closed:
            return

        state = self.player.get_state()
        if state == vlc.State.Ended or state == vlc.State.Error:
            # закрываем окно по завершении
            self.on_close()
        else:
            self.after(500, self.check_video_end)

class NewChatForm(ctk.CTkToplevel):
    def __init__(self, master, data: Data):
        super().__init__(master)
        self.geometry(f"320x240")
        self.title("new chat")
        self.attributes("-topmost", True)
        self.focus_force()

        self.data = data
        self.username_list = []
        self.username_list_lbl = ctk.CTkLabel(self, text='Group: [me]')
        self.username_list_lbl.pack(pady=(0, 10))
        
        self.chatname_lbl = ctk.CTkLabel(self, text='Enter the name of the group:')
        self.chatname_lbl.pack()
        self.chatname_entry = ctk.CTkEntry(self, placeholder_text='Enter here...')
        self.chatname_entry.pack(pady=(0, 10))

        self.username_lbl = ctk.CTkLabel(self, text='Enter username of group member:')
        self.username_lbl.pack()
        self.username_entry = ctk.CTkEntry(self, placeholder_text='Enter here...')
        self.username_entry.pack()
        self.username_btn = ctk.CTkButton(self, text='add user', command=async_handler(lambda: self.add_user(self.username_entry.get())))
        self.username_btn.pack(pady=(5, 10))

        self.submit_btn = ctk.CTkButton(self, text='create group', command=async_handler(lambda: self.submit(self.chatname_entry.get())))
        self.submit_btn.pack()

    async def add_user(self, username: str):
        exists = await self.data.user_exists(username)
        if exists and username not in self.username_list and username != self.data.username:
                self.username_list.append(username)
                self.username_list_lbl.configure(text=f"Group: [me, {', '.join(self.username_list)}]")
                self.username_entry.delete(0, "end")
        else:
            CTkMessagebox(title='Error', message=f"User {username} doesn't exist", icon='cancel')

    async def submit(self, chat_name: str | None):
        if self.username_list:
            await self.data.create_chat(chat_name or "", self.username_list)
        else:
            CTkMessagebox(title='Error', message=f"No group members", icon='cancel')
        self.destroy()

class ChatListFrame(ctk.CTkScrollableFrame):
    # self - экземпляр этого класса, master - экземпляр самой формы
    def __init__(self, master, title: str, data: Data):
        super().__init__(master, label_text=title) # создание на форме ctk.CTkScrollableFrame
        self.grid_columnconfigure(0, weight=1)  # чтобы на всю ширину Frame добавлялись
        self.chatlist = [] # список созданных объектов label
        self.data = data
        self.data.set_cb_chat_list(self.update)
        self.chatbutton = ctk.CTkButton(self, text='+', command=self.new_chat_form)
        self.chatbutton.grid(column=0, row=0, sticky='nsew')

    def new_chat_form(self):
        # всплывающее окно
        self.video_window = NewChatForm(self, self.data)

    def clear(self):
        for chat in self.chatlist:
            chat.destroy()
        self.chatlist = []

    def update(self, chat_list: ObservableList):
        self.clear()
        i=1
        for chat_info in chat_list.data:
            text = ""
            if chat_info['is_group']: 
                text = f"{chat_info['name']}\n"
            text += chat_info['members']
            label = ctk.CTkLabel(self, text=text)
            self.chatlist.append(label)
            label.grid(row=i, column=0)
            # значения аргументов по умолчанию вычисляются в момент определения функции (в данном случае - в момент создания лямбды), а не в момент её вызова
            label.bind('<Enter>', lambda event, lbl=label : lbl.configure(fg_color="#6B6767"))
            label.bind('<Leave>', lambda event, lbl=label : lbl.configure(fg_color='transparent'))
            label.bind('<Button-1>', async_handler(lambda event, id=chat_info['id'] : self.on_click(event, id)))
            i=i+1

    # невероятная конструкция чтобы передать аргумент в обработчик
    # ip задастся в момент инициализации, и потом можно будет понять на каком именно лейбле произошло событие
    async def on_click(self, event, id):
        widget = event.widget
        if widget.widgetName == 'label' and self.data.get_selected_chat() != id:
            await self.data.set_selected_chat(id)

class MessageFrame(ctk.CTkFrame):
    def __init__(self, master, data: Data, messageobj: dict, fg_color, wraplength):
        super().__init__(master, corner_radius=10, fg_color=fg_color)
        self.data = data
        # text_color="#19202E", wraplength=0.45*w
        self.configure(border_width=0)
        self.columnconfigure(0, weight=1)
        self.sender_label = ctk.CTkLabel(self, text=messageobj['username'], anchor='w', font=("font5", 10, "bold"), width=0, height=0, text_color="#C2B05A")
        self.sender_label.grid(row=0, column=0, sticky='w', padx=(10,10), columnspan = 2)

        msg_text = messageobj['text']
        if messageobj['type'] in ['audio', 'video']:
            msg_text = f"{messageobj['type']} message"
        self.text_label = ctk.CTkLabel(self, text=msg_text, anchor='w', wraplength=wraplength)
        self.text_label.grid(row=1, column=0, sticky='we', padx=(3,3))

        if messageobj['type'] == 'audio':
            self.play_btn = ctk.CTkButton(self, text='play', width=40, command=async_handler(lambda id=messageobj['id']: self.on_play_audio(id)))
            self.play_btn.grid(row=1, column=1, sticky='e', padx=(3,3))

        if messageobj['type'] == 'video':
            self.play_btn = ctk.CTkButton(self, text='play', width=40, command=async_handler(lambda id=messageobj['id']: self.on_play_video(id)))
            self.play_btn.grid(row=1, column=1, sticky='e', padx=(3,3))        

        self.time_label = ctk.CTkLabel(self, text=messageobj['sended_at'], anchor='e', font=("font5", 10), width=0, height=0, text_color="#C2B884")
        self.time_label.grid(row=2, column=0, sticky='e', padx=(10,10), columnspan = 2)

    async def on_play_audio(self, msg_id: int):
        filepath = await self.data.get_file(msg_id)

        self.play_btn.configure(text="playing...")
        await my_player.play_audio(filepath)
        
        # после окончания
        self.play_btn.configure(text="play")

    async def on_play_video(self, msg_id: int):
        filepath = await self.data.get_file(msg_id)
        self.play_btn.configure(text="playing...")

        # всплывающее окно
        self.video_window = VideoWindow(self, filepath, lambda: self.play_btn.configure(text="play"))
        

class ChatFrame(ctk.CTkScrollableFrame):
    def __init__(self, master, title: str, data: Data):
        super().__init__(master, label_text=title)
        self.chathist = [] # список созданных объектов label
        self.data = data
        self.data.set_cb_chat_messages(self.update)
        self.columnconfigure((0,1), weight=1)

    def clear(self):
        for message in self.chathist:
            message.destroy()
        self.chathist = []

    def selected_chat_info(self)->dict | None:
        selected_id = self.data.get_selected_chat()
        for chat in self.data.chat_list.data:
            if chat['id'] == selected_id:
                return chat
        return None

    def update(self, chat_messages: ObservableList):
        chat_info = self.selected_chat_info()
        text = ""
        if chat_info:
            if chat_info['is_group']:
                text = chat_info['name']
            text += f" ({chat_info['members']})"
        self.clear()  
        self.configure(label_text=text)
        w = self.winfo_width()
        i=0
        for message in chat_messages.data:
            if message['username'] != self.data.username :
                messframe = MessageFrame(self, self.data, message, "#53457A", 0.45*w)
                messframe.grid(row=i, column=0, sticky='w', padx=(0,10), pady=3)
                self.chathist.append(messframe)
            else:
                messframe = MessageFrame(self, self.data, message, "#455579", 0.45*w)
                messframe.grid(row=i, column=1, sticky='e', padx=(0,10), pady=3)
                self.chathist.append(messframe)
            i=i+1
        
        # чтобы отобразить последние сообщения
        self.update_idletasks() # обновить чтобы пересчитались размеры
        self._parent_canvas.yview_moveto(1.0)

class App(ctk.CTk):
    def __init__(self, username: str, usr_id: int, server_addr: str):
        super().__init__()
        self.title("NewGramm")
        self.geometry("800x500")

        self.grid_columnconfigure((2, 3, 4), weight=1)
        self.grid_rowconfigure((0, 1, 2, 3, 4, 5), weight=1)

        self.SAVE_AUDIO_PATH = 'voice_record.wav'
        self.SAVE_VIDEO_PATH = 'temp_video.mp4'
        self.FINAL_PATH = 'final_video.mp4'
        
        self.data = Data(usr_id, username, server_addr)
        self.data.set_cb_selected_chat(self.on_selected_chat_change)
        self.data.set_cb_call(self.on_answ_call)

        self.chatlistframe = ChatListFrame(self, 'List of chats', self.data)
        self.chatlistframe.grid(row=0, column=0, sticky='nsew', rowspan=7, columnspan=2)

        self.input = ctk.CTkEntry(self, placeholder_text="Enter the message...")
        self.input.grid(row=6, column=2, sticky='sew', columnspan=3)
        self.input.bind('<Return>', async_handler(lambda event: self.on_text_send()))

        self.sendbutton = ctk.CTkButton(self, text="Send", width=40, command=async_handler(lambda: self.on_text_send()), fg_color="#4D86D1", hover_color="#4070AF", state='disabled')
        self.sendbutton.grid(row=6, column=5, sticky='s')

        self.record_audio_event = asyncio.Event()
        self.audiobutton = ctk.CTkButton(self, corner_radius=20, width=40, text="🎤", command=async_handler(lambda: self.on_audio_click()), state='disabled')
        self.audiobutton.grid(row=6, column=6, sticky='s')

        # проверка наличия микрофона
        self.mic_exists = my_player.mic_exists()

        self.record_video_event = asyncio.Event()
        self.videobutton = ctk.CTkButton(self, corner_radius=20, width=40, text="🎥", command=async_handler(lambda: self.on_video_click()), state='disabled')
        self.videobutton.grid(row=6, column=7, sticky='s')

        # проверка наличия камеры
        self.cam_exists = my_player.cam_exists()

        # кнопка вызова
        self.callbutton = ctk.CTkButton(self, corner_radius=20, width=40, text="📞", command=self.on_call, state='disabled')
        self.callbutton.grid(row=6, column=8, sticky='s')

        self.chatframe = ChatFrame(self, "", self.data)
        self.chatframe.grid(row=0, column=2, sticky='nsew', columnspan=7, rowspan=6)

        # нельзя сразу тк основной цикл событий еще не создан
        try:
            self.after(100, lambda: asyncio.create_task(self.data.get_chats()))
            self.after(100, lambda: asyncio.create_task(self.data.get_updates()))
        except RuntimeError:
            self.after(1000, lambda: asyncio.create_task(self.data.get_chats()))
            self.after(1000, lambda: asyncio.create_task(self.data.get_updates()))

    def on_selected_chat_change(self, prev: int | None, curr: int | None):
        info = self.data.get_chat_info(curr)
        if self.mic_exists and info['is_group'] == False:
            self.callbutton.configure(state='normal')
        else:
            self.callbutton.configure(state='disabled')

        if prev is None and curr is not None:
            self.sendbutton.configure(state='normal')
            if self.mic_exists:
                self.audiobutton.configure(state='normal')
            if self.cam_exists:
                self.videobutton.configure(state='normal')

    async def on_text_send(self):
        await self.data.send_message(type='text', text=self.input.get())
        self.input.delete(0, 'end')

    async def on_audio_click(self):
        if not self.record_audio_event.is_set():
            self.record_audio_event.set()

            self.audiobutton.configure(text="⏹")
            asyncio.create_task(self.record_and_send_audio())
        else:
            self.record_audio_event.clear()
            self.audiobutton.configure(text="🎤")

    async def record_and_send_audio(self):
        await my_player.record_audio(self.record_audio_event, self.SAVE_AUDIO_PATH)
        await self.data.send_message(type='audio', filepath=self.SAVE_AUDIO_PATH)

    async def on_video_click(self):
        if not self.record_video_event.is_set():
            self.record_video_event.set()
            
            self.videobutton.configure(text="⏹")
            asyncio.create_task(self.record_and_send_video())
        else:
            self.record_video_event.clear()
            self.videobutton.configure(text="🎥")
            # когда цикл в record_video и record_audio увидит self.record_video_state = False, 
            # он завершится, и начнется процесс склейки.

    async def record_and_send_video(self):
        FPS = 15.0
        # чтобы не тратить время в функции записи, и не было рассинхрона
        # из-за того что запись видео началась позже аудио
        init_pair = my_player.init_video(FPS, self.SAVE_VIDEO_PATH)
        
        # запускаем две задачи одновременно
        await asyncio.gather(
            my_player.record_video(init_pair, self.record_video_event, FPS),
            my_player.record_audio(self.record_video_event, self.SAVE_AUDIO_PATH))

        my_player.merge_audio_video(self.SAVE_VIDEO_PATH, self.SAVE_AUDIO_PATH, self.FINAL_PATH)
        await self.data.send_message(type='video', filepath=self.FINAL_PATH)

    def on_call(self):
        self.call_window = CallWindow(self, self.data, self.data.get_selected_chat(), "init")

    def on_answ_call(self, chat_id: int):
        self.call_window = CallWindow(self, self.data, chat_id, "answer")

    def on_closing(self):
        # потому что вылазят tkinter исключениях про after штуки когда eventloop уже нет
        try:
            for after_id in self.tk.call('after', 'info').split():
                self.after_cancel(after_id)
        except Exception:
            pass
        
        async def close_and_destroy():
            await self.data.close()
            self.destroy()
        
        asyncio.create_task(close_and_destroy())

def main(server_addr: str):
    entr = Entrance(server_addr)
    entr.protocol("WM_DELETE_WINDOW", async_handler(entr.on_close))
    entr.update()
    async_mainloop(entr)

    if entr.usr_data:
        username = entr.usr_data['username']
        token = entr.usr_data['token']
        app = App(username, token, server_addr)
        app.update()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        async_mainloop(app)

if __name__=='__main__':
    base_dir = ''
    if getattr(sys, 'frozen', False):
        # Это EXE: ищем файлы рядом с exe
        # Иначе будет искать в распакованном exe где-то во временных файлах
        base_dir = Path(sys.executable).parent
    else:
        # Это скрипт: ищем файлы рядом со скриптом
        base_dir = Path(__file__).parent
    addr_file = base_dir / 'server_addr.txt'
    print(addr_file)
    if not addr_file.exists():
        print(f"File with server addr wasn't found. Add {addr_file}")
    else:
        with addr_file.open('rt') as f:
            addr = f.readline()
            print('success')
        print(f"Server addr {addr}")
        main(addr)