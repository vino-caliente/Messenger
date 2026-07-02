import aiomysql
import aiomysql.cursors

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Anastasia#3238', # на ноуте (3238) и компе (Anastasia#3238) разный!
    'db': 'messenger_db',
    'cursorclass': aiomysql.cursors.DictCursor
}

async def __check_db_content(pool: aiomysql.Pool):
    # для таблицы users
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM users")
            descr = cur.description
            print(descr[0][0], descr[1][0], descr[2][0], descr[3][0])
            rows = await cur.fetchall()
            for row in rows:
                print(row['id'], row['username'], row['password'], row['created_at'])

async def get_user(pool: aiomysql.Pool, username: str)-> tuple[str, int]|None:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            nrows = await cur.execute("SELECT password_hash, id FROM users WHERE username = %s", (username,))
            if nrows == 0:
                return None
            else:
                row = await cur.fetchone()
                return row["password_hash"], row["id"]
        
async def check_if_exists(pool: aiomysql.Pool, username: str)->bool:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            nrows = await cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            if nrows > 0:
                return True
            else:
                return False
        
async def add_user(pool: aiomysql.Pool, username: str, password_hash: str)->int:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # если nrow не 1, а 0 значит не добавилось
            nrow = await cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, password_hash))
            await conn.commit()
            id = cur.lastrowid
            return id

async def create_chat(pool: aiomysql.Pool, username_list: list[str], chat_name: str | None, is_group: bool)->tuple[int, list[int]]:
    str_username_list = "'" + "', '".join(username_list) + "'"
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO chat_names (name, is_group) VALUES (%s, %s)", (chat_name, is_group))
            await conn.commit()
            id = cur.lastrowid

            await cur.execute("INSERT INTO chat_members (chat_id, user_id) SELECT %s, id FROM users WHERE username IN (" + str_username_list + ")", (id,))
            await conn.commit()

            await cur.execute("SELECT user_id FROM chat_members WHERE chat_id = %s", (id,))
            data = await cur.fetchall()
            lst = []
            for d in data:
                lst.append(d['user_id'])
            return id, lst
        
async def send_message(pool: aiomysql.Pool, sender_id: int, chat_id: int, type: str, text: str)-> tuple[int, list[int]] | None:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute('SELECT user_id FROM chat_members WHERE chat_id = %s', (chat_id,))
            data = await cur.fetchall()
            chat_members = []
            for d in data:
                chat_members.append(d['user_id'])
            if len(chat_members)==0 or sender_id not in chat_members:
                return None
            
            await cur.execute("INSERT INTO messages (type, text, chat_id, sender_id) VALUES (%s, %s, %s, %s)", (type, text, chat_id, sender_id))
            await conn.commit()
            message_id = cur.lastrowid
            return message_id, chat_members
        
async def get_message_info(pool: aiomysql.Pool, message_id: int)-> dict | None:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            nrows = await cur.execute('SELECT type, text FROM messages WHERE id = %s', (message_id,))
            if nrows < 1:
                return None
            data = await cur.fetchone()
            return data
        
async def get_username_by_id(pool: aiomysql.Pool, user_id: int)-> str | None:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            nrows = await cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            if nrows < 1:
                return None
            sender_username = await cur.fetchone()
            return sender_username['username']
        
async def get_chat_list(pool: aiomysql.Pool, user_id: int)->list | None:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            nrows = await cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if nrows == 0:
                return None
            await cur.execute('''WITH chat_info AS
                                (
                                    SELECT n.id, n.name, n.is_group,
                                    GROUP_CONCAT(u.username SEPARATOR ', ') members
                                    FROM chat_names n
                                    RIGHT JOIN chat_members m
                                        ON n.id = m.chat_id
                                    LEFT JOIN users u
                                        ON u.id = m.user_id
                                    GROUP BY m.chat_id
                                )
                                SELECT info.id, info.name, info.is_group, info.members
                                FROM chat_members memb
                                JOIN chat_info info
                                    ON memb.chat_id = info.id
                                WHERE user_id = %s''', (user_id,))
            data = await cur.fetchall()
            return data

async def get_chat_messages(pool: aiomysql.Pool, chat_id: int)->list | None:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            nrows = await cur.execute("SELECT id FROM chat_names WHERE id = %s", (chat_id,))
            if nrows == 0:
                return None
            await cur.execute('''SELECT m.id, m.type, m.text, m.sended_at, u.username
                                FROM messages m
                                LEFT JOIN users u
                                    ON m.sender_id = u.id
                                WHERE chat_id = %s''', (chat_id,))
            data = await cur.fetchall()
            return data

# собеседник sender_id в chat_id 
async def get_peer_id(pool: aiomysql.Pool, sender_id: int, chat_id: int)->int | None:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            nrows = await cur.execute("SELECT user_id FROM chat_members WHERE chat_id = %s AND user_id != %s", (chat_id, sender_id))
            if nrows != 1:
                return None
            data = await cur.fetchone()
            return data['user_id']

if __name__=='__main__':
    pass