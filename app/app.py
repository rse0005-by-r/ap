#!/usr/bin/env python3
"""
Media Automation System для развертывания на Nginx + Gunicorn
Production версия
"""

from flask import Flask, jsonify, request, send_from_directory
import json
import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
import logging

# ==================== НАСТРОЙКИ ====================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'production-secret-key-2024')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('media_automation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Пути
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"

# Создаем папки
for folder in [DATA_DIR, STATIC_DIR, UPLOADS_DIR, OUTPUTS_DIR]:
    folder.mkdir(exist_ok=True)

# JSON база данных
class TaskManager:
    def __init__(self):
        self.db_file = DATA_DIR / "tasks_db.json"
        self.tasks = self._load_db()
        self.lock = threading.Lock()
    
    def _load_db(self):
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка загрузки БД: {e}")
                return {"tasks": [], "next_id": 1, "stats": {}}
        return {"tasks": [], "next_id": 1, "stats": {}}
    
    def _save_db(self):
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения БД: {e}")
    
    def create_task(self, name, task_type="image", description=""):
        with self.lock:
            task_id = self.tasks["next_id"]
            
            task = {
                "id": task_id,
                "name": name,
                "type": task_type,
                "description": description,
                "status": "pending",
                "progress": 0,
                "steps": [],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "result": None,
                "output_path": None
            }
            
            self.tasks["tasks"].append(task)
            self.tasks["next_id"] += 1
            
            # Обновляем статистику
            if "stats" not in self.tasks:
                self.tasks["stats"] = {}
            if task_type not in self.tasks["stats"]:
                self.tasks["stats"][task_type] = 0
            self.tasks["stats"][task_type] += 1
            
            self._save_db()
            logger.info(f"Создана задача #{task_id}: {name}")
            
            # Запускаем в фоне
            self._start_task_processing(task_id)
            
            return task
    
    def _start_task_processing(self, task_id):
        """Запуск обработки задачи в фоне"""
        def process():
            time.sleep(1)
            self.update_task(task_id, status="running", progress=10)
            
            # Симуляция различных этапов
            steps = [
                ("Анализ запроса", 20),
                ("Генерация промпта", 35),
                ("Создание изображений", 60),
                ("Апскейл", 80),
                ("Создание видео", 95),
                ("Финальная обработка", 100)
            ]
            
            for step_name, progress in steps:
                time.sleep(2)
                self.update_task(
                    task_id,
                    progress=progress,
                    steps=[*self.get_task(task_id).get("steps", []), step_name]
                )
            
            self.update_task(
                task_id,
                status="completed",
                result={
                    "message": "Задача успешно выполнена",
                    "images_generated": 4,
                    "video_created": True,
                    "output_path": f"/outputs/task_{task_id}.mp4"
                },
                output_path=f"/data/outputs/task_{task_id}.mp4"
            )
            logger.info(f"Задача #{task_id} завершена")
        
        thread = threading.Thread(target=process, daemon=True)
        thread.start()
    
    def update_task(self, task_id, **kwargs):
        with self.lock:
            for task in self.tasks["tasks"]:
                if task["id"] == task_id:
                    task.update(kwargs)
                    task["updated_at"] = datetime.now().isoformat()
                    self._save_db()
                    return True
            return False
    
    def get_task(self, task_id):
        for task in self.tasks["tasks"]:
            if task["id"] == task_id:
                return task
        return None
    
    def get_all_tasks(self, limit=50):
        tasks = sorted(self.tasks["tasks"], 
                      key=lambda x: x["created_at"], 
                      reverse=True)
        return tasks[:limit]
    
    def get_stats(self):
        stats = {
            "total_tasks": len(self.tasks["tasks"]),
            "completed": len([t for t in self.tasks["tasks"] if t["status"] == "completed"]),
            "running": len([t for t in self.tasks["tasks"] if t["status"] == "running"]),
            "pending": len([t for t in self.tasks["tasks"] if t["status"] == "pending"]),
            "by_type": self.tasks.get("stats", {})
        }
        return stats

