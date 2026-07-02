DROP DATABASE IF EXISTS `messenger_db`;

CREATE DATABASE `messenger_db`;
USE `messenger_db`;

CREATE TABLE users (
	id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chat_names (
	id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50), # null если личный чат
    is_group BOOLEAN DEFAULT FALSE
);

CREATE TABLE chat_members (
	chat_id INT,
	FOREIGN KEY (chat_id) REFERENCES chat_names(id),
    user_id INT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE messages (
	id INT AUTO_INCREMENT PRIMARY KEY,
	type ENUM('text', 'audio', 'video', 'file'),
	text TEXT, # текст сообщения или пользовательское имя файла
    sended_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    chat_id INT,
    FOREIGN KEY (chat_id) REFERENCES chat_names(id),
    sender_id INT,
    FOREIGN KEY (sender_id) REFERENCES users(id)
);