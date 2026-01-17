#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЯДРО СИСТЕМЫ: все основные функции видеоконвейера.
Содержит логику генерации, обработки и сборки видео.
"""

import os
import json
import yaml
import subprocess
import tempfile
import random
from datetime import datetime
from pathlib import Path
import shutil
import logging
from typing import List, Dict, Tuple, Optional

# Импорт утилит
import utils
from colab_runner import ColabManager

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoPipeline:
    """Основной класс видеоконвейера"""
    
    def __init__(self, config_path='config.yaml'):
        self.config = self._load_config(config_path)
        self.colab_manager = ColabManager()
        self.setup_directories()
        
    def _load_config(self, config_path: str) -> Dict:
        """Загрузка конфигурации из YAML файла"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            # Заменяем переменные окружения
            if 'apis' in config:
                for api_name, api_key in config['apis'].items():
                    if isinstance(api_key, str) and api_key.startswith('${') and api_key.endswith('}'):
                        env_var = api_key[2:-1]
                        config['apis'][api_name] = os.environ.get(env_var, '')
                        
            return config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Резервная конфигурация по умолчанию"""
        return {
            'paths': {
                'uploads': './uploads',
                'outputs': './outputs',
                'publish': './publish',
                'templates': './templates'
            },
            'video': {
                'short_duration': 10,
                'long_duration': 40,
                'fps': 60,
                'width': 1920,
                'height': 1080,
                '4k_width': 3840,
                '4k_height': 2160
            },
            'generation': {
                'num_variants': 4,
                'use_colab': True,
                'colab_timeout': 1800
            }
        }
    
    def setup_directories(self):
        """Создание необходимых директорий"""
        paths = self.config['paths']
        for path in paths.values():
            Path(path).mkdir(parents=True, exist_ok=True)
        
        # Дополнительные поддиректории
        subdirs = [
            'references', 'generated', 'selected', 'videos',
            'short', 'long', '4k', 'final', 'audio'
        ]
        
        for subdir in subdirs:
            Path(f"{paths['outputs']}/{subdir}").mkdir(parents=True, exist_ok=True)
    
    def generate_images(self, prompt: str, style_references: List[str]) -> List[str]:
        """
        Генерация 4 вариантов изображений на основе промта и референсов
        Возвращает список путей к сгенерированным изображениям
        """
        logger.info(f"Generating images for prompt: {prompt}")
        
        # Подготовка промта с учетом референсов
        enhanced_prompt = self._enhance_prompt(prompt, style_references)
        
        # Определяем метод генерации
        if self.config['generation'].get('use_colab', True):
            # Используем Colab для тяжёлых вычислений
            logger.info("Using Colab for image generation")
            
            # Подготавливаем данные для Colab
            colab_data = {
                'action': 'generate_images',
                'prompt': enhanced_prompt,
                'num_variants': self.config['generation'].get('num_variants', 4),
                'width': self.config['video']['width'],
                'height': self.config['video']['height'],
                'negative_prompt': self._get_negative_prompt(style_references)
            }
            
            # Отправляем задание в Colab
            result = self.colab_manager.execute_task(colab_data)
            
            if result['success']:
                generated_files = []
                for i, img_data in enumerate(result.get('images', [])):
                    # Сохраняем изображения локально
                    filename = f"gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.png"
                    filepath = os.path.join(
                        self.config['paths']['outputs'],
                        'generated',
                        filename
                    )
                    
                    utils.save_base64_image(img_data, filepath)
                    generated_files.append(filepath)
                
                logger.info(f"Generated {len(generated_files)} images")
                return generated_files
            else:
                raise Exception(f"Colab generation failed: {result.get('error')}")
        else:
            # Локальная генерация (заглушка - требует установки Stable Diffusion)
            logger.warning("Local generation - requires Stable Diffusion installation")
            return self._generate_local_images(enhanced_prompt)
    
    def _enhance_prompt(self, base_prompt: str, style_refs: List[str]) -> str:
        """Улучшение промта на основе референсных изображений"""
        enhanced = base_prompt
        
        if style_refs:
            # Здесь должна быть логика анализа референсов
            # Пока просто добавляем метку
            enhanced += f", style references: {', '.join(style_refs[:3])}"
            
            # Добавляем общие улучшающие слова
            enhanced += ", masterpiece, best quality, detailed, 8k, ultra detailed"
        
        return enhanced
    
    def _get_negative_prompt(self, style_refs: List[str]) -> str:
        """Формирование негативного промта"""
        negative_base = "worst quality, low quality, normal quality, blurry, watermark, signature"
        
        # Анализируем негативные аспекты из референсов
        # TODO: Реализовать анализ негативных описаний
        return negative_base
    
    def upscale_selected(self, image_path: str, scale_factor: int = 4) -> str:
        """
        Апскейл выбранного изображения
        Возвращает путь к улучшенному изображению
        """
        logger.info(f"Upscaling image: {image_path}")
        
        # Проверяем существование файла
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        if self.config['generation'].get('use_colab', True):
            # Используем Colab для апскейла
            with open(image_path, 'rb') as f:
                img_data = f.read()
            
            colab_data = {
                'action': 'upscale_image',
                'image_data': utils.encode_image_to_base64(img_data),
                'scale_factor': scale_factor,
                'target_width': self.config['video']['4k_width'],
                'target_height': self.config['video']['4k_height']
            }
            
            result = self.colab_manager.execute_task(colab_data)
            
            if result['success']:
                # Сохраняем результат
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"upscaled_{timestamp}.png"
                output_path = os.path.join(
                    self.config['paths']['outputs'],
                    'selected',
                    filename
                )
                
                utils.save_base64_image(result['image'], output_path)
                logger.info(f"Upscaled image saved to: {output_path}")
                return output_path
            else:
                raise Exception(f"Colab upscale failed: {result.get('error')}")
        else:
            # Локальный апскейл (заглушка)
            return self._local_upscale(image_path, scale_factor)
    
    def create_video_from_image(self, image_path: str, 
                               audio_tracks: List[Dict] = None) -> str:
        """
        Создание видео из изображения с аудиодорожками
        Возвращает путь к созданному видео (8-10 секунд)
        """
        logger.info(f"Creating video from image: {image_path}")
        
        if audio_tracks is None:
            audio_tracks = []
        
        # Проверяем изображение
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Создаем временную директорию
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Подготовка изображения для видео
            video_duration = self.config['video'].get('short_duration', 10)
            
            # Создаем последовательность кадров (статичное изображение)
            frames_dir = os.path.join(tmp_dir, 'frames')
            os.makedirs(frames_dir)
            
            num_frames = video_duration * self.config['video']['fps']
            
            for i in range(num_frames):
                frame_path = os.path.join(frames_dir, f"frame_{i:06d}.png")
                shutil.copy2(image_path, frame_path)
            
            # Создаем видео из кадров
            video_path = os.path.join(tmp_dir, 'raw_video.mp4')
            self._create_video_from_frames(
                frames_dir, 
                video_path,
                self.config['video']['fps']
            )
            
            # Добавляем аудиодорожки
            if audio_tracks:
                video_with_audio = self._mix_audio_tracks(video_path, audio_tracks, tmp_dir)
            else:
                video_with_audio = video_path
            
            # Сохраняем финальный вариант
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            final_path = os.path.join(
                self.config['paths']['outputs'],
                'videos',
                'short',
                f"video_{timestamp}.mp4"
            )
            
            shutil.copy2(video_with_audio, final_path)
            logger.info(f"Video created: {final_path}")
            return final_path
    
    def _create_video_from_frames(self, frames_dir: str, output_path: str, fps: int):
        """Создание видео из последовательности кадров с помощью ffmpeg"""
        try:
            # Используем ffmpeg для создания видео
            cmd = [
                'ffmpeg', '-y',
                '-framerate', str(fps),
                '-pattern_type', 'glob',
                '-i', os.path.join(frames_dir, '*.png'),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-crf', '18',
                output_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr.decode()}")
            raise Exception(f"Video creation failed: {e}")
        except FileNotFoundError:
            logger.error("FFmpeg not found. Please install ffmpeg.")
            raise Exception("FFmpeg is required for video processing")
    
    def _mix_audio_tracks(self, video_path: str, 
                         audio_tracks: List[Dict],
                         tmp_dir: str) -> str:
        """Микширование аудиодорожек с видео"""
        if not audio_tracks:
            return video_path
        
        # Подготавливаем аудиофайлы
        audio_files = []
        for i, track in enumerate(audio_tracks):
            audio_path = track.get('path')
            volume = track.get('volume', 100) / 100.0
            
            if os.path.exists(audio_path):
                # Нормализуем и устанавливаем громкость
                processed_audio = os.path.join(tmp_dir, f"audio_{i}.wav")
                
                cmd = [
                    'ffmpeg', '-y',
                    '-i', audio_path,
                    '-af', f'volume={volume}',
                    '-ac', '2',
                    processed_audio
                ]
                
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    audio_files.append(processed_audio)
                except Exception as e:
                    logger.warning(f"Failed to process audio {audio_path}: {e}")
        
        if not audio_files:
            return video_path
        
        # Микшируем аудиодорожки
        mixed_audio = os.path.join(tmp_dir, 'mixed_audio.wav')
        
        if len(audio_files) == 1:
            shutil.copy2(audio_files[0], mixed_audio)
        else:
            # Создаем фильтр для микширования
            filter_complex = ''
            for i in range(len(audio_files)):
                filter_complex += f'[{i}:a]'
            filter_complex += f'amerge=inputs={len(audio_files)}[out]'
            
            cmd = [
                'ffmpeg', '-y'
            ]
            
            for audio_file in audio_files:
                cmd.extend(['-i', audio_file])
            
            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', '[out]',
                '-ac', '2',
                mixed_audio
            ])
            
            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except Exception as e:
                logger.error(f"Audio mixing failed: {e}")
                return video_path
        
        # Объединяем видео и аудио
        output_path = os.path.join(tmp_dir, 'video_with_audio.mp4')
        
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', mixed_audio,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return output_path
        except Exception as e:
            logger.error(f"Failed to merge audio with video: {e}")
            return video_path
    
    def extend_video(self, short_video_path: str, 
                    target_duration: int = 40) -> str:
        """
        Расширение короткого видео до заданной длины (40-60 секунд)
        Возвращает путь к расширенному видео
        """
        logger.info(f"Extending video: {short_video_path} to {target_duration}s")
        
        if not os.path.exists(short_video_path):
            raise FileNotFoundError(f"Video not found: {short_video_path}")
        
        # Получаем информацию о видео
        video_info = utils.get_video_info(short_video_path)
        current_duration = float(video_info.get('duration', 0))
        
        if current_duration >= target_duration:
            logger.warning(f"Video already {current_duration}s, no extension needed")
            return short_video_path
        
        # Рассчитываем необходимое количество повторов
        repeats = int(target_duration / current_duration) + 1
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Создаем список файлов для конкатенации
            list_file = os.path.join(tmp_dir, 'concat_list.txt')
            
            with open(list_file, 'w') as f:
                for _ in range(repeats):
                    f.write(f"file '{short_video_path}'\n")
            
            # Конкатенируем видео
            extended_path = os.path.join(tmp_dir, 'extended.mp4')
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',
                extended_path
            ]
            
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                
                # Обрезаем до нужной длины
                final_path = os.path.join(
                    self.config['paths']['outputs'],
                    'videos',
                    'long',
                    f"extended_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                )
                
                cmd = [
                    'ffmpeg', '-y',
                    '-i', extended_path,
                    '-t', str(target_duration),
                    '-c', 'copy',
                    final_path
                ]
                
                subprocess.run(cmd, check=True, capture_output=True)
                logger.info(f"Extended video saved to: {final_path}")
                return final_path
                
            except Exception as e:
                logger.error(f"Video extension failed: {e}")
                raise Exception(f"Failed to extend video: {e}")
    
    def super_resolution(self, video_path: str) -> str:
        """
        Апскейл видео до 4K с улучшением детализации
        Разбирает на кадры, апскейлит каждый кадр, собирает обратно
        """
        logger.info(f"Starting 4K super resolution for: {video_path}")
        
        if self.config['generation'].get('use_colab', True):
            # Используем Colab для тяжёлого апскейла
            colab_data = {
                'action': 'super_resolution',
                'video_path': video_path,
                'target_width': self.config['video']['4k_width'],
                'target_height': self.config['video']['4k_height'],
                'fps': self.config['video']['fps']
            }
            
            result = self.colab_manager.execute_task(colab_data)
            
            if result['success']:
                # Сохраняем результат
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"4k_{timestamp}.mp4"
                output_path = os.path.join(
                    self.config['paths']['outputs'],
                    'videos',
                    '4k',
                    filename
                )
                
                # TODO: Скачать видео из Colab
                logger.info(f"4K video would be saved to: {output_path}")
                return output_path
            else:
                raise Exception(f"4K super resolution failed: {result.get('error')}")
        else:
            # Локальный апскейл (очень ресурсоёмко)
            return self._local_super_resolution(video_path)
    
    def create_seamless_loop(self, base_video_path: str, 
                           total_duration_minutes: int = 180) -> str:
        """
        Создание бесшовного длинного видео (3-24 часа)
        путём многократного дублирования и склейки
        """
        logger.info(f"Creating seamless loop: {total_duration_minutes} minutes")
        
        total_seconds = total_duration_minutes * 60
        video_info = utils.get_video_info(base_video_path)
        video_duration = float(video_info.get('duration', 0))
        
        if video_duration <= 0:
            raise ValueError("Invalid video duration")
        
        # Рассчитываем необходимое количество повторов
        repeats = int(total_seconds / video_duration) + 1
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Создаём оптимизированную склейку
            output_path = os.path.join(
                self.config['paths']['outputs'],
                'videos',
                'final',
                f"loop_{total_duration_minutes}min_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            )
            
            # Используем ffmpeg для создания плавной склейки
            list_file = os.path.join(tmp_dir, 'loop_list.txt')
            
            with open(list_file, 'w') as f:
                for i in range(repeats):
                    f.write(f"file '{base_video_path}'\n")
                    if i < repeats - 1:
                        # Добавляем crossfade для плавности
                        f.write(f"file '{base_video_path}'\n")
                        f.write("inpoint 0\n")
                        f.write("outpoint 0.5\n")
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-filter_complex',
                f'[0:v]fps={self.config["video"]["fps"]}[v];[0:a]aresample=44100[a]',
                '-map', '[v]',
                '-map', '[a]',
                '-c:v', 'libx264',
                '-crf', '18',
                '-preset', 'medium',
                '-c:a', 'aac',
                '-b:a', '192k',
                output_path
            ]
            
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                logger.info(f"Seamless loop created: {output_path}")
                return output_path
            except Exception as e:
                logger.error(f"Loop creation failed: {e}")
                raise Exception(f"Failed to create seamless loop: {e}")
    
    def generate_intro(self, template_name: str = 'default') -> str:
        """
        Генерация привлекательной заставки для видео
        Возвращает путь к созданной заставке
        """
        logger.info(f"Generating intro with template: {template_name}")
        
        # Здесь может быть сложная логика генерации заставки
        # Пока создаём простую анимированную заставку
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Создаём последовательность кадров для заставки
            frames_dir = os.path.join(tmp_dir, 'intro_frames')
            os.makedirs(frames_dir)
            
            # Генерируем простую анимацию
            for i in range(60):  # 1 секунда при 60fps
                frame = self._generate_intro_frame(i, template_name)
                frame_path = os.path.join(frames_dir, f"frame_{i:06d}.png")
                frame.save(frame_path)
            
            # Создаём видео
            intro_path = os.path.join(
                self.config['paths']['outputs'],
                'templates',
                f"intro_{template_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            )
            
            self._create_video_from_frames(frames_dir, intro_path, 60)
            logger.info(f"Intro generated: {intro_path}")
            return intro_path
    
    def _generate_intro_frame(self, frame_num: int, template: str):
        """Генерация одного кадра заставки"""
        # TODO: Реализовать реальную генерацию кадров
        # Пока возвращаем заглушку
        from PIL import Image, ImageDraw, ImageFont
        
        width, height = self.config['video']['width'], self.config['video']['height']
        image = Image.new('RGB', (width, height), color=(30, 30, 60))
        draw = ImageDraw.Draw(image)
        
        # Простая анимация текста
        try:
            font = ImageFont.truetype("arial.ttf", 80)
        except:
            font = ImageFont.load_default()
        
        text = "VIDEO PRODUCTION"
        text_width = draw.textlength(text, font=font)
        
        # Анимированная позиция
        x = (width - text_width) / 2
        y = height / 2 + 20 * (frame_num % 30) / 30 - 10
        
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        
        return image
    
    def generate_youtube_metadata(self, video_path: str, 
                                 language: str = 'ru') -> Dict:
        """
        Генерация метаданных для YouTube
        Возвращает заголовок, описание, теги
        """
        logger.info(f"Generating YouTube metadata for: {video_path}")
        
        # Анализируем видео для генерации релевантных метаданных
        # TODO: Интегрировать с Gemini API для умной генерации
        
        metadata = {
            'title': f"Атмосферное видео {datetime.now().strftime('%d.%m.%Y')}",
            'description': self._generate_description(video_path, language),
            'tags': self._generate_tags(language),
            'category': '22',  # People & Blogs
            'privacy': 'private',  # или 'public', 'unlisted'
            'language': language
        }
        
        return metadata
    
    def _generate_description(self, video_path: str, language: str) -> str:
        """Генерация описания для YouTube"""
        base_desc = f"""Атмосферное видео, созданное с помощью AI.
        
