#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Система мониторинга задач и производительности.
Отслеживает выполнение задач, собирает метрики и логи.
"""

import os
import json
import time
import threading
import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque
import psutil
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
import queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskMonitor:
    """Мониторинг выполнения задач"""
    
    def __init__(self, db_path='monitoring.db'):
        self.db_path = db_path
        self.task_queue = queue.Queue()
        self.active_tasks = {}
        self.task_history = deque(maxlen=1000)
        self.metrics = {}
        self.alerts = deque(maxlen=100)
        self.init_database()
        self.start_monitoring()
    
    def init_database(self):
        """Инициализация базы данных для мониторинга"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица задач
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            task_type TEXT NOT NULL,
            status TEXT NOT NULL,
            user TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            duration REAL,
            result_path TEXT,
            error_message TEXT,
            parameters TEXT
        )
        ''')
        
        # Таблица метрик системы
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cpu_percent REAL,
            memory_percent REAL,
            disk_usage_percent REAL,
            network_sent_mb REAL,
            network_recv_mb REAL,
            active_tasks INTEGER,
            queue_size INTEGER
        )
        ''')
        
        # Таблица ошибок
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            task_id TEXT,
            error_type TEXT,
            error_message TEXT,
            stack_trace TEXT,
            resolved BOOLEAN DEFAULT FALSE
        )
        ''')
        
        # Таблица предупреждений
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            alert_type TEXT NOT NULL,
            alert_level TEXT NOT NULL,
            message TEXT NOT NULL,
            acknowledged BOOLEAN DEFAULT FALSE,
            acknowledged_by TEXT,
            acknowledged_at TIMESTAMP
        )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Monitoring database initialized")
    
    def start_monitoring(self):
        """Запуск фонового мониторинга"""
        # Мониторинг системы
        self.monitor_thread = threading.Thread(
            target=self._system_monitor_loop,
            daemon=True
        )
        self.monitor_thread.start()
        
        # Очистка старых данных
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True
        )
        self.cleanup_thread.start()
        
        logger.info("Monitoring system started")
    
    def _system_monitor_loop(self):
        """Фоновый сбор метрик системы"""
        import time
        
        while True:
            try:
                self.collect_system_metrics()
                time.sleep(60)  # Сбор каждые 60 секунд
            except Exception as e:
                logger.error(f"System monitor error: {e}")
                time.sleep(300)  # При ошибке ждём 5 минут
    
    def _cleanup_loop(self):
        """Фоновая очистка старых данных"""
        import time
        
        while True:
            try:
                self.cleanup_old_data()
                time.sleep(3600)  # Очистка каждый час
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                time.sleep(7200)  # При ошибке ждём 2 часа
    
    def collect_system_metrics(self):
        """Сбор метрик системы"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Память
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Диск
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Сеть
            net_io = psutil.net_io_counters()
            network_sent_mb = net_io.bytes_sent / (1024 * 1024)
            network_recv_mb = net_io.bytes_recv / (1024 * 1024)
            
            # Сохраняем в базу
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO system_metrics 
            (cpu_percent, memory_percent, disk_usage_percent, 
             network_sent_mb, network_recv_mb, active_tasks, queue_size)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                cpu_percent,
                memory_percent,
                disk_percent,
                network_sent_mb,
                network_recv_mb,
                len(self.active_tasks),
                self.task_queue.qsize()
            ))
            
            conn.commit()
            conn.close()
            
            # Сохраняем в память для быстрого доступа
            self.metrics['last_collection'] = datetime.now().isoformat()
            self.metrics['cpu'] = cpu_percent
            self.metrics['memory'] = memory_percent
            self.metrics['disk'] = disk_percent
            self.metrics['network_sent_mb'] = network_sent_mb
            self.metrics['network_recv_mb'] = network_recv_mb
            
            # Проверяем пороговые значения
            self.check_thresholds()
            
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
    
    def check_thresholds(self):
        """Проверка пороговых значений для генерации предупреждений"""
        thresholds = {
            'cpu': 90,        # CPU > 90%
            'memory': 85,     # Память > 85%
            'disk': 90,       # Диск > 90%
            'queue': 50       # Очередь > 50 задач
        }
        
        if self.metrics.get('cpu', 0) > thresholds['cpu']:
            self.create_alert(
                'high_cpu_usage',
                'warning',
                f"Высокая загрузка CPU: {self.metrics['cpu']}%"
            )
        
        if self.metrics.get('memory', 0) > thresholds['memory']:
            self.create_alert(
                'high_memory_usage',
                'warning',
                f"Высокая загрузка памяти: {self.metrics['memory']}%"
            )
        
        if self.metrics.get('disk', 0) > thresholds['disk']:
            self.create_alert(
                'high_disk_usage',
                'critical',
                f"Высокая загрузка диска: {self.metrics['disk']}%"
            )
        
        if self.task_queue.qsize() > thresholds['queue']:
            self.create_alert(
                'large_queue',
                'warning',
                f"Большая очередь задач: {self.task_queue.qsize()}"
            )
    
    def create_alert(self, alert_type: str, level: str, message: str):
        """Создание предупреждения"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'type': alert_type,
            'level': level,
            'message': message,
            'acknowledged': False
        }
        
        self.alerts.append(alert)
        
        # Сохраняем в базу
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO alerts (alert_type, alert_level, message)
        VALUES (?, ?, ?)
        ''', (alert_type, level, message))
        
        conn.commit()
        conn.close()
        
        logger.warning(f"Alert created: {level} - {message}")
        
        # TODO: Отправка уведомлений (email, telegram и т.д.)
    
    def log_task(self, task_id: str, task_type: str, status: str, 
                user: str = None, parameters: Dict = None):
        """Логирование задачи"""
        task_data = {
            'task_id': task_id,
            'task_type': task_type,
            'status': status,
            'user': user,
            'timestamp': datetime.now().isoformat(),
            'parameters': parameters or {}
        }
        
        # Сохраняем в историю
        self.task_history.append(task_data)
        
        # Сохраняем в базу
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if status == 'created':
            cursor.execute('''
            INSERT INTO tasks (task_id, task_type, status, user, parameters)
            VALUES (?, ?, ?, ?, ?)
            ''', (
                task_id,
                task_type,
                status,
                user,
                json.dumps(parameters, ensure_ascii=False) if parameters else None
            ))
        
        elif status == 'started':
            cursor.execute('''
            UPDATE tasks 
            SET status = ?, started_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            ''', (status, task_id))
        
        elif status in ['completed', 'failed', 'cancelled']:
            cursor.execute('''
            UPDATE tasks 
            SET status = ?, completed_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            ''', (status, task_id))
            
            # Вычисляем длительность выполнения
            cursor.execute('''
            UPDATE tasks 
            SET duration = (
                SELECT CAST(
                    (julianday(completed_at) - julianday(started_at)) * 86400.0 
                    AS REAL
                )
            )
            WHERE task_id = ? AND started_at IS NOT NULL AND completed_at IS NOT NULL
            ''', (task_id,))
        
        conn.commit()
        conn.close()
        
        # Обновляем активные задачи
        if status == 'started':
            self.active_tasks[task_id] = task_data
        elif status in ['completed', 'failed', 'cancelled']:
            self.active_tasks.pop(task_id, None)
        
        logger.info(f"Task logged: {task_id} - {task_type} - {status}")
    
    def update_task_result(self, task_id: str, result_path: str = None, 
                          error_message: str = None):
        """Обновление результата задачи"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if error_message:
            cursor.execute('''
            UPDATE tasks 
            SET error_message = ?, status = 'failed'
            WHERE task_id = ?
            ''', (error_message, task_id))
            
            # Логируем ошибку
            self.log_error(task_id, 'task_error', error_message)
        else:
            cursor.execute('''
            UPDATE tasks 
            SET result_path = ?, status = 'completed'
            WHERE task_id = ?
            ''', (result_path, task_id))
        
        conn.commit()
        conn.close()
    
    def log_error(self, task_id: str, error_type: str, 
                 error_message: str, stack_trace: str = None):
        """Логирование ошибки"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO errors (task_id, error_type, error_message, stack_trace)
        VALUES (?, ?, ?, ?)
        ''', (task_id, error_type, error_message, stack_trace))
        
        conn.commit()
        conn.close()
        
        logger.error(f"Error logged for task {task_id}: {error_message}")
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Получение статуса задачи"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM tasks WHERE task_id = ?
        ''', (task_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_recent_tasks(self, limit: int = 50) -> List[Dict]:
        """Получение последних задач"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM tasks 
        ORDER BY created_at DESC 
        LIMIT ?
        ''', (limit,))
        
        tasks = []
        for row in cursor.fetchall():
            task_dict = dict(row)
            
            # Парсим параметры
            if task_dict.get('parameters'):
                try:
                    task_dict['parameters'] = json.loads(task_dict['parameters'])
                except:
                    task_dict['parameters'] = {}
            
            tasks.append(task_dict)
        
        conn.close()
        return tasks
    
    def get_active_tasks(self) -> List[Dict]:
        """Получение активных задач"""
        return list(self.active_tasks.values())
    
    def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Получение статистики за указанный период"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # Общая статистика
        cursor.execute('''
        SELECT 
            COUNT(*) as total_tasks,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled,
            AVG(duration) as avg_duration
        FROM tasks 
        WHERE created_at >= datetime('now', ?)
        ''', (f'-{days} days',))
        
        row = cursor.fetchone()
        if row:
            stats['total_tasks'] = row[0] or 0
            stats['completed'] = row[1] or 0
            stats['failed'] = row[2] or 0
            stats['cancelled'] = row[3] or 0
            stats['avg_duration'] = row[4] or 0
            stats['success_rate'] = (
                (row[1] / row[0] * 100) if row[0] > 0 else 0
            )
        
        # Статистика по типам задач
        cursor.execute('''
        SELECT 
            task_type,
            COUNT(*) as count,
            AVG(duration) as avg_duration,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM tasks 
        WHERE created_at >= datetime('now', ?)
        GROUP BY task_type
        ''', (f'-{days} days',))
        
        stats['by_type'] = {}
        for row in cursor.fetchall():
            stats['by_type'][row[0]] = {
                'count': row[1],
                'avg_duration': row[2] or 0,
                'completed': row[3],
                'success_rate': (row[3] / row[1] * 100) if row[1] > 0 else 0
            }
        
        # Статистика по часам
        cursor.execute('''
        SELECT 
            strftime('%H', created_at) as hour,
            COUNT(*) as task_count
        FROM tasks 
        WHERE created_at >= datetime('now', ?)
        GROUP BY strftime('%H', created_at)
        ORDER BY hour
        ''', (f'-{days} days',))
        
        stats['by_hour'] = {}
        for row in cursor.fetchall():
            stats['by_hour'][row[0]] = row[1]
        
        conn.close()
        
        # Добавляем текущие метрики
        stats['current'] = {
            'active_tasks': len(self.active_tasks),
            'queue_size': self.task_queue.qsize(),
            'cpu': self.metrics.get('cpu', 0),
            'memory': self.metrics.get('memory', 0),
            'disk': self.metrics.get('disk', 0)
        }
        
        return stats
    
    def get_system_metrics_history(self, hours: int = 24) -> List[Dict]:
        """Получение истории метрик системы"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM system_metrics 
        WHERE timestamp >= datetime('now', ?)
        ORDER BY timestamp ASC
        ''', (f'-{hours} hours',))
        
        metrics = []
        for row in cursor.fetchall():
            metrics.append(dict(row))
        
        conn.close()
        return metrics
    
    def get_recent_alerts(self, limit: int = 20) -> List[Dict]:
        """Получение последних предупреждений"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM alerts 
        ORDER BY timestamp DESC 
        LIMIT ?
        ''', (limit,))
        
        alerts = []
        for row in cursor.fetchall():
            alerts.append(dict(row))
        
        conn.close()
        return alerts
    
    def acknowledge_alert(self, alert_id: int, username: str):
        """Подтверждение предупреждения"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE alerts 
        SET acknowledged = TRUE,
            acknowledged_by = ?,
            acknowledged_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''', (username, alert_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Alert {alert_id} acknowledged by {username}")
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Очистка старых данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = f'-{days_to_keep} days'
        
        # Очищаем старые задачи
        cursor.execute('''
        DELETE FROM tasks 
        WHERE created_at < datetime('now', ?)
        ''', (cutoff_date,))
        
        tasks_deleted = cursor.rowcount
        
        # Очищаем старые метрики (оставляем только за 7 дней)
        cursor.execute('''
        DELETE FROM system_metrics 
        WHERE timestamp < datetime('now', '-7 days')
        ''')
        
        metrics_deleted = cursor.rowcount
        
        # Очищаем старые ошибки (оставляем подтверждённые за 90 дней)
        cursor.execute('''
        DELETE FROM errors 
        WHERE timestamp < datetime('now', '-90 days') 
        AND resolved = TRUE
        ''')
        
        errors_deleted = cursor.rowcount
        
        # Очищаем старые предупреждения (оставляем подтверждённые за 30 дней)
        cursor.execute('''
        DELETE FROM alerts 
        WHERE timestamp < datetime('now', ?) 
        AND acknowledged = TRUE
        ''', (cutoff_date,))
        
        alerts_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        if any([tasks_deleted, metrics_deleted, errors_deleted, alerts_deleted]):
            logger.info(
                f"Cleanup completed: "
                f"tasks={tasks_deleted}, "
                f"metrics={metrics_deleted}, "
                f"errors={errors_deleted}, "
                f"alerts={alerts_deleted}"
            )
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Получение данных для дашборда"""
        return {
            'stats': self.get_statistics(1),  # За последние 24 часа
            'active_tasks': self.get_active_tasks(),
            'recent_tasks': self.get_recent_tasks(10),
            'recent_alerts': self.get_recent_alerts(10),
            'system_metrics': self.metrics,
            'queue_size': self.task_queue.qsize()
        }


# Глобальный экземпляр
task_monitor = TaskMonitor()