# Инициализация менеджера задач
task_manager = TaskManager()

# ==================== ВЕБ-ИНТЕРФЕЙС ====================

@app.route('/')
def index():
    """Главная страница"""
    return '''
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Media Automation - Production</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                --primary: #4361ee;
                --secondary: #3a0ca3;
                --success: #4cc9f0;
                --dark: #1d3557;
            }
            body {
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                min-height: 100vh;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            .navbar {
                background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            }
            .card {
                border-radius: 15px;
                border: none;
                box-shadow: 0 5px 20px rgba(0,0,0,0.08);
                margin-bottom: 25px;
                transition: transform 0.3s;
            }
            .card:hover {
                transform: translateY(-5px);
            }
            .stat-card {
                text-align: center;
                padding: 25px 15px;
            }
            .stat-icon {
                font-size: 2.5rem;
                margin-bottom: 15px;
                opacity: 0.8;
            }
            .progress {
                height: 10px;
                border-radius: 5px;
            }
            .task-item {
                border-left: 4px solid var(--primary);
                transition: all 0.3s;
            }
            .task-item:hover {
                background-color: #f8f9fa;
                transform: translateX(5px);
            }
            .step-badge {
                font-size: 0.7rem;
                padding: 3px 8px;
                margin-right: 5px;
                margin-bottom: 5px;
            }
            .server-status {
                position: fixed;
                bottom: 20px;
                right: 20px;
                z-index: 1000;
            }
        </style>
    </head>
    <body>
        <!-- Навигация -->
        <nav class="navbar navbar-expand-lg navbar-dark">
            <div class="container">
                <a class="navbar-brand" href="/">
                    <i class="fas fa-robot me-2"></i>
                    <strong>Media Automation</strong>
                    <span class="badge bg-light text-dark ms-2">Production</span>
                </a>
                <div class="navbar-text">
                    <i class="fas fa-server me-1"></i>
                    <span id="serverStatus">Nginx + Flask</span>
                </div>
            </div>
        </nav>

        <!-- Основной контент -->
        <div class="container mt-4">
            <!-- Заголовок -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card bg-white">
                        <div class="card-body">
                            <h1 class="display-5 mb-3">🎬 Система автоматической генерации контента</h1>
                            <p class="lead mb-0">Production версия с Nginx и многопоточной обработкой</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Статистика -->
            <div class="row mb-4" id="statsRow">
                <div class="col-md-3">
                    <div class="card stat-card">
                        <div class="text-primary stat-icon">
                            <i class="fas fa-tasks"></i>
                        </div>
                        <h2 class="text-primary" id="totalTasks">0</h2>
                        <p class="text-muted">Всего задач</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card stat-card">
                        <div class="text-success stat-icon">
                            <i class="fas fa-check-circle"></i>
                        </div>
                        <h2 class="text-success" id="completedTasks">0</h2>
                        <p class="text-muted">Завершено</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card stat-card">
                        <div class="text-info stat-icon">
                            <i class="fas fa-sync-alt"></i>
                        </div>
                        <h2 class="text-info" id="runningTasks">0</h2>
                        <p class="text-muted">В процессе</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card stat-card">
                        <div class="text-warning stat-icon">
                            <i class="fas fa-chart-line"></i>
                        </div>
                        <h2 class="text-warning" id="successRate">0%</h2>
                        <p class="text-muted">Успешность</p>
                    </div>
                </div>
            </div>

            <!-- Панель управления -->
            <div class="row">
                <div class="col-lg-8">
                    <div class="card">
                        <div class="card-header bg-dark text-white">
                            <h4 class="mb-0"><i class="fas fa-cogs me-2"></i>Создание новой задачи</h4>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label class="form-label">Название задачи:</label>
                                <input type="text" class="form-control" id="taskName" 
                                       placeholder="Например: 'Генерация космического пейзажа'">
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Подробное описание:</label>
                                <textarea class="form-control" id="taskDescription" rows="4"
                                          placeholder="Опишите детали. Система учтет ваши предпочтения..."></textarea>
                            </div>
                            
                            <div class="row mb-4">
                                <div class="col-md-6">
                                    <label class="form-label">Тип контента:</label>
                                    <select class="form-select" id="contentType">
                                        <option value="image">Изображения (4 варианта)</option>
                                        <option value="video">Видео из изображения</option>
                                        <option value="full">Полный пайплайн</option>
                                    </select>
                                </div>
                                <div class="col-md-6">
                                    <label class="form-label">Приоритет:</label>
                                    <select class="form-select" id="taskPriority">
                                        <option value="normal">Обычный</option>
                                        <option value="high">Высокий</option>
                                        <option value="urgent">Срочный</option>
                                    </select>
                                </div>
                            </div>
                            
                            <div class="d-grid gap-2">
                                <button class="btn btn-primary btn-lg" onclick="createNewTask()">
                                    <i class="fas fa-rocket me-2"></i>Запустить задачу
                                </button>
                                <button class="btn btn-outline-secondary" onclick="loadAllTasks()">
                                    <i class="fas fa-redo me-2"></i>Обновить список
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Список задач -->
                    <div class="card mt-4">
                        <div class="card-header">
                            <h4 class="mb-0"><i class="fas fa-list-ul me-2"></i>Активные задачи</h4>
                        </div>
                        <div class="card-body">
                            <div id="tasksList">
                                <div class="text-center py-5">
                                    <div class="spinner-border text-primary" role="status">
                                        <span class="visually-hidden">Загрузка...</span>
                                    </div>
                                    <p class="mt-3">Загрузка списка задач...</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Боковая панель -->
                <div class="col-lg-4">
                    <div class="card">
                        <div class="card-header bg-info text-white">
                            <h5 class="mb-0"><i class="fas fa-info-circle me-2"></i>Информация о системе</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <h6><i class="fas fa-server me-2"></i>Сервер</h6>
                                <div class="small">
                                    <div>Nginx + Flask + Gunicorn</div>
                                    <div>Python 3.8+</div>
                                </div>
                            </div>
                            
                            <div class="mb-3">
                                <h6><i class="fas fa-database me-2"></i>База данных</h6>
                                <div class="small">
                                    <div>JSON файловая БД</div>
                                    <div>Автосохранение</div>
                                </div>
                            </div>
                            
                            <div class="mb-3">
                                <h6><i class="fas fa-bolt me-2"></i>Производительность</h6>
                                <div class="small">
                                    <div>Многопоточная обработка</div>
                                    <div>Фоновые задачи</div>
                                </div>
                            </div>
                            
                            <hr>
                            
                            <div class="text-center">
                                <button class="btn btn-sm btn-outline-danger" onclick="clearAllTasks()">
                                    <i class="fas fa-trash me-1"></i>Очистить все задачи
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card mt-4">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="fas fa-history me-2"></i>Последние действия</h5>
                        </div>
                        <div class="card-body">
                            <div id="recentActivity" class="small">
                                <div class="text-muted">Загрузка...</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Уведомление о статусе сервера -->
        <div class="server-status">
            <div class="toast show" role="alert">
                <div class="toast-header">
                    <strong class="me-auto">Статус сервера</strong>
                    <small>только что</small>
                    <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
                </div>
                <div class="toast-body">
                    <span class="badge bg-success me-2"><i class="fas fa-circle"></i></span>
                    Система активна
                </div>
            </div>
        </div>

        <!-- JavaScript -->
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
        // Глобальные переменные
        let autoRefreshInterval = null;
        
        // Функция создания задачи
        function createNewTask() {
            const name = document.getElementById('taskName').value.trim();
            const description = document.getElementById('taskDescription').value.trim();
            const type = document.getElementById('contentType').value;
            const priority = document.getElementById('taskPriority').value;
            
            if (!name) {
                showAlert('Введите название задачи', 'warning');
                return;
            }
            
            if (!description) {
                showAlert('Введите описание задачи', 'warning');
                return;
            }
            
            showAlert('Создание задачи...', 'info');
            
            fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: name,
                    description: description,
                    type: type,
                    priority: priority
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert(`Задача #${data.task.id} создана успешно!`, 'success');
                    document.getElementById('taskName').value = '';
                    document.getElementById('taskDescription').value = '';
                    loadAllTasks();
                    updateStats();
                } else {
                    showAlert('Ошибка: ' + data.error, 'danger');
                }
            })
            .catch(error => {
                showAlert('Ошибка сети: ' + error, 'danger');
            });
        }
        
        // Загрузка всех задач
        function loadAllTasks() {
            fetch('/api/tasks')
            .then(response => response.json())
            .then(tasks => {
                renderTasksList(tasks);
            })
            .catch(error => {
                console.error('Ошибка загрузки задач:', error);
            });
        }
        
        // Отображение списка задач
        function renderTasksList(tasks) {
            const container = document.getElementById('tasksList');
            
            if (!tasks || tasks.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-5">
                        <i class="fas fa-inbox fa-3x text-muted mb-3"></i>
                        <p class="text-muted">Нет активных задач</p>
                        <button class="btn btn-primary" onclick="createNewTask()">
                            <i class="fas fa-plus me-1"></i>Создать первую задачу
                        </button>
                    </div>
                `;
                return;
            }
            
            let html = '';
            tasks.forEach(task => {
                // Определяем цвет статуса
                let statusClass = 'secondary';
                let statusIcon = 'fa-clock';
                
                if (task.status === 'completed') {
                    statusClass = 'success';
                    statusIcon = 'fa-check-circle';
                } else if (task.status === 'running') {
                    statusClass = 'primary';
                    statusIcon = 'fa-spinner fa-spin';
                } else if (task.status === 'failed') {
                    statusClass = 'danger';
                    statusIcon = 'fa-exclamation-triangle';
                }
                
                // Форматируем время
                const createdTime = new Date(task.created_at).toLocaleTimeString('ru-RU');
                const updatedTime = new Date(task.updated_at).toLocaleTimeString('ru-RU');
                
                html += `
                    <div class="task-item card mb-3">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div>
                                    <h5 class="card-title mb-1">${task.name}</h5>
                                    <div class="small text-muted mb-2">
                                        <span class="me-3"><i class="fas fa-tag me-1"></i>${task.type}</span>
                                        <span><i class="fas fa-calendar me-1"></i>${createdTime}</span>
                                    </div>
                                </div>
                                <div>
                                    <span class="badge bg-${statusClass}">
                                        <i class="fas ${statusIcon} me-1"></i>${task.status}
                                    </span>
                                </div>
                            </div>
                            
                            <p class="card-text small text-muted mb-3">${task.description || 'Без описания'}</p>
                            
                            <!-- Шаги выполнения -->
                            ${task.steps && task.steps.length > 0 ? `
                                <div class="mb-3">
                                    <small class="text-muted d-block mb-1">Выполненные шаги:</small>
                                    <div>
                                        ${task.steps.map(step => 
                                            `<span class="badge bg-light text-dark step-badge">${step}</span>`
                                        ).join('')}
                                    </div>
                                </div>
                            ` : ''}
                            
                            <!-- Прогресс -->
                            <div class="mb-3">
                                <div class="d-flex justify-content-between mb-1">
                                    <small>Прогресс выполнения</small>
                                    <small>${task.progress}%</small>
                                </div>
                                <div class="progress">
                                    <div class="progress-bar bg-${statusClass}" 
                                         style="width: ${task.progress}%">
                                    </div>
                                </div>
                            </div>
                            
                            <div class="d-flex justify-content-between align-items-center">
                                <small class="text-muted">
                                    <i class="fas fa-sync-alt me-1"></i>Обновлено: ${updatedTime}
                                </small>
                                <div>
                                    <button class="btn btn-sm btn-outline-primary" onclick="viewTaskDetails(${task.id})">
                                        <i class="fas fa-eye"></i>
                                    </button>
                                    ${task.status === 'running' ? `
                                        <button class="btn btn-sm btn-outline-danger ms-1" onclick="cancelTask(${task.id})">
                                            <i class="fas fa-stop"></i>
                                        </button>
                                    ` : ''}
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }
        
        // Обновление статистики
        function updateStats() {
            fetch('/api/stats')
            .then(response => response.json())
            .then(stats => {
                document.getElementById('totalTasks').textContent = stats.total_tasks;
                document.getElementById('completedTasks').textContent = stats.completed;
                document.getElementById('runningTasks').textContent = stats.running;
                
                const successRate = stats.total_tasks > 0 
                    ? Math.round((stats.completed / stats.total_tasks) * 100) 
                    : 0;
                document.getElementById('successRate').textContent = successRate + '%';
            });
        }
        
        // Просмотр деталей задачи
        function viewTaskDetails(taskId) {
            fetch(`/api/tasks/${taskId}`)
            .then(response => response.json())
            .then(task => {
                let resultInfo = 'Нет результатов';
                if (task.result) {
                    if (typeof task.result === 'string') {
                        try {
                            const result = JSON.parse(task.result);
                            resultInfo = JSON.stringify(result, null, 2);
                        } catch {
                            resultInfo = task.result;
                        }
                    } else {
                        resultInfo = JSON.stringify(task.result, null, 2);
                    }
                }
                
                alert(`Детали задачи #${task.id}\n\n` +
                      `Название: ${task.name}\n` +
                      `Тип: ${task.type}\n` +
                      `Статус: ${task.status}\n` +
                      `Прогресс: ${task.progress}%\n` +
                      `Создана: ${new Date(task.created_at).toLocaleString('ru-RU')}\n` +
                      `Результат:\n${resultInfo}`);
            });
        }
        
        // Отмена задачи
        function cancelTask(taskId) {
            if (confirm('Вы уверены, что хотите отменить эту задачу?')) {
                fetch(`/api/tasks/${taskId}/cancel`, {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showAlert('Задача отменена', 'success');
                        loadAllTasks();
                        updateStats();
                    }
                });
            }
        }
        
        // Очистка всех задач
        function clearAllTasks() {
            if (confirm('ВНИМАНИЕ! Это удалит ВСЕ задачи. Продолжить?')) {
                fetch('/api/tasks/clear', {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showAlert('Все задачи удалены', 'success');
                        loadAllTasks();
                        updateStats();
                    }
                });
            }
        }
        
        // Всплывающие уведомления
        function showAlert(message, type) {
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
            alertDiv.style.cssText = `
                top: 80px;
                right: 20px;
                z-index: 9999;
                min-width: 300px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            `;
            alertDiv.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            
            document.body.appendChild(alertDiv);
            
            setTimeout(() => {
                if (alertDiv.parentNode) {
                    alertDiv.classList.remove('show');
                    setTimeout(() => alertDiv.remove(), 300);
                }
            }, 5000);
        }
        
        // Автоматическое обновление
        function startAutoRefresh() {
            if (autoRefreshInterval) clearInterval(autoRefreshInterval);
            
            autoRefreshInterval = setInterval(() => {
                loadAllTasks();
                updateStats();
            }, 10000); // Каждые 10 секунд
        }
        
        // Инициализация при загрузке страницы
        document.addEventListener('DOMContentLoaded', function() {
            loadAllTasks();
            updateStats();
            startAutoRefresh();
            
            // Обновляем время каждую минуту
            setInterval(() => {
                const now = new Date();
                document.getElementById('serverStatus').innerHTML = 
                    `<i class="fas fa-server me-1"></i>Nginx + Flask | ${now.toLocaleTimeString('ru-RU')}`;
            }, 60000);
        });
        </script>
    </body>
    </html>
    '''

