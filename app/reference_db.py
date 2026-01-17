#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление референсными изображениями и их описаниями.
Хранение позитивных/негативных аспектов для генерации.
"""

import os
import json
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
import shutil
import logging
from typing import Dict, List, Optional, Tuple
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReferenceManager:
    """Менеджер для работы с референсными изображениями"""
    
    def __init__(self, db_path='references.db'):
        self.db_path = db_path
        self.init_database()
        self.thumbnails_dir = 'thumbnails'
        os.makedirs(self.thumbnails_dir, exist_ok=True)
    
    def init_database(self):
        """Инициализация базы данных SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица референсов (переименована из references в image_references)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS image_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            filehash TEXT UNIQUE NOT NULL,
            positive_text TEXT,
            negative_text TEXT,
            style_tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP,
            use_count INTEGER DEFAULT 0
        )
        ''')
        
        # Таблица стилей (извлечённые из референсов)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            characteristics TEXT,
            example_refs TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица использования референсов в генерациях
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reference_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_id INTEGER,
            generation_id TEXT,
            influence_score REAL,
            used_as_positive BOOLEAN,
            used_as_negative BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reference_id) REFERENCES image_references (id)
        )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    
    def add_reference(self, image_path: str, 
                     descriptions: Dict[str, str]) -> int:
        """
        Добавление нового референсного изображения
        Возвращает ID добавленного референса
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Генерируем хэш файла для уникальности
        file_hash = self._calculate_file_hash(image_path)
        
        # Проверяем, нет ли уже такого изображения
        existing_id = self._find_reference_by_hash(file_hash)
        if existing_id:
            logger.info(f"Reference already exists with ID: {existing_id}")
            return existing_id
        
        # Создаём thumbnail
        thumbnail_path = self._create_thumbnail(image_path)
        
        # Извлекаем имя файла
        filename = os.path.basename(image_path)
        
        # Анализируем изображение для извлечения стиля
        style_tags = self._analyze_image_style(image_path)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO image_references 
        (filename, filepath, filehash, positive_text, negative_text, style_tags)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            filename,
            image_path,
            file_hash,
            descriptions.get('positive', ''),
            descriptions.get('negative', ''),
            json.dumps(style_tags, ensure_ascii=False)
        ))
        
        ref_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        logger.info(f"Reference added with ID: {ref_id}")
        return ref_id
    
    def _calculate_file_hash(self, filepath: str) -> str:
        """Вычисление MD5 хэша файла"""
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _find_reference_by_hash(self, file_hash: str) -> Optional[int]:
        """Поиск референса по хэшу файла"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id FROM image_references WHERE filehash = ?",
            (file_hash,)
        )
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def _create_thumbnail(self, image_path: str, size: Tuple[int, int] = (200, 200)) -> str:
        """Создание thumbnail изображения"""
        try:
            with Image.open(image_path) as img:
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                # Генерируем имя файла thumbnail
                filename = os.path.basename(image_path)
                name_without_ext = os.path.splitext(filename)[0]
                thumbnail_name = f"{name_without_ext}_thumb.jpg"
                thumbnail_path = os.path.join(self.thumbnails_dir, thumbnail_name)
                
                # Сохраняем thumbnail
                img.convert('RGB').save(thumbnail_path, 'JPEG', quality=85)
                
                return thumbnail_path
        except Exception as e:
            logger.error(f"Failed to create thumbnail: {e}")
            return ""
    
    def _analyze_image_style(self, image_path: str) -> List[str]:
        """
        Анализ изображения для извлечения стилевых характеристик
        В реальной реализации здесь может быть нейросетевая модель
        """
        try:
            with Image.open(image_path) as img:
                tags = []
                
                # Простой анализ цвета
                colors = img.getcolors(maxcolors=10000)
                if colors:
                    # Определяем преобладающие цвета
                    colors.sort(reverse=True, key=lambda x: x[0])
                    dominant_colors = [c[1] for c in colors[:3]]
                    
                    # Добавляем теги на основе цветов
                    for color in dominant_colors:
                        if color[0] > 200 and color[1] > 200 and color[2] > 200:
                            tags.append('bright')
                        elif color[0] < 50 and color[1] < 50 and color[2] < 50:
                            tags.append('dark')
                        elif color[0] > color[1] and color[0] > color[2]:
                            tags.append('warm')
                        elif color[1] > color[0] and color[1] > color[2]:
                            tags.append('green_tones')
                        elif color[2] > color[0] and color[2] > color[1]:
                            tags.append('cool')
                
                # Анализ размера и соотношения сторон
                width, height = img.size
                if width > height:
                    tags.append('landscape')
                elif height > width:
                    tags.append('portrait')
                else:
                    tags.append('square')
                
                # Определяем разрешение
                if width >= 3840 or height >= 2160:
                    tags.append('4k')
                elif width >= 1920 or height >= 1080:
                    tags.append('hd')
                
                return tags
                
        except Exception as e:
            logger.error(f"Style analysis failed: {e}")
            return []
    
    def get_reference(self, ref_id: int) -> Optional[Dict]:
        """Получение информации о референсе по ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM image_references WHERE id = ?
        ''', (ref_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_all_references(self) -> List[Dict]:
        """Получение всех референсов"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT id, filename, positive_text, negative_text, style_tags, 
               created_at, use_count
        FROM image_references 
        ORDER BY created_at DESC
        ''')
        
        references = []
        for row in cursor.fetchall():
            ref_dict = dict(row)
            # Парсим JSON стилевых тегов
            if ref_dict.get('style_tags'):
                try:
                    ref_dict['style_tags'] = json.loads(ref_dict['style_tags'])
                except:
                    ref_dict['style_tags'] = []
            references.append(ref_dict)
        
        conn.close()
        return references
    
    def update_reference(self, ref_id: int, updates: Dict[str, str]) -> bool:
        """Обновление информации о референсе"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Подготавливаем данные для обновления
        set_clauses = []
        values = []
        
        if 'positive_text' in updates:
            set_clauses.append("positive_text = ?")
            values.append(updates['positive_text'])
        
        if 'negative_text' in updates:
            set_clauses.append("negative_text = ?")
            values.append(updates['negative_text'])
        
        if set_clauses:
            query = f'''
            UPDATE image_references 
            SET {', '.join(set_clauses)}, last_used = CURRENT_TIMESTAMP
            WHERE id = ?
            '''
            values.append(ref_id)
            
            cursor.execute(query, values)
            conn.commit()
            success = cursor.rowcount > 0
        else:
            success = False
        
        conn.close()
        
        if success:
            logger.info(f"Reference {ref_id} updated")
        else:
            logger.warning(f"No updates performed for reference {ref_id}")
        
        return success
    
    def increment_use_count(self, ref_id: int):
        """Увеличение счётчика использования референса"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE image_references 
        SET use_count = use_count + 1, 
            last_used = CURRENT_TIMESTAMP
        WHERE id = ?
        ''', (ref_id,))
        
        conn.commit()
        conn.close()
        logger.debug(f"Use count incremented for reference {ref_id}")
    
    def search_references(self, query: str, 
                         search_in: List[str] = None) -> List[Dict]:
        """
        Поиск референсов по текстовому запросу
        search_in: список полей для поиска ['positive_text', 'negative_text', 'style_tags']
        """
        if search_in is None:
            search_in = ['positive_text', 'negative_text']
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Строим условия поиска
        conditions = []
        params = []
        
        for field in search_in:
            if field == 'style_tags':
                # Поиск в JSON-поле style_tags
                conditions.append("style_tags LIKE ?")
                params.append(f'%{query}%')
            else:
                conditions.append(f"{field} LIKE ?")
                params.append(f'%{query}%')
        
        where_clause = " OR ".join(conditions)
        
        cursor.execute(f'''
        SELECT id, filename, positive_text, negative_text, style_tags,
               created_at, use_count
        FROM image_references 
        WHERE {where_clause}
        ORDER BY use_count DESC
        ''', params)
        
        results = []
        for row in cursor.fetchall():
            ref_dict = dict(row)
            if ref_dict.get('style_tags'):
                try:
                    ref_dict['style_tags'] = json.loads(ref_dict['style_tags'])
                except:
                    ref_dict['style_tags'] = []
            results.append(ref_dict)
        
        conn.close()
        logger.info(f"Found {len(results)} references for query: '{query}'")
        return results
    
    def get_references_by_style(self, style_tags: List[str]) -> List[Dict]:
        """Получение референсов по стилевым тегам"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Ищем референсы, содержащие хотя бы один из указанных тегов
        conditions = []
        params = []
        
        for tag in style_tags:
            conditions.append("style_tags LIKE ?")
            params.append(f'%{tag}%')
        
        where_clause = " OR ".join(conditions)
        
        cursor.execute(f'''
        SELECT id, filename, positive_text, negative_text, style_tags,
               created_at, use_count
        FROM image_references 
        WHERE {where_clause}
        ORDER BY use_count DESC
        ''', params)
        
        results = []
        for row in cursor.fetchall():
            ref_dict = dict(row)
            if ref_dict.get('style_tags'):
                try:
                    ref_dict['style_tags'] = json.loads(ref_dict['style_tags'])
                except:
                    ref_dict['style_tags'] = []
            results.append(ref_dict)
        
        conn.close()
        return results
    
    def delete_reference(self, ref_id: int) -> bool:
        """Удаление референса"""
        # Сначала получаем информацию о файле
        ref_info = self.get_reference(ref_id)
        if not ref_info:
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Удаляем запись из базы
        cursor.execute('DELETE FROM image_references WHERE id = ?', (ref_id,))
        
        # Удаляем связанные записи об использовании
        cursor.execute('DELETE FROM reference_usage WHERE reference_id = ?', (ref_id,))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        
        if success:
            # Удаляем thumbnail если существует
            filename = ref_info['filename']
            name_without_ext = os.path.splitext(filename)[0]
            thumbnail_path = os.path.join(
                self.thumbnails_dir, 
                f"{name_without_ext}_thumb.jpg"
            )
            
            if os.path.exists(thumbnail_path):
                try:
                    os.remove(thumbnail_path)
                except Exception as e:
                    logger.error(f"Failed to delete thumbnail: {e}")
            
            logger.info(f"Reference {ref_id} deleted")
        
        return success
    
    def get_statistics(self) -> Dict:
        """Получение статистики по референсам"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # Общее количество
        cursor.execute("SELECT COUNT(*) FROM image_references")
        stats['total'] = cursor.fetchone()[0]
        
        # Самый используемый
        cursor.execute('''
        SELECT filename, use_count 
        FROM image_references 
        ORDER BY use_count DESC 
        LIMIT 1
        ''')
        result = cursor.fetchone()
        if result:
            stats['most_used'] = {
                'filename': result[0],
                'use_count': result[1]
            }
        
        # Новейший
        cursor.execute('''
        SELECT filename, created_at 
        FROM image_references 
        ORDER BY created_at DESC 
        LIMIT 1
        ''')
        result = cursor.fetchone()
        if result:
            stats['newest'] = {
                'filename': result[0],
                'created_at': result[1]
            }
        
        # Статистика по тегам
        cursor.execute("SELECT style_tags FROM image_references")
        all_tags = []
        for row in cursor.fetchall():
            if row[0]:
                try:
                    tags = json.loads(row[0])
                    all_tags.extend(tags)
                except:
                    pass
        
        from collections import Counter
        tag_counts = Counter(all_tags)
        stats['top_tags'] = tag_counts.most_common(10)
        
        conn.close()
        return stats
    
    def log_usage(self, reference_id: int, generation_id: str, 
                 influence_score: float = 0.5,
                 positive_use: bool = True,
                 negative_use: bool = False):
        """Логирование использования референса в генерации"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO reference_usage 
        (reference_id, generation_id, influence_score, 
         used_as_positive, used_as_negative)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            reference_id,
            generation_id,
            influence_score,
            positive_use,
            negative_use
        ))
        
        conn.commit()
        conn.close()
        
        # Увеличиваем общий счётчик использования
        self.increment_use_count(reference_id)
        
        logger.debug(f"Logged usage of reference {reference_id} in generation {generation_id}")


# Глобальный экземпляр для использования
reference_manager = ReferenceManager()
