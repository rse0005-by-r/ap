#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Вспомогательные утилиты для видеоконвейера.
Общие функции, используемые в разных модулях.
"""

import os
import json
import base64
import hashlib
import shutil
import tempfile
import subprocess
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any, Union
import logging
import random
import string
from PIL import Image
import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ Функции для работы с файлами ============

def safe_path(base_dir: str, filename: str) -> str:
    """
    Безопасное создание пути к файлу.
    Защита от path traversal атак.
    """
    # Нормализуем путь
    safe_filename = os.path.basename(filename)
    full_path = os.path.abspath(os.path.join(base_dir, safe_filename))
    
    # Проверяем, что путь внутри базовой директории
    if not full_path.startswith(os.path.abspath(base_dir)):
        raise ValueError(f"Попытка доступа за пределами {base_dir}")
    
    return full_path

def create_directory(path: str, clear_existing: bool = False) -> str:
    """
    Создание директории с опциональной очисткой существующей.
    Возвращает абсолютный путь к созданной директории.
    """
    abs_path = os.path.abspath(path)
    
    if clear_existing and os.path.exists(abs_path):
        shutil.rmtree(abs_path)
        logger.info(f"Cleared directory: {abs_path}")
    
    os.makedirs(abs_path, exist_ok=True)
    logger.debug(f"Directory ready: {abs_path}")
    
    return abs_path

def generate_unique_filename(prefix: str = "file", 
                           extension: str = "txt",
                           timestamp: bool = True,
                           random_suffix: bool = True) -> str:
    """
    Генерация уникального имени файла.
    """
    parts = [prefix]
    
    if timestamp:
        parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
    
    if random_suffix:
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        parts.append(random_str)
    
    filename = "_".join(parts)
    
    if extension:
        if not extension.startswith("."):
            extension = "." + extension
        filename += extension
    
    return filename

def get_file_hash(filepath: str, algorithm: str = "md5") -> str:
    """
    Вычисление хэша файла.
    """
    if algorithm.lower() == "md5":
        hash_func = hashlib.md5()
    elif algorithm.lower() == "sha256":
        hash_func = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()

def get_file_size_human(filepath: str) -> str:
    """
    Получение размера файла в удобочитаемом формате.
    """
    size_bytes = os.path.getsize(filepath)
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    
    return f"{size_bytes:.2f} PB"

def list_files(directory: str, 
              extensions: List[str] = None,
              recursive: bool = False) -> List[str]:
    """
    Получение списка файлов в директории.
    """
    if not os.path.exists(directory):
        return []
    
    files = []
    
    if recursive:
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(root, filename)
                if extensions:
                    if any(filename.lower().endswith(ext.lower()) for ext in extensions):
                        files.append(filepath)
                else:
                    files.append(filepath)
    else:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                if extensions:
                    if any(filename.lower().endswith(ext.lower()) for ext in extensions):
                        files.append(filepath)
                else:
                    files.append(filepath)
    
    return sorted(files)

def cleanup_old_files(directory: str, 
                     max_age_days: int = 7,
                     extensions: List[str] = None) -> int:
    """
    Удаление старых файлов из директории.
    Возвращает количество удалённых файлов.
    """
    if not os.path.exists(directory):
        return 0
    
    cutoff_time = datetime.now() - timedelta(days=max_age_days)
    deleted_count = 0
    
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if extensions:
                if not any(filename.lower().endswith(ext.lower()) for ext in extensions):
                    continue
            
            filepath = os.path.join(root, filename)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            if file_mtime < cutoff_time:
                try:
                    os.remove(filepath)
                    deleted_count += 1
                    logger.debug(f"Deleted old file: {filepath}")
                except Exception as e:
                    logger.error(f"Failed to delete {filepath}: {e}")
    
    if deleted_count:
        logger.info(f"Cleaned up {deleted_count} old files from {directory}")
    
    return deleted_count

# ============ Функции для работы с изображениями ============

def encode_image_to_base64(image_path: str) -> str:
    """
    Кодирование изображения в base64.
    """
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    
    return encoded_string

def save_base64_image(base64_string: str, output_path: str) -> bool:
    """
    Сохранение изображения из base64 строки.
    """
    try:
        # Декодируем base64
        image_data = base64.b64decode(base64_string)
        
        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            tmp_file.write(image_data)
            tmp_path = tmp_file.name
        
        # Проверяем, является ли файл валидным изображением
        try:
            with Image.open(tmp_path) as img:
                img.verify()  # Проверка целостности
        except Exception as e:
            logger.error(f"Invalid image data: {e}")
            os.unlink(tmp_path)
            return False
        
        # Копируем в конечный путь
        shutil.copy2(tmp_path, output_path)
        os.unlink(tmp_path)
        
        logger.debug(f"Image saved to: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save base64 image: {e}")
        return False

def resize_image(image_path: str, 
                target_size: Tuple[int, int],
                keep_aspect_ratio: bool = True,
                output_path: str = None) -> Optional[str]:
    """
    Изменение размера изображения.
    """
    if not output_path:
        # Создаём путь для результата
        name, ext = os.path.splitext(os.path.basename(image_path))
        output_path = os.path.join(
            os.path.dirname(image_path),
            f"{name}_resized{ext}"
        )
    
    try:
        with Image.open(image_path) as img:
            if keep_aspect_ratio:
                # Сохраняем пропорции
                img.thumbnail(target_size, Image.Resampling.LANCZOS)
            else:
                # Изменяем без сохранения пропорций
                img = img.resize(target_size, Image.Resampling.LANCZOS)
            
            # Сохраняем результат
            img.save(output_path)
            logger.debug(f"Image resized: {output_path}")
            return output_path
            
    except Exception as e:
        logger.error(f"Failed to resize image {image_path}: {e}")
        return None

def get_image_info(image_path: str) -> Dict[str, Any]:
    """
    Получение информации об изображении.
    """
    try:
        with Image.open(image_path) as img:
            info = {
                'path': image_path,
                'filename': os.path.basename(image_path),
                'format': img.format,
                'mode': img.mode,
                'size': img.size,
                'width': img.width,
                'height': img.height,
                'aspect_ratio': img.width / img.height if img.height > 0 else 0,
                'filesize': os.path.getsize(image_path),
                'filesize_human': get_file_size_human(image_path)
            }
            return info
    except Exception as e:
        logger.error(f"Failed to get image info {image_path}: {e}")
        return {}

def convert_image_format(input_path: str, 
                        output_format: str,
                        quality: int = 95) -> Optional[str]:
    """
    Конвертация изображения в другой формат.
    """
    if not os.path.exists(input_path):
        return None
    
    # Создаём имя выходного файла
    name = os.path.splitext(os.path.basename(input_path))[0]
    output_dir = os.path.dirname(input_path)
    output_path = os.path.join(output_dir, f"{name}.{output_format.lower()}")
    
    try:
        with Image.open(input_path) as img:
            # Конвертируем в RGB для JPEG
            if output_format.upper() in ['JPG', 'JPEG'] and img.mode in ['RGBA', 'LA']:
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            
            # Сохраняем в новом формате
            save_kwargs = {}
            if output_format.upper() in ['JPG', 'JPEG']:
                save_kwargs['quality'] = quality
                save_kwargs['optimize'] = True
            elif output_format.upper() == 'PNG':
                save_kwargs['compress_level'] = 6
            
            img.save(output_path, format=output_format.upper(), **save_kwargs)
            logger.debug(f"Image converted: {output_path}")
            return output_path
            
    except Exception as e:
        logger.error(f"Failed to convert image {input_path}: {e}")
        return None

# ============ Функции для работы с видео ============

def get_video_info(video_path: str) -> Dict[str, Any]:
    """
    Получение информации о видеофайле с помощью ffprobe.
    """
    if not os.path.exists(video_path):
        return {'error': 'File not found'}
    
    try:
        # Команда ffprobe для получения информации в JSON формате
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        
        # Извлекаем нужную информацию
        video_info = {
            'path': video_path,
            'filename': os.path.basename(video_path),
            'filesize': os.path.getsize(video_path),
            'filesize_human': get_file_size_human(video_path)
        }
        
        # Информация о формате
        if 'format' in info:
            format_info = info['format']
            video_info.update({
                'format_name': format_info.get('format_name', ''),
                'format_long_name': format_info.get('format_long_name', ''),
                'duration': float(format_info.get('duration', 0)),
                'bit_rate': int(format_info.get('bit_rate', 0)) if format_info.get('bit_rate') else 0,
                'size': int(format_info.get('size', 0))
            })
        
        # Информация о потоках
        video_streams = []
        audio_streams = []
        
        if 'streams' in info:
            for stream in info['streams']:
                if stream['codec_type'] == 'video':
                    video_streams.append({
                        'codec': stream.get('codec_name', ''),
                        'width': stream.get('width', 0),
                        'height': stream.get('height', 0),
                        'fps': eval(stream.get('avg_frame_rate', '0/1')) if stream.get('avg_frame_rate') else 0,
                        'bitrate': stream.get('bit_rate', 0),
                        'pix_fmt': stream.get('pix_fmt', '')
                    })
                elif stream['codec_type'] == 'audio':
                    audio_streams.append({
                        'codec': stream.get('codec_name', ''),
                        'channels': stream.get('channels', 0),
                        'sample_rate': stream.get('sample_rate', 0),
                        'bitrate': stream.get('bit_rate', 0)
                    })
        
        video_info['video_streams'] = video_streams
        video_info['audio_streams'] = audio_streams
        
        # Основные характеристики из первого видео потока
        if video_streams:
            main_video = video_streams[0]
            video_info.update({
                'resolution': f"{main_video['width']}x{main_video['height']}",
                'width': main_video['width'],
                'height': main_video['height'],
                'fps': main_video['fps']
            })
        
        return video_info
        
    except subprocess.CalledProcessError as e:
        logger.error(f"ffprobe error for {video_path}: {e.stderr}")
        return {'error': str(e)}
    except FileNotFoundError:
        logger.error("ffprobe not found. Please install ffmpeg.")
        return {'error': 'ffprobe not installed'}
    except Exception as e:
        logger.error(f"Failed to get video info {video_path}: {e}")
        return {'error': str(e)}

def extract_frames(video_path: str, 
                  output_dir: str,
                  fps: int = None,
                  quality: int = 95) -> List[str]:
    """
    Извлечение кадров из видео.
    Возвращает список путей к извлечённым кадрам.
    """
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: {video_path}")
        return []
    
    # Создаём выходную директорию
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Команда ffmpeg для извлечения кадров
        cmd = [
            'ffmpeg', '-i', video_path,
            '-qscale:v', str(quality),  # Качество (1-31, меньше = лучше)
        ]
        
        if fps:
            cmd.extend(['-r', str(fps)])
        
        # Паттерн для имён файлов
        frame_pattern = os.path.join(output_dir, 'frame_%06d.jpg')
        cmd.append(frame_pattern)
        
        # Выполняем команду
        subprocess.run(cmd, capture_output=True, check=True)
        
        # Получаем список извлечённых кадров
        frames = []
        for filename in sorted(os.listdir(output_dir)):
            if filename.startswith('frame_') and filename.endswith('.jpg'):
                frame_path = os.path.join(output_dir, filename)
                frames.append(frame_path)
        
        logger.info(f"Extracted {len(frames)} frames from {video_path}")
        return frames
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error extracting frames: {e.stderr.decode()}")
        return []
    except Exception as e:
        logger.error(f"Failed to extract frames: {e}")
        return []

def create_video_from_frames(frames_dir: str,
                           output_path: str,
                           fps: int = 30,
                           codec: str = 'libx264',
                           crf: int = 18) -> bool:
    """
    Создание видео из последовательности кадров.
    """
    if not os.path.exists(frames_dir):
        logger.error(f"Frames directory not found: {frames_dir}")
        return False
    
    # Проверяем наличие кадров
    frame_files = []
    for ext in ['.jpg', '.jpeg', '.png']:
        frame_files.extend(
            f for f in os.listdir(frames_dir) 
            if f.lower().endswith(ext)
        )
    
    if not frame_files:
        logger.error(f"No frame files found in {frames_dir}")
        return False
    
    # Сортируем файлы кадров
    frame_files.sort()
    
    try:
        # Создаём временный файл со списком кадров
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as list_file:
            for frame_file in frame_files:
                frame_path = os.path.join(frames_dir, frame_file)
                list_file.write(f"file '{frame_path}'\n")
            list_path = list_file.name
        
        # Команда ffmpeg для создания видео
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_path,
            '-framerate', str(fps),
            '-c:v', codec,
            '-crf', str(crf),
            '-pix_fmt', 'yuv420p',
            '-preset', 'medium',
            output_path
        ]
        
        # Выполняем команду
        subprocess.run(cmd, capture_output=True, check=True)
        
        # Удаляем временный файл
        os.unlink(list_path)
        
        logger.info(f"Video created: {output_path}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error creating video: {e.stderr.decode()}")
        return False
    except Exception as e:
        logger.error(f"Failed to create video: {e}")
        return False

def extract_audio(video_path: str, output_path: str) -> bool:
    """
    Извлечение аудио из видео.
    """
    if not os.path.exists(video_path):
        return False
    
    try:
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-q:a', '0',
            '-map', 'a',
            output_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        logger.debug(f"Audio extracted: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to extract audio: {e}")
        return False

# ============ Функции для работы с конфигурацией ============

def load_config(config_path: str = 'config.yaml') -> Dict:
    """
    Загрузка конфигурации из YAML файла.
    """
    if not os.path.exists(config_path):
        logger.warning(f"Config file not found: {config_path}")
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Заменяем переменные окружения
        config = _replace_env_vars(config)
        
        logger.debug(f"Config loaded from {config_path}")
        return config or {}
        
    except Exception as e:
        logger.error(f"Failed to load config {config_path}: {e}")
        return {}

def _replace_env_vars(data: Any) -> Any:
    """
    Рекурсивная замена переменных окружения в конфигурации.
    """
    if isinstance(data, dict):
        return {k: _replace_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_replace_env_vars(item) for item in data]
    elif isinstance(data, str) and data.startswith('${') and data.endswith('}'):
        env_var = data[2:-1]
        return os.environ.get(env_var, '')
    else:
        return data

def save_config(config: Dict, config_path: str = 'config.yaml'):
    """
    Сохранение конфигурации в YAML файл.
    """
    try:
        # Создаём директорию если нужно
        os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        logger.debug(f"Config saved to {config_path}")
        
    except Exception as e:
        logger.error(f"Failed to save config {config_path}: {e}")

# ============ Прочие утилиты ============

def format_duration(seconds: float) -> str:
    """
    Форматирование длительности в человекочитаемый вид.
    """
    if seconds < 60:
        return f"{seconds:.1f} сек"
    
    minutes, seconds = divmod(seconds, 60)
    
    if minutes < 60:
        return f"{int(minutes)} мин {int(seconds)} сек"
    
    hours, minutes = divmod(minutes, 60)
    
    if hours < 24:
        return f"{int(hours)} час {int(minutes)} мин"
    
    days, hours = divmod(hours, 24)
    return f"{int(days)} дн {int(hours)} час"

def validate_email(email: str) -> bool:
    """
    Простая валидация email адреса.
    """
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def get_mime_type(filename: str) -> str:
    """
    Получение MIME типа файла.
    """
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'

def is_supported_audio_format(filename: str) -> bool:
    """
    Проверка поддерживаемых аудио форматов.
    """
    supported = ['.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac']
    return any(filename.lower().endswith(ext) for ext in supported)

def is_supported_video_format(filename: str) -> bool:
    """
    Проверка поддерживаемых видео форматов.
    """
    supported = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv']
    return any(filename.lower().endswith(ext) for ext in supported)

def is_supported_image_format(filename: str) -> bool:
    """
    Проверка поддерживаемых изображений форматов.
    """
    supported = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']
    return any(filename.lower().endswith(ext) for ext in supported)

def calculate_directory_size(directory: str) -> Tuple[int, str]:
    """
    Вычисление размера директории.
    Возвращает размер в байтах и человекочитаемом формате.
    """
    total_size = 0
    
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.isfile(filepath):
                total_size += os.path.getsize(filepath)
    
    # Конвертируем в человекочитаемый формат
    for unit in ['B', 'KB', 'MB', 'GB']:
        if total_size < 1024.0:
            human_size = f"{total_size:.2f} {unit}"
            break
        total_size /= 1024.0
    else:
        human_size = f"{total_size:.2f} TB"
    
    return total_size, human_size

def backup_file(filepath: str, backup_dir: str = 'backups') -> Optional[str]:
    """
    Создание резервной копии файла.
    """
    if not os.path.exists(filepath):
        return None
    
    # Создаём директорию для бэкапов
    os.makedirs(backup_dir, exist_ok=True)
    
    # Генерируем имя бэкапа
    filename = os.path.basename(filepath)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{os.path.splitext(filename)[0]}_{timestamp}{os.path.splitext(filename)[1]}"
    backup_path = os.path.join(backup_dir, backup_name)
    
    try:
        shutil.copy2(filepath, backup_path)
        logger.info(f"Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return None

def check_disk_space(path: str = '/') -> Dict[str, Any]:
    """
    Проверка свободного места на диске.
    """
    try:
        stat = shutil.disk_usage(path)
        
        return {
            'total_gb': stat.total / (1024**3),
            'used_gb': stat.used / (1024**3),
            'free_gb': stat.free / (1024**3),
            'used_percent': (stat.used / stat.total) * 100,
            'free_percent': (stat.free / stat.total) * 100
        }
    except Exception as e:
        logger.error(f"Failed to check disk space: {e}")
        return {}

# ============ Функции для логирования ============

def setup_logging(log_dir: str = 'logs', 
                 log_level: str = 'INFO',
                 max_log_size_mb: int = 10,
                 backup_count: int = 5):
    """
    Настройка системы логирования.
    """
    import logging.handlers
    
    # Создаём директорию для логов
    os.makedirs(log_dir, exist_ok=True)
    
    # Формат логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Основной логгер
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Удаляем существующие обработчики
    logger.handlers.clear()
    
    # Обработчик для файла с ротацией
    log_file = os.path.join(log_dir, 'video_pipeline.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_log_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    logger.addHandler(file_handler)
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    logger.addHandler(console_handler)
    
    logger.info(f"Logging system initialized. Level: {log_level}")

def log_performance(func):
    """
    Декоратор для логирования времени выполнения функции.
    """
    import time
    from functools import wraps
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger.debug(f"Starting {func.__name__}")
        
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            logger.debug(
                f"Completed {func.__name__} in {elapsed:.2f} seconds"
            )
            
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"Failed {func.__name__} after {elapsed:.2f} seconds: {e}"
            )
            raise
    
    return wrapper

# Экспортируем часто используемые функции
__all__ = [
    'safe_path',
    'create_directory',
    'generate_unique_filename',
    'get_file_hash',
    'encode_image_to_base64',
    'save_base64_image',
    'get_image_info',
    'get_video_info',
    'extract_frames',
    'create_video_from_frames',
    'load_config',
    'save_config',
    'format_duration',
    'setup_logging',
    'log_performance'
]
