#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главный файл веб-приложения для управления видеоконвейером.
Запускает Flask-сервер с интерфейсом управления.
"""

import os
import json
import shutil
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from werkzeug.utils import secure_filename
import threading
from queue import Queue

# Импорт модулей проекта
from pipeline_core import VideoPipeline
from colab_runner import ColabManager
from reference_db import ReferenceManager
from auth import login_required, check_auth
from monitor import TaskMonitor
import utils

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-2024')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max

# Создаем папки
for folder in ['uploads', 'outputs', 'static', 'templates', 'logs']:
    os.makedirs(folder, exist_ok=True)

# Инициализация менеджеров
pipeline = VideoPipeline()
colab_manager = ColabManager()
reference_manager = ReferenceManager()
task_monitor = TaskMonitor()

# Очередь задач
task_queue = Queue()
active_tasks = {}

def process_queue():
    """Фоновая обработка задач из очереди"""
    while True:
        task_data = task_queue.get()
        task_id = task_data['task_id']
        task_type = task_data['type']
        
        try:
            if task_type == 'generate_images':
                result = pipeline.generate_images(
                    task_data['prompt'],
                    task_data['style_refs']
                )
                active_tasks[task_id]['result'] = result
                active_tasks[task_id]['status'] = 'completed'
                
            elif task_type == 'upscale':
                result = pipeline.upscale_selected(task_data['image_path'])
                active_tasks[task_id]['result'] = result
                active_tasks[task_id]['status'] = 'completed'
                
            elif task_type == 'create_video':
                result = pipeline.create_video_from_image(
                    task_data['image_path'],
                    task_data.get('audio_tracks', [])
                )
                active_tasks[task_id]['result'] = result
                active_tasks[task_id]['status'] = 'completed'
                
        except Exception as e:
            active_tasks[task_id]['status'] = 'error'
            active_tasks[task_id]['error'] = str(e)
        
        task_queue.task_done()

# Запуск фонового обработчика
threading.Thread(target=process_queue, daemon=True).start()

@app.route('/')
@login_required
def index():
    """Главная страница с дашбордом"""
    tasks = task_monitor.get_recent_tasks(10)
    stats = task_monitor.get_statistics()
    return render_template('index.html', 
                         tasks=tasks, 
                         stats=stats,
                         active_tasks=active_tasks)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница авторизации"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if check_auth(username, password):
            session['user'] = username
            return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Выход из системы"""
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/generate', methods=['GET', 'POST'])
@login_required
def generate_page():
    """Страница генерации изображений"""
    references = reference_manager.get_all_references()
    
    if request.method == 'POST':
        prompt = request.form.get('prompt', '')
        selected_refs = request.form.getlist('style_refs')
        
        # Создаем задачу
        task_id = f"gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        active_tasks[task_id] = {
            'type': 'generate_images',
            'status': 'queued',
            'prompt': prompt,
            'style_refs': selected_refs,
            'created_at': datetime.now().isoformat()
        }
        
        # Добавляем в очередь
        task_queue.put({
            'task_id': task_id,
            'type': 'generate_images',
            'prompt': prompt,
            'style_refs': selected_refs
        })
        
        task_monitor.log_task(task_id, 'generate_images', 'queued')
        return jsonify({'task_id': task_id, 'status': 'queued'})
    
    return render_template('generate.html', references=references)

@app.route('/task_status/<task_id>')
@login_required
def task_status(task_id):
    """Проверка статуса задачи"""
    task = active_tasks.get(task_id, {})
    return jsonify(task)

@app.route('/upload_reference', methods=['POST'])
@login_required
def upload_reference():
    """Загрузка референсного изображения"""
    if 'image' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['image']
    positive = request.form.get('positive', '')
    negative = request.form.get('negative', '')
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'references', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    file.save(filepath)
    
    # Добавляем в базу
    ref_id = reference_manager.add_reference(
        filepath, 
        {'positive': positive, 'negative': negative}
    )
    
    return jsonify({'success': True, 'ref_id': ref_id})

@app.route('/colab_status')
@login_required
def colab_status():
    """Проверка статуса Colab сессии"""
    status = colab_manager.get_status()
    return jsonify(status)

@app.route('/download/<path:filename>')
@login_required
def download_file(filename):
    """Скачивание файла"""
    safe_path = utils.safe_path('outputs', filename)
    if os.path.exists(safe_path):
        return send_file(safe_path, as_attachment=True)
    return 'File not found', 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
