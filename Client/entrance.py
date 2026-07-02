import customtkinter as ctk
import httpx
from CTkMessagebox import CTkMessagebox
from async_tkinter_loop import async_handler, async_mainloop
import asyncio

class Entrance(ctk.CTk):
    def __init__(self, server_addr: str):
        super().__init__()
        self.title("Entrance")
        self.geometry("300x320")

        self.client = httpx.AsyncClient(base_url=f"http://{server_addr}")
        self.usr_data = None

        self.tabview = ctk.CTkTabview(self, width=250)
        self.tabview.pack()

        # вход
        self.login_tab = self.tabview.add("Sign In")
        self.login_tab.columnconfigure((0, 1), weight=1)
        self.login_tab.rowconfigure((0, 1, 2, 3, 4), weight=1)

        self.login_usr_lbl = ctk.CTkLabel(self.login_tab, text="Username:")
        self.login_usr_lbl.grid(pady=(10, 0), row=0, column=0, sticky="nsew")
        self.login_usr_entry = ctk.CTkEntry(self.login_tab, placeholder_text="Enter here...")
        self.login_usr_entry.grid(pady=(10, 10), row=1, column=0, columnspan=2, sticky="nsew")

        self.login_pass_lbl = ctk.CTkLabel(self.login_tab, text="Password:  ")
        self.login_pass_lbl.grid(pady=(10, 0), row=2, column=0, sticky="nsw")
        self.login_pass_switch = ctk.CTkSwitch(self.login_tab, text='Show', command=self.toggle_password)
        self.login_pass_switch.grid(pady=(10, 0), row=2, column=1, sticky="nse")
        self.login_pass_entry = ctk.CTkEntry(self.login_tab, placeholder_text="Enter here...", show="*")
        self.login_pass_entry.grid(pady=(10, 0), row=3, column=0, columnspan=2, sticky="nsew")

        self.login_btn = ctk.CTkButton(self.login_tab, text="Sign In", command=async_handler(lambda: self.on_login(self.login_usr_entry.get(), self.login_pass_entry.get())))
        self.login_btn.grid(pady=(20, 10), row=4, column=0, columnspan=2, sticky="nsew")

        # регистрация
        self.reg_tab = self.tabview.add("Sign Up")
        self.reg_tab.columnconfigure((0, 1), weight=1)
        self.reg_tab.rowconfigure((0, 1, 2, 3, 4, 5), weight=1)

        self.reg_usr_lbl = ctk.CTkLabel(self.reg_tab, text="Username:")
        self.reg_usr_lbl.grid(pady=(10, 0), row=0, column=0, sticky="nsw")
        self.reg_usr_entry = ctk.CTkEntry(self.reg_tab, placeholder_text="Enter here...")
        self.reg_usr_entry.grid(pady=(10, 0), row=1, column=0, columnspan=2, sticky="nsew")

        self.reg_avail_btn = ctk.CTkButton(self.reg_tab, text="Check", command=async_handler(lambda: self.on_check_avail(self.reg_usr_entry.get())))
        self.reg_avail_btn.grid(pady=(10, 10), row=2, column=0, sticky="nsw")
        self.reg_avail_lbl = ctk.CTkLabel(self.reg_tab, text="Not available", text_color='red')
        self.reg_avail_lbl.grid(pady=(10, 10), row=2, column=1, sticky="nsew")

        self.reg_pass_lbl = ctk.CTkLabel(self.reg_tab, text="Password:")
        self.reg_pass_lbl.grid(pady=(10, 0), row=3, column=0, sticky="nsw")
        self.reg_pass_entry = ctk.CTkEntry(self.reg_tab, placeholder_text="Enter here...")
        self.reg_pass_entry.grid(pady=(10, 0), row=4, column=0, columnspan=2, sticky="nsew")

        self.reg_btn = ctk.CTkButton(self.reg_tab, text="Sign Up", command=async_handler(lambda: self.on_reg(self.reg_usr_entry.get(), self.reg_pass_entry.get())))
        self.reg_btn.grid(pady=(20, 10), row=5, column=0, columnspan=2, sticky="nsew")

    async def login(self, username: str, passw: str)-> str | None:
        resp = await self.client.post("/sign_in", json={'username': username, 'password': passw})
        if resp.status_code == 200:
            return resp.json()['token']
        else:
            return None
        
    async def check_exists(self, username: str)->bool:
        resp = await self.client.get("/username_exists", params={'username': username})
        return resp.json()['exists']
    
    async def reg(self, username: str, passw: str)-> str | None:
        resp = await self.client.post("/registration", json={'username': username, 'password': passw})
        if resp.status_code == 200:
            return resp.json()['token']
        else:
            return None
        
    def toggle_password(self):
        if self.login_pass_switch.get() == 1:
            self.login_pass_entry.configure(show='')
        else:
            self.login_pass_entry.configure(show="*")

    async def on_login(self, username: str, passw: str):
        res = await self.login(username, passw)
        if res:
            self.on_success(username, res)
        else:
            CTkMessagebox(self, title="Error", message="Incorrect username or password", icon="cancel")

    async def on_check_avail(self, username: str):
        res = await self.check_exists(username)
        if not res and username != "":
            self.reg_avail_lbl.configure(text="Available", text_color='green')
        else:
            self.reg_avail_lbl.configure(text="Not available", text_color='red')

    async def on_reg(self, username: str, passw: str):
        res = await self.reg(username, passw)
        if res:
            self.on_success(username, res)
        else:
            await self.on_check_avail(username)  # если проблема во время регистрации в юзернейме это высветится
            CTkMessagebox(self, title="Error", message="Registration failed", icon="cancel")

    def on_success(self, username: str, token: str):
        print(f"usrname: {username}, 'token': {token}")
        self.usr_data = {'username': username, 'token': token}
        asyncio.create_task(self.on_close())

    async def on_close(self):
        await self.client.aclose()
        self.destroy()

if __name__ == '__main__':
    app = Entrance()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.update()
    async_mainloop(app)