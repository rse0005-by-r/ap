#!/usr/bin/env python3
"""
Media Automation System с просмотром медиафайлов
"""

from flask import Flask, jsonify, request, send_from_directory, render_template_string, Response
import json
import os
import time
import threading
import random
from datetime import datetime
from pathlib import Path
import mimetypes
from werkzeug.utils import secure_filename

# ==================== НАСТРОЙКИ ====================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'media-viewer-key-2024'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.config['UPLOAD_FOLDER'] = 'data/uploads'
app.config['OUTPUT_FOLDER'] = 'data/outputs'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'webm'}

# Создаем папки
BASE_DIR = Path(__file__).parent
for folder in ['static/images', 'static/videos', 'static/thumbnails', 
               'data/uploads', 'data/outputs/images', 'data/outputs/videos']:
    (BASE_DIR / folder).mkdir(parents=True, exist_ok=True)

# ==================== МОДЕЛЬ ДАННЫХ ====================

class MediaDatabase:
    """База данных для медиафайлов"""
    
    def __init__(self):
        self.db_file = BASE_DIR / 'data' / 'media_db.json'
        self.media = self._load_db()
    
    def _load_db(self):
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {"media": [], "next_id": 1}
        return {"media": [], "next_id": 1}
    
    def _save_db(self):
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.media, f, ensure_ascii=False, indent=2)
    
    def add_media(self, filename, media_type, description=""):
        """Добавление медиафайла в базу"""
        media_id = self.media["next_id"]
        
        # Определяем тип файла
        ext = filename.split('.')[-1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            file_type = 'image'
            thumbnail = f'/static/thumbnails/{media_id}.jpg'
            preview_url = f'/media/preview/{media_id}'
        elif ext in ['mp4', 'mov', 'avi', 'webm']:
            file_type = 'video'
            thumbnail = f'/static/thumbnails/{media_id}.jpg'
            preview_url = f'/media/player/{media_id}'
        else:
            file_type = 'document'
            thumbnail = None
            preview_url = None
        
        media_item = {
            "id": media_id,
            "filename": filename,
            "type": file_type,
            "media_type": media_type,  # original/generated/upscaled
            "description": description,
            "path": f"/data/uploads/{filename}",
            "thumbnail": thumbnail,
            "preview_url": preview_url,
            "created_at": datetime.now().isoformat(),
            "size": "1920x1080",
            "status": "active"
        }
        
        self.media["media"].append(media_item)
        self.media["next_id"] += 1
        self._save_db()
        
        # Создаем тестовую миниатюру
        self._create_test_thumbnail(media_id)
        
        return media_item
    
    def _create_test_thumbnail(self, media_id):
        """Создание тестовой миниатюры (заглушка)"""
        import random
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']
        color = random.choice(colors)
        
        # В реальном приложении здесь будет генерация реальной миниатюры
        thumb_path = BASE_DIR / 'static' / 'thumbnails' / f'{media_id}.jpg'
        
        # Создаем простой SVG как заглушку
        svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
        <svg width="300" height="200" xmlns="http://www.w3.org/2000/svg">
            <rect width="300" height="200" fill="{color}"/>
            <text x="150" y="100" font-family="Arial" font-size="24" 
                  fill="white" text-anchor="middle" dominant-baseline="middle">
                Preview {media_id}
            </text>
            <text x="150" y="130" font-family="Arial" font-size="14" 
                  fill="white" text-anchor="middle" dominant-baseline="middle">
                1920x1080
            </text>
        </svg>'''
        
        with open(thumb_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
    
    def get_media(self, media_id):
        """Получение медиафайла по ID"""
        for item in self.media["media"]:
            if item["id"] == media_id:
                return item
        return None
    
    def get_all_media(self, media_type=None):
        """Получение всех медиафайлов"""
        if media_type:
            return [m for m in self.media["media"] if m["type"] == media_type]
        return self.media["media"]
    
    def search_media(self, query):
        """Поиск медиафайлов"""
        results = []
        query = query.lower()
        for item in self.media["media"]:
            if (query in item["description"].lower() or 
                query in item["filename"].lower()):
                results.append(item)
        return results

# Инициализация базы данных
db = MediaDatabase()

# ==================== HTML ИНТЕРФЕЙС ====================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Media Automation - Просмотр медиа</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --primary: #4361ee;
            --secondary: #3a0ca3;
            --success: #4cc9f0;
        }
        body {
            background: #f8f9fa;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .media-card {
            border: none;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            height: 100%;
        }
        .media-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }
        .media-thumbnail {
            width: 100%;
            height: 200px;
            object-fit: cover;
            background: linear-gradient(45deg, #667eea, #764ba2);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 24px;
        }
        .media-icon {
            font-size: 48px;
            opacity: 0.8;
        }
        .media-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 2;
        }
        .media-actions {
            position: absolute;
            bottom: 10px;
            right: 10px;
            opacity: 0;
            transition: opacity 0.3s;
        }
        .media-card:hover .media-actions {
            opacity: 1;
        }
        .modal-fullscreen {
            max-width: 95vw;
            max-height: 95vh;
        }
        .modal-content {
            border-radius: 15px;
            overflow: hidden;
        }
        .media-preview {
            max-width: 100%;
            max-height: 70vh;
            object-fit: contain;
        }
        .tab-content {
            padding: 20px 0;
        }
        .upload-area {
            border: 3px dashed #dee2e6;
            border-radius: 15px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        .upload-area:hover {
            border-color: var(--primary);
            background-color: rgba(67, 97, 238, 0.05);
        }
        .upload-icon {
            font-size: 48px;
            color: #6c757d;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <!-- Навигация -->
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-photo-video me-2"></i>
                <strong>Media Automation</strong>
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link active" href="#" onclick="showTab('gallery')">
                            <i class="fas fa-th-large me-1"></i> Галерея
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="#" onclick="showTab('upload')">
                            <i class="fas fa-upload me-1"></i> Загрузить
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="#" onclick="showTab('generate')">
                            <i class="fas fa-robot me-1"></i> Сгенерировать
                        </a>
                    </li>
                </ul>
                <div class="navbar-text text-white">
                    <i class="fas fa-database me-1"></i>
                    <span id="mediaCount">0</span> файлов
                </div>
            </div>
        </div>
    </nav>

    <!-- Основной контент -->
    <div class="container mt-4">
        <!-- Табы -->
        <div class="mb-4">
            <ul class="nav nav-tabs" id="mediaTabs">
                <li class="nav-item">
                    <button class="nav-link active" onclick="showTab('gallery')">
                        <i class="fas fa-th-large me-2"></i>Галерея медиа
                    </button>
                </li>
                <li class="nav-item">
                    <button class="nav-link" onclick="showTab('upload')">
                        <i class="fas fa-upload me-2"></i>Загрузка файлов
                    </button>
                </li>
                <li class="nav-item">
                    <button class="nav-link" onclick="showTab('generate')">
                        <i class="fas fa-magic me-2"></i>Генерация контента
                    </button>
                </li>
            </ul>
        </div>

        <!-- Вкладка галереи -->
        <div id="galleryTab" class="tab-content">
            <div class="row mb-4">
                <div class="col-md-6">
                    <h3><i class="fas fa-images me-2"></i>Медиатека</h3>
                </div>
                <div class="col-md-6">
                    <div class="input-group">
                        <input type="text" class="form-control" id="searchMedia" 
                               placeholder="Поиск по названию или описанию...">
                        <button class="btn btn-primary" onclick="searchMedia()">
                            <i class="fas fa-search"></i>
                        </button>
                    </div>
                </div>
            </div>

            <div class="row">
                <div class="col-md-3 mb-3">
                    <div class="card media-card">
                        <div class="card-body text-center">
                            <div class="upload-icon">
                                <i class="fas fa-plus-circle"></i>
                            </div>
                            <h5>Новый контент</h5>
                            <p class="text-muted small">Добавить медиафайлы</p>
                            <button class="btn btn-primary btn-sm" onclick="showTab('upload')">
                                <i class="fas fa-plus me-1"></i>Добавить
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Сюда будут добавляться карточки медиа -->
                <div id="mediaGallery" class="row">
                    <!-- Карточки загружаются через JavaScript -->
                </div>
            </div>
        </div>

        <!-- Вкладка загрузки -->
        <div id="uploadTab" class="tab-content" style="display: none;">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-header bg-primary text-white">
                            <h4 class="mb-0"><i class="fas fa-cloud-upload-alt me-2"></i>Загрузка медиафайлов</h4>
                        </div>
                        <div class="card-body">
                            <div class="upload-area" onclick="document.getElementById('fileInput').click()">
                                <div class="upload-icon">
                                    <i class="fas fa-cloud-upload-alt"></i>
                                </div>
                                <h4>Перетащите файлы сюда</h4>
                                <p class="text-muted">или нажмите для выбора файлов</p>
                                <p class="small text-muted">Поддерживаются: JPG, PNG, GIF, MP4, MOV</p>
                            </div>
                            
                            <input type="file" id="fileInput" multiple style="display: none;" 
                                   onchange="handleFileSelect(this.files)">
                            
                            <div class="mt-4">
                                <label class="form-label">Описание (опционально):</label>
                                <textarea class="form-control" id="fileDescription" rows="3" 
                                          placeholder="Опишите, что на изображении/видео..."></textarea>
                            </div>
                            
                            <div class="mt-4">
                                <label class="form-label">Тип контента:</label>
                                <select class="form-select" id="mediaType">
                                    <option value="reference">Пример (для обучения ИИ)</option>
                                    <option value="generated">Сгенерированный контент</option>
                                    <option value="upscaled">Апскейлированное</option>
                                    <option value="final">Финальный результат</option>
                                </select>
                            </div>
                            
                            <div class="d-grid gap-2 mt-4">
                                <button class="btn btn-success btn-lg" onclick="uploadFiles()">
                                    <i class="fas fa-upload me-2"></i>Загрузить выбранные файлы
                                </button>
                            </div>
                            
                            <div id="uploadProgress" class="mt-4" style="display: none;">
                                <div class="progress">
                                    <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                         role="progressbar" style="width: 0%"></div>
                                </div>
                                <div class="text-center mt-2" id="uploadStatus"></div>
                            </div>
                            
                            <div id="selectedFiles" class="mt-4"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Вкладка генерации -->
        <div id="generateTab" class="tab-content" style="display: none;">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-header bg-success text-white">
                            <h4 class="mb-0"><i class="fas fa-robot me-2"></i>Генерация контента</h4>
                        </div>
                        <div class="card-body">
                            <div class="mb-4">
                                <label class="form-label">Описание для генерации:</label>
                                <textarea class="form-control" id="generatePrompt" rows="4"
                                          placeholder="Опишите, что вы хотите сгенерировать. Например: 'Космический пейзаж с планетами в стиле научной фантастики'"></textarea>
                            </div>
                            
                            <div class="row mb-4">
                                <div class="col-md-6">
                                    <label class="form-label">Тип контента:</label>
                                    <select class="form-select" id="generateType">
                                        <option value="image">Изображение</option>
                                        <option value="video">Видео</option>
                                    </select>
                                </div>
                                <div class="col-md-6">
                                    <label class="form-label">Количество вариантов:</label>
                                    <select class="form-select" id="generateCount">
                                        <option value="1">1 вариант</option>
                                        <option value="2">2 варианта</option>
                                        <option value="4" selected>4 варианта</option>
                                        <option value="8">8 вариантов</option>
                                    </select>
                                </div>
                            </div>
                            
                            <div class="d-grid gap-2">
                                <button class="btn btn-success btn-lg" onclick="generateContent()">
                                    <i class="fas fa-magic me-2"></i>Сгенерировать контент
                                </button>
                            </div>
                            
                            <div id="generateProgress" class="mt-4" style="display: none;">
                                <div class="progress">
                                    <div class="progress-bar progress-bar-striped progress-bar-animated bg-success" 
                                         role="progressbar" style="width: 0%"></div>
                                </div>
                                <div class="text-center mt-2" id="generateStatus"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Модальное окно для просмотра -->
    <div class="modal fade" id="mediaModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-xl modal-fullscreen">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="mediaModalTitle">Просмотр медиа</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body text-center">
                    <div id="mediaPreviewContainer">
                        <!-- Здесь будет отображаться медиафайл -->
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick="downloadMedia()">
                        <i class="fas fa-download me-2"></i>Скачать
                    </button>
                    <button class="btn btn-outline-secondary" data-bs-dismiss="modal">
                        Закрыть
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- JavaScript -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
    // Глобальные переменные
    let selectedFiles = [];
    let currentMediaId = null;
    
    // Функции для вкладок
    function showTab(tabName) {
        // Скрыть все вкладки
        document.getElementById('galleryTab').style.display = 'none';
        document.getElementById('uploadTab').style.display = 'none';
        document.getElementById('generateTab').style.display = 'none';
        
        // Показать выбранную вкладку
        document.getElementById(tabName + 'Tab').style.display = 'block';
        
        // Обновить активный таб в навигации
        document.querySelectorAll('.nav-tabs .nav-link').forEach(link => {
            link.classList.remove('active');
        });
        event.target.classList.add('active');
        
        // Если это галерея - загрузить медиа
        if (tabName === 'gallery') {
            loadMediaGallery();
        }
    }
    
    // Загрузка галереи медиа
    function loadMediaGallery() {
        fetch('/api/media')
            .then(response => response.json())
            .then(media => {
                updateMediaCount(media.length);
                renderMediaGallery(media);
            })
            .catch(error => {
                console.error('Ошибка загрузки медиа:', error);
                document.getElementById('mediaGallery').innerHTML = 
                    '<div class="col-12 text-center"><p class="text-danger">Ошибка загрузки медиа</p></div>';
            });
    }
    
    // Обновление счетчика медиа
    function updateMediaCount(count) {
        document.getElementById('mediaCount').textContent = count;
    }
    
    // Отрисовка галереи
    function renderMediaGallery(media) {
        const container = document.getElementById('mediaGallery');
        
        if (!media || media.length === 0) {
            container.innerHTML = `
                <div class="col-12 text-center py-5">
                    <i class="fas fa-inbox fa-3x text-muted mb-3"></i>
                    <h4 class="text-muted">Медиатека пуста</h4>
                    <p class="text-muted mb-4">Загрузите или сгенерируйте первый файл</p>
                    <button class="btn btn-primary" onclick="showTab('upload')">
                        <i class="fas fa-upload me-2"></i>Загрузить файлы
                    </button>
                    <button class="btn btn-success ms-2" onclick="showTab('generate')">
                        <i class="fas fa-magic me-2"></i>Сгенерировать
                    </button>
                </div>
            `;
            return;
        }
        
        let html = '';
        media.forEach(item => {
            // Определяем иконку по типу
            let icon = 'fa-file';
            let badgeClass = 'bg-secondary';
            
            if (item.type === 'image') {
                icon = 'fa-image';
                badgeClass = 'bg-success';
            } else if (item.type === 'video') {
                icon = 'fa-video';
                badgeClass = 'bg-primary';
            }
            
            // Определяем цвет бейджа по типу контента
            let typeBadgeClass = 'bg-info';
            if (item.media_type === 'reference') typeBadgeClass = 'bg-warning';
            else if (item.media_type === 'generated') typeBadgeClass = 'bg-success';
            else if (item.media_type === 'upscaled') typeBadgeClass = 'bg-purple';
            else if (item.media_type === 'final') typeBadgeClass = 'bg-danger';
            
            html += `
                <div class="col-md-3 mb-4">
                    <div class="card media-card" data-media-id="${item.id}">
                        <!-- Миниатюра -->
                        <div class="media-thumbnail position-relative">
                            ${item.thumbnail ? 
                                `<img src="${item.thumbnail}" class="w-100 h-100" style="object-fit: cover;">` :
                                `<i class="fas ${icon} media-icon"></i>`
                            }
                            
                            <!-- Бейдж типа -->
                            <span class="badge ${typeBadgeClass} media-badge">
                                ${item.media_type === 'reference' ? 'Пример' : 
                                  item.media_type === 'generated' ? 'Сген.' :
                                  item.media_type === 'upscaled' ? 'Апск.' : 'Финальный'}
                            </span>
                            
                            <!-- Действия -->
                            <div class="media-actions">
                                <button class="btn btn-sm btn-light" onclick="viewMedia(${item.id})" title="Просмотр">
                                    <i class="fas fa-eye"></i>
                                </button>
                                <button class="btn btn-sm btn-light ms-1" onclick="downloadMedia(${item.id})" title="Скачать">
                                    <i class="fas fa-download"></i>
                                </button>
                            </div>
                        </div>
                        
                        <!-- Информация -->
                        <div class="card-body">
                            <h6 class="card-title text-truncate" title="${item.filename}">
                                <i class="fas ${icon} me-2 text-${item.type === 'image' ? 'success' : 'primary'}"></i>
                                ${item.filename}
                            </h6>
                            <p class="card-text small text-muted mb-2">
                                ${item.description || 'Без описания'}
                            </p>
                            <div class="d-flex justify-content-between align-items-center">
                                <small class="text-muted">
                                    ${item.size || '1920x1080'}
                                </small>
                                <small class="text-muted">
                                    ${new Date(item.created_at).toLocaleDateString('ru-RU')}
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    // Просмотр медиафайла
    function viewMedia(mediaId) {
        currentMediaId = mediaId;
        
        fetch(`/api/media/${mediaId}`)
            .then(response => response.json())
            .then(media => {
                const modal = new bootstrap.Modal(document.getElementById('mediaModal'));
                const container = document.getElementById('mediaPreviewContainer');
                
                document.getElementById('mediaModalTitle').textContent = media.filename;
                
                if (media.type === 'image') {
                    // Для изображений
                    container.innerHTML = `
                        <img src="${media.path}" class="media-preview" alt="${media.filename}">
                        <div class="mt-3">
                            <p class="mb-2"><strong>Описание:</strong> ${media.description || 'Нет описания'}</p>
                            <p class="mb-2"><strong>Размер:</strong> ${media.size || 'Неизвестно'}</p>
                            <p class="mb-0"><strong>Тип:</strong> ${media.media_type === 'reference' ? 'Пример' : 'Сгенерированное'}</p>
                        </div>
                    `;
                } else if (media.type === 'video') {
                    // Для видео
                    container.innerHTML = `
                        <video controls class="media-preview">
                            <source src="${media.path}" type="video/mp4">
                            Ваш браузер не поддерживает видео.
                        </video>
                        <div class="mt-3">
                            <p class="mb-2"><strong>Описание:</strong> ${media.description || 'Нет описания'}</p>
                            <p class="mb-2"><strong>Размер:</strong> ${media.size || 'Неизвестно'}</p>
                            <p class="mb-0"><strong>Тип:</strong> ${media.media_type === 'reference' ? 'Пример' : 'Сгенерированное'}</p>
                        </div>
                    `;
                }
                
                modal.show();
            })
            .catch(error => {
                alert('Ошибка загрузки медиафайла: ' + error);
            });
    }
    
    // Поиск медиа
    function searchMedia() {
        const query = document.getElementById('searchMedia').value;
        if (!query.trim()) {
            loadMediaGallery();
            return;
        }
        
        fetch(`/api/media/search?q=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(media => {
                renderMediaGallery(media);
            });
    }
    
    // Обработка выбора файлов
    function handleFileSelect(files) {
        selectedFiles = Array.from(files);
        const container = document.getElementById('selectedFiles');
        
        if (selectedFiles.length === 0) {
            container.innerHTML = '';
            return;
        }
        
        let html = '<h5>Выбранные файлы:</h5><div class="list-group">';
        selectedFiles.forEach((file, index) => {
            html += `
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="fas ${file.type.startsWith('image') ? 'fa-image text-success' : 
                                          file.type.startsWith('video') ? 'fa-video text-primary' : 'fa-file'} me-2"></i>
                            ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)
                        </div>
                        <button class="btn btn-sm btn-danger" onclick="removeFile(${index})">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        
        container.innerHTML = html;
    }
    
    // Удаление файла из списка
    function removeFile(index) {
        selectedFiles.splice(index, 1);
        handleFileSelect(selectedFiles);
    }
    
    // Загрузка файлов на сервер
    function uploadFiles() {
        if (selectedFiles.length === 0) {
            alert('Выберите файлы для загрузки');
            return;
        }
        
        const description = document.getElementById('fileDescription').value;
        const mediaType = document.getElementById('mediaType').value;
        
        document.getElementById('uploadProgress').style.display = 'block';
        document.getElementById('uploadStatus').textContent = 'Начинаю загрузку...';
        
        let uploadedCount = 0;
        const totalFiles = selectedFiles.length;
        
        selectedFiles.forEach(file => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('description', description);
            formData.append('media_type', mediaType);
            
            fetch('/api/media/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                uploadedCount++;
                const progress = Math.round((uploadedCount / totalFiles) * 100);
                
                document.querySelector('#uploadProgress .progress-bar').style.width = progress + '%';
                document.getElementById('uploadStatus').textContent = 
                    `Загружено ${uploadedCount} из ${totalFiles} файлов`;
                
                if (uploadedCount === totalFiles) {
                    document.getElementById('uploadStatus').innerHTML = 
                        '<span class="text-success">✅ Все файлы загружены!</span>';
                    
                    // Очистить форму
                    selectedFiles = [];
                    document.getElementById('selectedFiles').innerHTML = '';
                    document.getElementById('fileDescription').value = '';
                    
                    // Показать галерею
                    setTimeout(() => {
                        showTab('gallery');
                    }, 2000);
                }
            })
            .catch(error => {
                console.error('Ошибка загрузки:', error);
                document.getElementById('uploadStatus').innerHTML = 
                    `<span class="text-danger">❌ Ошибка загрузки файла ${file.name}</span>`;
            });
        });
    }
    
    // Генерация контента
    function generateContent() {
        const prompt = document.getElementById('generatePrompt').value;
        const type = document.getElementById('generateType').value;
        const count = document.getElementById('generateCount').value;
        
        if (!prompt.trim()) {
            alert('Введите описание для генерации');
            return;
        }
        
        document.getElementById('generateProgress').style.display = 'block';
        document.getElementById('generateStatus').textContent = 'Начинаю генерацию...';
        
        fetch('/api/media/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                prompt: prompt,
                type: type,
                count: parseInt(count)
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Симуляция прогресса генерации
                let progress = 0;
                const interval = setInterval(() => {
                    progress += 10;
                    document.querySelector('#generateProgress .progress-bar').style.width = progress + '%';
                    document.getElementById('generateStatus').textContent = 
                        `Генерация... ${progress}%`;
                    
                    if (progress >= 100) {
                        clearInterval(interval);
                        document.getElementById('generateStatus').innerHTML = 
                            '<span class="text-success">✅ Генерация завершена!</span>';
                        
                        // Показать галерею
                        setTimeout(() => {
                            showTab('gallery');
                            loadMediaGallery();
                        }, 2000);
                    }
                }, 500);
            } else {
                document.getElementById('generateStatus').innerHTML = 
                    `<span class="text-danger">❌ Ошибка: ${data.error}</span>`;
            }
        })
        .catch(error => {
            document.getElementById('generateStatus').innerHTML = 
                `<span class="text-danger">❌ Ошибка сети: ${error}</span>`;
        });
    }
    
    // Скачивание медиафайла
    function downloadMedia(mediaId) {
        if (!mediaId && currentMediaId) {
            mediaId = currentMediaId;
        }
        
        if (mediaId) {
            window.open(`/api/media/${mediaId}/download`, '_blank');
        }
    }
    
    // Инициализация при загрузке страницы
    document.addEventListener('DOMContentLoaded', function() {
        loadMediaGallery();
        
        // Добавляем обработчик перетаскивания файлов
        const uploadArea = document.querySelector('.upload-area');
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.style.borderColor = '#4361ee';
            uploadArea.style.backgroundColor = 'rgba(67, 97, 238, 0.1)';
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.style.borderColor = '#dee2e6';
            uploadArea.style.backgroundColor = '';
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.style.borderColor = '#dee2e6';
            uploadArea.style.backgroundColor = '';
            
            if (e.dataTransfer.files.length > 0) {
                handleFileSelect(e.dataTransfer.files);
            }
        });
    });
    </script>
</body>
</html>
'''

# ==================== API ЭНДПОИНТЫ ====================

@app.route('/')
def index():
    """Главная страница"""
    return HTML_TEMPLATE

@app.route('/api/media')
def get_all_media():
    """Получение всех медиафайлов"""
    media = db.get_all_media()
    return jsonify(media)

@app.route('/api/media/<int:media_id>')
def get_media_by_id(media_id):
    """Получение конкретного медиафайла"""
    media = db.get_media(media_id)
    if media:
        return jsonify(media)
    return jsonify({'error': 'Медиафайл не найден'}), 404

@app.route('/api/media/search')
def search_media():
    """Поиск медиафайлов"""
    query = request.args.get('q', '')
    results = db.search_media(query)
    return jsonify(results)

@app.route('/api/media/upload', methods=['POST'])
def upload_media():
    """Загрузка медиафайла"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Файл не найден'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Файл не выбран'}), 400
        
        # Безопасное имя файла
        filename = secure_filename(file.filename)
        
        # Сохраняем файл
        filepath = BASE_DIR / 'data' / 'uploads' / filename
        file.save(filepath)
        
        # Добавляем в базу данных
        description = request.form.get('description', '')
        media_type = request.form.get('media_type', 'generated')
        
        media_item = db.add_media(filename, media_type, description)
        
        return jsonify({
            'success': True,
            'media': media_item,
            'message': 'Файл успешно загружен'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/generate', methods=['POST'])
def generate_media():
    """Генерация медиаконтента"""
    try:
        data = request.json
        prompt = data.get('prompt', '')
        media_type = data.get('type', 'image')
        count = data.get('count', 4)
        
        if not prompt:
            return jsonify({'error': 'Не указан промпт для генерации'}), 400
        
        # В реальном приложении здесь будет вызов AI API
        # Пока создаем тестовые медиафайлы
        
        generated_items = []
        for i in range(count):
            if media_type == 'image':
                filename = f"generated_{int(time.time())}_{i}.jpg"
                description = f"Сгенерированное изображение: {prompt}"
            else:
                filename = f"generated_{int(time.time())}_{i}.mp4"
                description = f"Сгенерированное видео: {prompt}"
            
            # Добавляем в базу данных
            media_item = db.add_media(filename, 'generated', description)
            generated_items.append(media_item)
            
            # Создаем тестовый файл (заглушку)
            test_file = BASE_DIR / 'data' / 'uploads' / filename
            with open(test_file, 'w') as f:
                f.write(f"Test {media_type} file - {prompt}")
        
        return jsonify({
            'success': True,
            'generated': generated_items,
            'message': f'Сгенерировано {count} {media_type} файлов'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<int:media_id>/download')
def download_media(media_id):
    """Скачивание медиафайла"""
    media = db.get_media(media_id)
    if not media:
        return jsonify({'error': 'Файл не найден'}), 404
    
    filepath = BASE_DIR / 'data' / 'uploads' / media['filename']
    if not filepath.exists():
        return jsonify({'error': 'Файл не существует на сервере'}), 404
    
    return send_from_directory(
        BASE_DIR / 'data' / 'uploads',
        media['filename'],
        as_attachment=True,
        download_name=media['filename']
    )

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Сервис статических файлов"""
    return send_from_directory(BASE_DIR / 'static', filename)

@app.route('/data/uploads/<path:filename>')
def serve_upload(filename):
    """Сервис загруженных файлов"""
    return send_from_directory(BASE_DIR / 'data' / 'uploads', filename)

# ==================== ЗАПУСК СЕРВЕРА ====================

if __name__ == '__main__':
    # Добавляем тестовые данные
    if len(db.get_all_media()) == 0:
        test_media = [
            ("example1.jpg", "reference", "Пример пейзажа с горами"),
            ("example2.jpg", "reference", "Пример портрета с хорошим освещением"),
            ("generated1.jpg", "generated", "Сгенерированный космический пейзаж"),
            ("generated2.mp4", "generated", "Сгенерированное видео анимации"),
            ("upscaled1.jpg", "upscaled", "Апскейлированное изображение 4K"),
            ("final_video.mp4", "final", "Финальный ролик для публикации")
        ]
        
        for filename, media_type, description in test_media:
            db.add_media(filename, media_type, description)
    
    print("=" * 60)
    print("🎬 MEDIA AUTOMATION SYSTEM - ПРОСМОТР МЕДИА")
    print("=" * 60)
    print("📁 Папки созданы:")
    print(f"  • Загрузки: {BASE_DIR / 'data' / 'uploads'}")
    print(f"  • Статика: {BASE_DIR / 'static'}")
    print(f"  • Миниатюры: {BASE_DIR / 'static' / 'thumbnails'}")
    print("")
    print("🌐 Запуск:")
    print("  1. Установите Flask: pip install flask")
    print("  2. Запустите: python app_nginx.py")
    print("  3. Откройте: http://localhost:8000")
    print("")
    print("👁 Функции:")
    print("  • Просмотр картинок и видео")
    print("  • Загрузка файлов")
    print("  • Генерация контента")
    print("  • Поиск по медиатеке")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=8000, debug=True)