📅 Дата создания: {datetime.now().strftime('%d.%m.%Y')}
⏱ Длительность: {utils.get_video_info(video_path).get('duration', 'N/A')} секунд
🎨 Стиль: AI-генерация, цифровое искусство
        
#AIart #DigitalArt #ГенеративноеИскусство #АтмосферноеВидео
"""
        
        if language == 'en':
            base_desc = f"""Atmospheric video created with AI.
            
📅 Creation date: {datetime.now().strftime('%Y-%m-%d')}
⏱ Duration: {utils.get_video_info(video_path).get('duration', 'N/A')} seconds
🎨 Style: AI generation, digital art
            
#AIart #DigitalArt #GenerativeArt #AtmosphericVideo
"""
        
        return base_desc
    
    def _generate_tags(self, language: str) -> List[str]:
        """Генерация тегов для YouTube"""
        if language == 'ru':
            return [
                'AI искусство', 'генеративное искусство', 'цифровое искусство',
                'атмосферное видео', 'релакс видео', 'фон для рабочего стола',
                'медитация', 'успокаивающее видео', 'визуализация'
            ]
        else:
            return [
                'AI art', 'generative art', 'digital art',
                'atmospheric video', 'relax video', 'wallpaper',
                'meditation', 'calming video', 'visualization'
            ]
    
    def finalize_video(self, intro_path: str, main_video_path: str) -> str:
        """
        Финальная сборка: склейка заставки и основного видео
        Возвращает путь к финальному видео
        """
        logger.info(f"Finalizing video: {intro_path} + {main_video_path}")
        
        if not os.path.exists(intro_path) or not os.path.exists(main_video_path):
            raise FileNotFoundError("Intro or main video not found")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Создаём список для конкатенации
            list_file = os.path.join(tmp_dir, 'final_list.txt')
            
            with open(list_file, 'w') as f:
                f.write(f"file '{intro_path}'\n")
                f.write(f"file '{main_video_path}'\n")
            
            # Финальное видео
            final_path = os.path.join(
                self.config['paths']['publish'],
                datetime.now().strftime('%Y-%m-%d'),
                f"final_video_{datetime.now().strftime('%H%M%S')}.mp4"
            )
            
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',
                final_path
            ]
            
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                logger.info(f"Final video saved to: {final_path}")
                return final_path
            except Exception as e:
                logger.error(f"Final assembly failed: {e}")
                raise Exception(f"Failed to assemble final video: {e}")
    
    # Заглушки для локальных методов (требуют установки дополнительных библиотек)
    def _generate_local_images(self, prompt: str) -> List[str]:
        """Локальная генерация изображений (заглушка)"""
        logger.warning("Local image generation not implemented")
        # TODO: Интегрировать с локальной установкой Stable Diffusion
        return []
    
    def _local_upscale(self, image_path: str, scale_factor: int) -> str:
        """Локальный апскейл (заглушка)"""
        logger.warning("Local upscale not implemented")
        # TODO: Интегрировать с Real-ESRGAN или подобным
        return image_path
    
    def _local_super_resolution(self, video_path: str) -> str:
        """Локальный апскейл видео (заглушка)"""
        logger.warning("Local video super resolution not implemented")
        # TODO: Интегрировать с RIFE или подобным
        return video_path


# Глобальный экземпляр для использования в других модулях
video_pipeline = VideoPipeline()
