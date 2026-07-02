INSERT INTO users (username, password)
VALUES ('ann', '1181');

SELECT *
FROM chat_names;

SELECT id
FROM users
WHERE username = 'rootb' AND password = '1234';

SELECT id
FROM users
WHERE username = 'root';

INSERT INTO chat_names (name, is_group)
VALUES (NULL, FALSE);
SELECT last_insert_id();

INSERT INTO chat_members (chat_id, user_id)
SELECT 1, id
FROM users
WHERE username IN ('root', 'maria', 'm');

SELECT chat_id
FROM chat_members
WHERE user_id = 6;

INSERT INTO messages (text, chat_id, sender_id)
VALUES ("hello", 10, 6);

SELECT user_id
FROM chat_members
WHERE chat_id = 1;

SELECT VERSION() as mysql_version, NOW() as server_time, USER() as 'current_user';

SELECT 
DATABASE() as database_name,
COUNT(*) as table_count 
FROM information_schema.tables 
WHERE table_schema = DATABASE();

WITH chat_info AS
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
WHERE user_id = 6;

SELECT n.id, n.name, n.is_group,
GROUP_CONCAT(u.username SEPARATOR ', ') members
FROM chat_names n
RIGHT JOIN chat_members m
	ON n.id = m.chat_id
LEFT JOIN users u
	ON u.id = m.user_id
GROUP BY m.chat_id
;

SELECT id
FROM users
WHERE id = 8;

SELECT m.text, m.sended_at, u.username
FROM messages m
LEFT JOIN users u
	ON m.sender_id = u.id
WHERE chat_id = 1;

SELECT id FROM chat_names WHERE id = 8;