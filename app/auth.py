#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль аутентификации и авторизации.
Обеспечивает безопасный доступ к веб-интерфейсу.
"""

import os
import json
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
import logging
from typing import Optional, Dict, Any
import bcrypt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthManager:
    """Менеджер аутентификации пользователей"""
    
    def __init__(self, config_path='config.yaml'):
        self.config = self._load_config(config_path)
        self.users_file = 'users.json'
        self.sessions = {}
        self.failed_attempts = {}
        self.max_attempts = 5
        self.lockout_time = 300  # 5 минут
        self.session_timeout = self.config.get('web', {}).get('session_timeout', 3600)
        
        # Инициализация пользователей
        self._init_users()
    
    def _load_config(self, config_path):
        """Загрузка конфигурации"""
        import yaml
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except:
            return {}
    
    def _init_users(self):
        """Инициализация файла пользователей"""
        if not os.path.exists(self.users_file):
            # Создаём файл с пользователем по умолчанию
            default_user = {
                'username': 'admin',
                'password_hash': self.hash_password('admin123'),  # Сменить при первом входе!
                'email': 'admin@example.com',
                'role': 'admin',
                'created_at': datetime.now().isoformat(),
                'last_login': None,
                'is_active': True
            }
            
            self._save_users({'admin': default_user})
            logger.warning("Default user created: admin/admin123 - CHANGE PASSWORD!")
    
    def _load_users(self) -> Dict[str, Dict]:
        """Загрузка пользователей из файла"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load users: {e}")
        return {}
    
    def _save_users(self, users: Dict[str, Dict]):
        """Сохранение пользователей в файл"""
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save users: {e}")
    
    def hash_password(self, password: str) -> str:
        """Хеширование пароля с использованием bcrypt"""
        # Генерируем соль и хешируем пароль
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        return password_hash.decode('utf-8')
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Проверка пароля"""
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                password_hash.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False
    
    def check_auth(self, username: str, password: str) -> bool:
        """
        Проверка учетных данных пользователя
        Возвращает True при успешной аутентификации
        """
        # Проверка блокировки аккаунта
        if self.is_account_locked(username):
            logger.warning(f"Account locked for user: {username}")
            return False
        
        # Загружаем пользователей
        users = self._load_users()
        user = users.get(username)
        
        if not user:
            # Несуществующий пользователь - всё равно считаем попытку
            self.record_failed_attempt(username)
            logger.warning(f"Login attempt for non-existent user: {username}")
            return False
        
        if not user.get('is_active', True):
            logger.warning(f"Inactive user attempted login: {username}")
            return False
        
        # Проверяем пароль
        password_hash = user.get('password_hash', '')
        if self.verify_password(password, password_hash):
            # Успешный вход
            self.clear_failed_attempts(username)
            
            # Обновляем время последнего входа
            user['last_login'] = datetime.now().isoformat()
            users[username] = user
            self._save_users(users)
            
            logger.info(f"Successful login for user: {username}")
            return True
        else:
            # Неверный пароль
            self.record_failed_attempt(username)
            logger.warning(f"Failed login attempt for user: {username}")
            return False
    
    def record_failed_attempt(self, username: str):
        """Запись неудачной попытки входа"""
        now = time.time()
        
        if username not in self.failed_attempts:
            self.failed_attempts[username] = []
        
        self.failed_attempts[username].append(now)
        
        # Оставляем только последние попытки за период блокировки
        cutoff = now - self.lockout_time
        self.failed_attempts[username] = [
            attempt for attempt in self.failed_attempts[username]
            if attempt > cutoff
        ]
    
    def clear_failed_attempts(self, username: str):
        """Очистка неудачных попыток"""
        if username in self.failed_attempts:
            del self.failed_attempts[username]
    
    def is_account_locked(self, username: str) -> bool:
        """Проверка, заблокирован ли аккаунт"""
        if username not in self.failed_attempts:
            return False
        
        attempts = self.failed_attempts[username]
        now = time.time()
        cutoff = now - self.lockout_time
        
        # Считаем только последние попытки
        recent_attempts = [a for a in attempts if a > cutoff]
        
        if len(recent_attempts) >= self.max_attempts:
            # Аккаунт заблокирован
            lockout_until = max(recent_attempts) + self.lockout_time
            remaining = lockout_until - now
            
            if remaining > 0:
                logger.warning(
                    f"Account {username} locked for {int(remaining)} seconds"
                )
                return True
        
        return False
    
    def create_session(self, username: str, client_ip: str = None) -> str:
        """Создание новой сессии"""
        session_id = secrets.token_urlsafe(32)
        
        session_data = {
            'username': username,
            'created_at': time.time(),
            'last_activity': time.time(),
            'client_ip': client_ip,
            'user_agent': None  # Можно добавить из запроса
        }
        
        self.sessions[session_id] = session_data
        logger.info(f"Session created for {username}: {session_id[:8]}...")
        
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[Dict]:
        """Проверка валидности сессии"""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        now = time.time()
        
        # Проверка таймаута сессии
        if now - session['last_activity'] > self.session_timeout:
            logger.info(f"Session expired: {session_id[:8]}...")
            del self.sessions[session_id]
            return None
        
        # Обновляем время последней активности
        session['last_activity'] = now
        self.sessions[session_id] = session
        
        return session
    
    def destroy_session(self, session_id: str):
        """Уничтожение сессии"""
        if session_id in self.sessions:
            username = self.sessions[session_id].get('username', 'unknown')
            del self.sessions[session_id]
            logger.info(f"Session destroyed for {username}: {session_id[:8]}...")
    
    def cleanup_expired_sessions(self):
        """Очистка просроченных сессий"""
        now = time.time()
        expired = []
        
        for session_id, session in self.sessions.items():
            if now - session['last_activity'] > self.session_timeout:
                expired.append(session_id)
        
        for session_id in expired:
            del self.sessions[session_id]
        
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
    
    def create_user(self, username: str, password: str, 
                   email: str = None, role: str = 'user') -> bool:
        """Создание нового пользователя"""
        users = self._load_users()
        
        if username in users:
            logger.warning(f"User already exists: {username}")
            return False
        
        # Создаём нового пользователя
        new_user = {
            'username': username,
            'password_hash': self.hash_password(password),
            'email': email or f"{username}@example.com",
            'role': role,
            'created_at': datetime.now().isoformat(),
            'last_login': None,
            'is_active': True
        }
        
        users[username] = new_user
        self._save_users(users)
        
        logger.info(f"User created: {username}")
        return True
    
    def update_user(self, username: str, updates: Dict[str, Any]) -> bool:
        """Обновление информации о пользователе"""
        users = self._load_users()
        
        if username not in users:
            logger.warning(f"User not found: {username}")
            return False
        
        user = users[username]
        
        # Обновляем разрешённые поля
        allowed_fields = ['email', 'role', 'is_active']
        
        for field, value in updates.items():
            if field in allowed_fields:
                user[field] = value
        
        users[username] = user
        self._save_users(users)
        
        logger.info(f"User updated: {username}")
        return True
    
    def change_password(self, username: str, 
                       current_password: str, 
                       new_password: str) -> bool:
        """Смена пароля пользователя"""
        users = self._load_users()
        
        if username not in users:
            return False
        
        user = users[username]
        
        # Проверяем текущий пароль
        if not self.verify_password(current_password, user['password_hash']):
            logger.warning(f"Wrong current password for: {username}")
            return False
        
        # Устанавливаем новый пароль
        user['password_hash'] = self.hash_password(new_password)
        users[username] = user
        self._save_users(users)
        
        logger.info(f"Password changed for: {username}")
        return True
    
    def get_user_info(self, username: str) -> Optional[Dict]:
        """Получение информации о пользователе"""
        users = self._load_users()
        return users.get(username)
    
    def get_all_users(self) -> Dict[str, Dict]:
        """Получение списка всех пользователей"""
        return self._load_users()


# Декораторы для Flask

def login_required(f):
    """Декоратор для проверки аутентификации в Flask"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session, redirect, url_for
        
        auth = AuthManager()
        
        # Проверяем сессию
        session_id = session.get('session_id')
        user_session = auth.validate_session(session_id) if session_id else None
        
        if not user_session:
            # Сессия недействительна
            if session_id:
                auth.destroy_session(session_id)
                session.pop('session_id', None)
            
            return redirect(url_for('login'))
        
        # Обновляем сессию в Flask
        session['username'] = user_session['username']
        session['session_id'] = session_id
        
        return f(*args, **kwargs)
    
    return decorated_function


def admin_required(f):
    """Декоратор для проверки прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session, redirect, url_for, flash
        
        auth = AuthManager()
        
        # Проверяем сессию
        session_id = session.get('session_id')
        user_session = auth.validate_session(session_id) if session_id else None
        
        if not user_session:
            return redirect(url_for('login'))
        
        # Проверяем роль пользователя
        username = user_session['username']
        user_info = auth.get_user_info(username)
        
        if not user_info or user_info.get('role') != 'admin':
            flash('Требуются права администратора', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    
    return decorated_function


# Глобальный экземпляр
auth_manager = AuthManager()

# Функция для прямого использования в других модулях
def check_auth(username: str, password: str) -> bool:
    """Проверка учетных данных (для использования в app.py)"""
    return auth_manager.check_auth(username, password)