# ==================== API ЭНДПОИНТЫ ====================

@app.route('/api/stats')
def get_stats():
    """Получение статистики"""
    stats = task_manager.get_stats()
    return jsonify(stats)

@app.route('/api/tasks', methods=['GET', 'POST'])
def tasks_api():
    """Управление задачами"""
    if request.method == 'GET':
        tasks = task_manager.get_all_tasks()
        return jsonify(tasks)
    
    elif request.method == 'POST':
        data = request.json
        
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Не указано название задачи'}), 400
        
        task = task_manager.create_task(
            name=data['name'],
            task_type=data.get('type', 'image'),
            description=data.get('description', '')
        )
        
        return jsonify({'success': True, 'task': task})

@app.route('/api/tasks/<int:task_id>')
def get_task_api(task_id):
    """Получение конкретной задачи"""
    task = task_manager.get_task(task_id)
    if task:
        return jsonify(task)
    return jsonify({'error': 'Задача не найдена'}), 404

@app.route('/api/tasks/<int:task_id>/cancel', methods=['POST'])
def cancel_task_api(task_id):
    """Отмена задачи"""
    if task_manager.update_task(task_id, status='cancelled'):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Задача не найдена'}), 404

@app.route('/api/tasks/clear', methods=['POST'])
def clear_tasks_api():
    """Очистка всех задач"""
    # В реальном приложении нужно архивировать, а не удалять
    task_manager.tasks = {"tasks": [], "next_id": 1, "stats": {}}
    task_manager._save_db()
    
    # Создаем системную задачу
    task_manager.create_task("Система очищена", "system", "Все задачи были очищены администратором")
    
    return jsonify({'success': True, 'message': 'Все задачи очищены'})

# Статические файлы
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route('/data/<path:filename>')
def serve_data(filename):
    return send_from_directory(DATA_DIR, filename)

# ==================== ЗАПУСК СЕРВЕРА ====================

def run_gunicorn():
    """Запуск через Gunicorn (для production)"""
    try:
        import gunicorn.app.base
        from gunicorn.six import iteritems
        
        class StandaloneApplication(gunicorn.app.base.BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()
            
            def load_config(self):
                config = {key: value for key, value in iteritems(self.options)
                         if key in self.cfg.settings and value is not None}
                for key, value in iteritems(config):
                    self.cfg.set(key.lower(), value)
            
            def load(self):
                return self.application
        
        options = {
            'bind': '127.0.0.1:8000',
            'workers': 4,
            'worker_class': 'sync',
            'timeout': 120,
            'accesslog': 'access.log',
            'errorlog': 'error.log',
            'loglevel': 'info'
        }
        
        StandaloneApplication(app, options).run()
        
    except ImportError:
        logger.warning("Gunicorn не установлен. Запускаю в режиме разработки.")
        app.run(host='0.0.0.0', port=8000, debug=True)

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 Media Automation System - Production Version")
    logger.info("=" * 60)
    logger.info("Режимы запуска:")
    logger.info("  1. Для разработки: python app_nginx.py")
    logger.info("  2. Для production: gunicorn app_nginx:app")
    logger.info("")
    logger.info("📁 Структура:")
    logger.info(f"  • База данных: {DATA_DIR / 'tasks_db.json'}")
    logger.info(f"  • Выходные данные: {OUTPUTS_DIR}")
    logger.info(f"  • Логи: media_automation.log")
    logger.info("=" * 60)
    
    # Запуск в режиме разработки
    app.run(host='0.0.0.0', port=8000, debug=False)