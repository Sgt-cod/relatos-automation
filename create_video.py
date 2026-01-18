#!/usr/bin/env python3
"""
WWII History Video Creator
Handles audio generation, media collection, and video assembly
Roda dentro do GitHub Actions - 100% gratuito
"""

import os
import json
import time
import math
import requests
from datetime import datetime
from pathlib import Path

import edge_tts
import asyncio
from pydub import AudioSegment
from moviepy.editor import *
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
YOUTUBE_CREDENTIALS = os.environ.get('YOUTUBE_CREDENTIALS')

# Directories
PRODUCTIONS_DIR = Path('productions')
OUTPUT_DIR = Path('output')
SEGMENTS_DIR = Path('segments')
MEDIA_DIR = Path('media')

# Create directories
for directory in [PRODUCTIONS_DIR, OUTPUT_DIR, SEGMENTS_DIR, MEDIA_DIR]:
    directory.mkdir(exist_ok=True)

class WorkflowCancelled(Exception):
    """Exception raised when workflow is cancelled by user"""
    pass

class TelegramInterface:
    """Handle Telegram communication"""
    
    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        self.chat_id = TELEGRAM_CHAT_ID
        self.update_offset = 0
        self.cancelled = False
        self.cancel_flag_file = Path('productions/cancel_flag.json')
    
    def check_for_cancel(self):
        """Verifica se usuário enviou comando /cancel"""
        # Verificar arquivo de flag primeiro
        if self.cancel_flag_file.exists():
            print("🛑 Flag de cancelamento detectada!")
            return True
        
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                'offset': self.update_offset,
                'timeout': 0
            }
            
            response = requests.get(url, params=params, timeout=5)
            result = response.json()
            
            if not result.get('ok'):
                return False
            
            updates = result.get('result', [])
            
            for update in updates:
                self.update_offset = update['update_id'] + 1
                
                if 'message' in update:
                    message = update['message']
                    
                    if str(message['chat']['id']) != str(self.chat_id):
                        continue
                    
                    text = message.get('text', '').strip().lower()
                    
                    if text in ['/cancel', '/cancelar', 'cancel', 'cancelar']:
                        print("🛑 Comando de cancelamento recebido!")
                        self.cancelled = True
                        
                        cancel_data = {
                            'cancelled': True,
                            'timestamp': datetime.now().isoformat(),
                            'reason': 'User requested cancellation'
                        }
                        
                        with open(self.cancel_flag_file, 'w') as f:
                            json.dump(cancel_data, f, indent=2)
                        
                        self.send_message(
                            "🛑 <b>WORKFLOW CANCELADO</b>\n\n"
                            "A produção foi cancelada com sucesso."
                        )
                        
                        return True
            
            return False
            
        except Exception as e:
            print(f"⚠️ Erro ao verificar cancelamento: {e}")
            return False
    
    def send_message(self, text, reply_markup=None):
        """Send text message"""
        url = f"{self.base_url}/sendMessage"
        data = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        
        try:
            response = requests.post(url, json=data, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Error sending message: {e}")
            return None
    
    def get_updates(self, timeout=30):
        """Get updates from Telegram"""
        url = f"{self.base_url}/getUpdates"
        params = {
            'offset': self.update_offset,
            'timeout': timeout
        }
        
        try:
            response = requests.get(url, params=params, timeout=timeout+5)
            result = response.json()
            
            if result.get('ok') and result.get('result'):
                updates = result['result']
                if updates:
                    self.update_offset = updates[-1]['update_id'] + 1
                return updates
            return []
        except:
            return []
    
    def download_media(self, file_id, output_path):
        """Download media file from Telegram"""
        try:
            # Get file info
            file_info_url = f"{self.base_url}/getFile"
            response = requests.get(file_info_url, params={'file_id': file_id}, timeout=10)
            file_data = response.json()
            
            if not file_data.get('ok'):
                return None
            
            file_path = file_data['result']['file_path']
            download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            
            # Download file
            file_response = requests.get(download_url, timeout=30)
            
            with open(output_path, 'wb') as f:
                f.write(file_response.content)
            
            print(f"✅ Media downloaded: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"❌ Error downloading media: {e}")
            return None
    
    def wait_for_media(self, segment_num, total_segments, timeout=1200):
        """Wait for user to send media via Telegram"""
        print(f"\n📸 Waiting for media {segment_num}/{total_segments}")
        
        self.send_message(
            f"📸 <b>Media Request {segment_num}/{total_segments}</b>\n\n"
            f"🎬 Send an image or short video for segment {segment_num}\n"
            f"⏱️ This segment is approximately 30 seconds\n\n"
            f"💡 <b>Tips:</b>\n"
            f"• Use historical photos/footage\n"
            f"• High resolution (1920x1080 preferred)\n"
            f"• Related to the narration\n\n"
            f"⏰ Waiting for {timeout//60} minutes...\n\n"
            f"🛑 Use /cancel to cancel production"
        )
        
        start_time = time.time()
        last_reminder = 0
        last_cancel_check = 0
        
        while time.time() - start_time < timeout:
            # Verificar cancelamento a cada 5 segundos
            elapsed = time.time() - start_time
            if elapsed - last_cancel_check >= 5:
                if self.check_for_cancel():
                    raise WorkflowCancelled("Workflow cancelled by user")
                last_cancel_check = elapsed
            
            # Reminder every 3 minutes
            if int(elapsed) // 180 > last_reminder:
                remaining = int((timeout - elapsed) / 60)
                self.send_message(
                    f"⏳ Still waiting for media {segment_num}/{total_segments}\n"
                    f"⏰ {remaining} minutes remaining\n\n"
                    f"💡 Use /cancel to cancel"
                )
                last_reminder = int(elapsed) // 180
            
            updates = self.get_updates(timeout=10)
            
            for update in updates:
                if 'message' not in update:
                    continue
                
                message = update['message']
                
                # Verificar cancelamento
                text = message.get('text', '').strip().lower()
                if text in ['/cancel', '/cancelar', 'cancel', 'cancelar']:
                    self.cancelled = True
                    cancel_data = {
                        'cancelled': True,
                        'timestamp': datetime.now().isoformat()
                    }
                    with open(self.cancel_flag_file, 'w') as f:
                        json.dump(cancel_data, f, indent=2)
                    
                    self.send_message("🛑 <b>WORKFLOW CANCELADO</b>")
                    raise WorkflowCancelled("Workflow cancelled by user")
                
                # Check for photo
                if 'photo' in message:
                    photo = message['photo'][-1]
                    file_id = photo['file_id']
                    
                    output_path = MEDIA_DIR / f"segment_{segment_num:03d}.jpg"
                    result = self.download_media(file_id, output_path)
                    
                    if result:
                        self.send_message(f"✅ Media {segment_num}/{total_segments} received!")
                        return str(output_path), 'image'
                
                # Check for video
                elif 'video' in message:
                    video = message['video']
                    file_id = video['file_id']
                    
                    output_path = MEDIA_DIR / f"segment_{segment_num:03d}.mp4"
                    result = self.download_media(file_id, output_path)
                    
                    if result:
                        self.send_message(f"✅ Media {segment_num}/{total_segments} received!")
                        return str(output_path), 'video'
                
                # Check for document
                elif 'document' in message:
                    document = message['document']
                    mime_type = document.get('mime_type', '')
                    
                    if mime_type.startswith('image/'):
                        file_id = document['file_id']
                        ext = mime_type.split('/')[-1]
                        
                        output_path = MEDIA_DIR / f"segment_{segment_num:03d}.{ext}"
                        result = self.download_media(file_id, output_path)
                        
                        if result:
                            self.send_message(f"✅ Media {segment_num}/{total_segments} received!")
                            return str(output_path), 'image'
            
            time.sleep(2)
        
        self.send_message(f"⏰ Timeout waiting for media {segment_num}")
        return None, None

class VideoProducer:
    """Main video production class"""
    
    def __init__(self, video_data):
        self.video_id = video_data['video_id']
        self.script = video_data['script']
        self.title = video_data['title']
        self.description = video_data['description']
        self.tags = video_data['tags']
        self.telegram = TelegramInterface()
        
        self.production_file = PRODUCTIONS_DIR / f"{self.video_id}.json"
    
    async def generate_audio(self):
        """Generate narration audio from script"""
        print("\n🎙️ Generating narration audio...")
        
        audio_path = SEGMENTS_DIR / f"{self.video_id}_full_audio.mp3"
        
        # Use Edge TTS with American English voice
        voice = "pt-BR-ThalitaMultilingualNeural"  # Professional male American voice
        # Alternative: "en-US-JennyNeural" for female voice
        
        try:
            communicate = edge_tts.Communicate(
                self.script,
                voice,
                rate="+0%",
                pitch="+0Hz"
            )
            
            await communicate.save(str(audio_path))
            print(f"✅ Audio generated: {audio_path}")
            
            self.telegram.send_message(
                "🎙️ <b>Audio Generated!</b>\n\n"
                "Narration created successfully.\n"
                "Now segmenting audio..."
            )
            
            return str(audio_path)
            
        except Exception as e:
            print(f"❌ Error generating audio: {e}")
            raise
    
    def segment_audio(self, audio_path, segment_duration=30000):
        """Split audio into 30-second segments"""
        print(f"\n✂️ Segmenting audio into {segment_duration/1000}s chunks...")
        
        # Load audio
        audio = AudioSegment.from_mp3(audio_path)
        total_duration = len(audio)
        
        # Calculate number of segments
        num_segments = math.ceil(total_duration / segment_duration)
        
        print(f"📊 Total duration: {total_duration/1000:.1f}s")
        print(f"📊 Number of segments: {num_segments}")
        
        self.telegram.send_message(
            f"✂️ <b>Audio Segmented</b>\n\n"
            f"📊 Total duration: {total_duration/1000:.1f} seconds\n"
            f"📊 Number of segments: {num_segments}\n\n"
            f"Now I'll request media for each segment..."
        )
        
        segments = []
        
        for i in range(num_segments):
            start = i * segment_duration
            end = min((i + 1) * segment_duration, total_duration)
            
            segment = audio[start:end]
            segment_path = SEGMENTS_DIR / f"{self.video_id}_segment_{i+1:03d}.mp3"
            
            segment.export(str(segment_path), format="mp3")
            
            segments.append({
                'index': i + 1,
                'path': str(segment_path),
                'duration': len(segment) / 1000,  # in seconds
                'start_time': start / 1000,
                'end_time': end / 1000
            })
            
            print(f"  ✅ Segment {i+1}: {len(segment)/1000:.1f}s")
        
        return segments
    
    def collect_media(self, segments):
        """Collect media for each segment via Telegram"""
        print(f"\n📸 Collecting media for {len(segments)} segments...")
        
        self.telegram.send_message(
            f"📸 <b>Starting Media Collection</b>\n\n"
            f"📊 Total segments: {len(segments)}\n"
            f"⏱️ ~30 seconds each\n\n"
            f"I'll request media for each segment.\n"
            f"Please send images or short videos in order.\n\n"
            f"⏰ You have 20 minutes per segment."
        )
        
        time.sleep(3)
        
        media_list = []
        
        for i, segment in enumerate(segments, 1):
            media_path, media_type = self.telegram.wait_for_media(
                i,
                len(segments),
                timeout=1200  # 20 minutes per segment
            )
            
            if not media_path:
                self.telegram.send_message(
                    f"⚠️ No media received for segment {i}\n"
                    f"Using placeholder..."
                )
                # Create black placeholder
                media_path = self.create_placeholder(i)
                media_type = 'image'
            
            media_list.append({
                'segment_index': i,
                'path': media_path,
                'type': media_type,
                'duration': segment['duration']
            })
        
        self.telegram.send_message(
            f"✅ <b>All Media Collected!</b>\n\n"
            f"Received {len(media_list)} media files.\n"
            f"Now creating the video..."
        )
        
        return media_list
    
    def create_placeholder(self, segment_num):
        """Create black placeholder image"""
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGB', (1920, 1080), color=(20, 20, 20))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
        except:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 80)
            except:
                font = ImageFont.load_default()
        
        text = f"Segment {segment_num}"
        
        # Usar textbbox se disponível (Pillow >= 8.0.0)
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            # Fallback para versões antigas do Pillow
            text_width, text_height = draw.textsize(text, font=font)
        
        position = ((1920 - text_width) // 2, (1080 - text_height) // 2)
        draw.text(position, text, fill=(100, 100, 100), font=font)
        
        output_path = MEDIA_DIR / f"placeholder_{segment_num:03d}.jpg"
        img.save(output_path, quality=95)
        
        return str(output_path)
    
    def request_background_music(self, timeout=600):
        """Request background music from user via Telegram"""
        print("\n🎵 Requesting background music...")
        
        self.telegram.send_message(
            "🎵 <b>MÚSICA DE FUNDO (Opcional)</b>\n\n"
            "📻 Envie uma música instrumental para o vídeo:\n\n"
            "💡 <b>Recomendações:</b>\n"
            "• Música INSTRUMENTAL (sem letra)\n"
            "• Estilo épico/cinematográfico\n"
            "• Formato: MP3 ou M4A\n"
            "• Duração: qualquer (será ajustada)\n\n"
            f"⏰ Você tem {timeout//60} minutos\n\n"
            "⏭️ Digite <b>/skip</b> para vídeo sem música de fundo"
        )
        
        start_time = time.time()
        last_reminder = 0
        
        while time.time() - start_time < timeout:
            # Check for cancellation
            elapsed = time.time() - start_time
            if elapsed - last_reminder >= 5:
                if self.telegram.check_for_cancel():
                    raise WorkflowCancelled("Workflow cancelled by user")
            
            # Reminder every 2 minutes
            if int(elapsed) // 120 > last_reminder:
                remaining = int((timeout - elapsed) / 60)
                self.telegram.send_message(
                    f"⏳ Ainda aguardando música de fundo...\n"
                    f"⏰ {remaining} minutos restantes\n\n"
                    f"⏭️ Digite /skip para sem música"
                )
                last_reminder = int(elapsed) // 120
            
            updates = self.telegram.get_updates(timeout=10)
            
            for update in updates:
                if 'message' not in update:
                    continue
                
                message = update['message']
                
                # Check for skip command
                text = message.get('text', '').strip().lower()
                if text in ['/skip', 'skip', '/pular', 'pular']:
                    self.telegram.send_message(
                        "⏭️ <b>Música Pulada</b>\n\n"
                        "Vídeo será criado sem música de fundo."
                    )
                    return None
                
                # Check for cancellation
                if text in ['/cancel', '/cancelar', 'cancel', 'cancelar']:
                    self.telegram.cancelled = True
                    cancel_data = {
                        'cancelled': True,
                        'timestamp': datetime.now().isoformat()
                    }
                    with open(self.telegram.cancel_flag_file, 'w') as f:
                        json.dump(cancel_data, f, indent=2)
                    
                    self.telegram.send_message("🛑 <b>WORKFLOW CANCELADO</b>")
                    raise WorkflowCancelled("Workflow cancelled by user")
                
                # Check for audio/document
                if 'audio' in message:
                    audio = message['audio']
                    file_id = audio['file_id']
                    
                    output_path = SEGMENTS_DIR / 'background_music.mp3'
                    result = self.telegram.download_media(file_id, output_path)
                    
                    if result:
                        self.telegram.send_message(
                            "✅ <b>Música Recebida!</b>\n\n"
                            "A música será aplicada com volume baixo."
                        )
                        return str(output_path)
                
                elif 'document' in message:
                    document = message['document']
                    mime_type = document.get('mime_type', '')
                    
                    if mime_type.startswith('audio/') or document.get('file_name', '').endswith(('.mp3', '.m4a', '.wav')):
                        file_id = document['file_id']
                        
                        output_path = SEGMENTS_DIR / 'background_music.mp3'
                        result = self.telegram.download_media(file_id, output_path)
                        
                        if result:
                            self.telegram.send_message(
                                "✅ <b>Música Recebida!</b>\n\n"
                                "A música será aplicada com volume baixo."
                            )
                            return str(output_path)
            
            time.sleep(2)
        
        self.telegram.send_message(
            "⏰ <b>Timeout</b>\n\n"
            "Vídeo será criado sem música de fundo."
        )
        return None
    
    def request_channel_logo(self, timeout=600):
        """Request channel logo from user via Telegram"""
        print("\n🖼️ Requesting channel logo...")
        
        self.telegram.send_message(
            "🖼️ <b>LOGO DO CANAL (Opcional)</b>\n\n"
            "📺 Envie a imagem de perfil do seu canal:\n\n"
            "💡 <b>Recomendações:</b>\n"
            "• Imagem quadrada (1:1)\n"
            "• PNG com fundo transparente (ideal)\n"
            "• Resolução: 800x800 ou maior\n"
            "• Logo ficará no canto inferior direito\n\n"
            f"⏰ Você tem {timeout//60} minutos\n\n"
            "⏭️ Digite <b>/skip</b> para vídeo sem logo"
        )
        
        start_time = time.time()
        last_reminder = 0
        
        while time.time() - start_time < timeout:
            # Check for cancellation
            elapsed = time.time() - start_time
            if elapsed - last_reminder >= 5:
                if self.telegram.check_for_cancel():
                    raise WorkflowCancelled("Workflow cancelled by user")
            
            # Reminder every 2 minutes
            if int(elapsed) // 120 > last_reminder:
                remaining = int((timeout - elapsed) / 60)
                self.telegram.send_message(
                    f"⏳ Ainda aguardando logo do canal...\n"
                    f"⏰ {remaining} minutos restantes\n\n"
                    f"⏭️ Digite /skip para sem logo"
                )
                last_reminder = int(elapsed) // 120
            
            updates = self.telegram.get_updates(timeout=10)
            
            for update in updates:
                if 'message' not in update:
                    continue
                
                message = update['message']
                
                # Check for skip command
                text = message.get('text', '').strip().lower()
                if text in ['/skip', 'skip', '/pular', 'pular']:
                    self.telegram.send_message(
                        "⏭️ <b>Logo Pulado</b>\n\n"
                        "Vídeo será criado sem logo do canal."
                    )
                    return None
                
                # Check for cancellation
                if text in ['/cancel', '/cancelar', 'cancel', 'cancelar']:
                    self.telegram.cancelled = True
                    cancel_data = {
                        'cancelled': True,
                        'timestamp': datetime.now().isoformat()
                    }
                    with open(self.telegram.cancel_flag_file, 'w') as f:
                        json.dump(cancel_data, f, indent=2)
                    
                    self.telegram.send_message("🛑 <b>WORKFLOW CANCELADO</b>")
                    raise WorkflowCancelled("Workflow cancelled by user")
                
                # Check for photo
                if 'photo' in message:
                    photo = message['photo'][-1]
                    file_id = photo['file_id']
                    
                    output_path = SEGMENTS_DIR / 'channel_logo.png'
                    result = self.telegram.download_media(file_id, output_path)
                    
                    if result:
                        self.telegram.send_message(
                            "✅ <b>Logo Recebida!</b>\n\n"
                            "Logo aparecerá no canto inferior direito."
                        )
                        return str(output_path)
                
                # Check for document
                elif 'document' in message:
                    document = message['document']
                    mime_type = document.get('mime_type', '')
                    
                    if mime_type.startswith('image/'):
                        file_id = document['file_id']
                        ext = mime_type.split('/')[-1]
                        
                        output_path = SEGMENTS_DIR / f'channel_logo.{ext}'
                        result = self.telegram.download_media(file_id, output_path)
                        
                        if result:
                            self.telegram.send_message(
                                "✅ <b>Logo Recebida!</b>\n\n"
                                "Logo aparecerá no canto inferior direito."
                            )
                            return str(output_path)
            
            time.sleep(2)
        
        self.telegram.send_message(
            "⏰ <b>Timeout</b>\n\n"
            "Vídeo será criado sem logo do canal."
        )
        return None
    
    def create_video(self, audio_segments, media_list, background_music=None, channel_logo=None):
        """Create final video from segments and media"""
        print("\n🎬 Creating final video...")
        
        clips = []
        
        for i, (audio_seg, media_info) in enumerate(zip(audio_segments, media_list)):
            print(f"\n  Processing segment {i+1}/{len(audio_segments)}")
            
            # Load audio
            audio_clip = AudioFileClip(audio_seg['path'])
            duration = audio_clip.duration
            
            # Load media
            if media_info['type'] == 'image':
                # Create image clip with Ken Burns effect
                img_clip = ImageClip(media_info['path'])
                
                # Resize to fit 1920x1080
                img_clip = img_clip.resize(height=1080)
                if img_clip.w < 1920:
                    img_clip = img_clip.resize(width=1920)
                
                # Center crop
                img_clip = img_clip.crop(
                    x_center=img_clip.w/2,
                    y_center=img_clip.h/2,
                    width=1920,
                    height=1080
                )
                
                # Add subtle zoom effect (Ken Burns)
                img_clip = img_clip.resize(lambda t: 1 + 0.05 * (t / duration))
                img_clip = img_clip.set_duration(duration)
                
            else:  # video
                video_clip = VideoFileClip(media_info['path'])
                
                # Resize and crop to 1920x1080
                video_clip = video_clip.resize(height=1080)
                if video_clip.w < 1920:
                    video_clip = video_clip.resize(width=1920)
                
                video_clip = video_clip.crop(
                    x_center=video_clip.w/2,
                    y_center=video_clip.h/2,
                    width=1920,
                    height=1080
                )
                
                # Loop if necessary
                if video_clip.duration < duration:
                    video_clip = video_clip.loop(duration=duration)
                else:
                    video_clip = video_clip.subclip(0, duration)
                
                img_clip = video_clip
            
            # Set audio
            img_clip = img_clip.set_audio(audio_clip)
            
            # Add fade in/out
            if i == 0:
                img_clip = img_clip.fadein(1)
            if i == len(audio_segments) - 1:
                img_clip = img_clip.fadeout(1)
            
            clips.append(img_clip)
            
            print(f"    ✅ Segment {i+1} processed ({duration:.1f}s)")
        
    def create_video(self, audio_segments, media_list, background_music=None, channel_logo=None):
        """Create final video from segments and media with optional music and logo"""
        print("\n🎬 Creating final video...")
        
        clips = []
        
        for i, (audio_seg, media_info) in enumerate(zip(audio_segments, media_list)):
            print(f"\n  Processing segment {i+1}/{len(audio_segments)}")
            
            # Load audio
            audio_clip = AudioFileClip(audio_seg['path'])
            duration = audio_clip.duration
            
            # Load media
            if media_info['type'] == 'image':
                # Create image clip with Ken Burns effect
                img_clip = ImageClip(media_info['path'])
                
                # Resize to fit 1920x1080
                img_clip = img_clip.resize(height=1080)
                if img_clip.w < 1920:
                    img_clip = img_clip.resize(width=1920)
                
                # Center crop
                img_clip = img_clip.crop(
                    x_center=img_clip.w/2,
                    y_center=img_clip.h/2,
                    width=1920,
                    height=1080
                )
                
                # Add subtle zoom effect (Ken Burns)
                img_clip = img_clip.resize(lambda t: 1 + 0.05 * (t / duration))
                img_clip = img_clip.set_duration(duration)
                
            else:  # video
                video_clip = VideoFileClip(media_info['path'])
                
                # Resize and crop to 1920x1080
                video_clip = video_clip.resize(height=1080)
                if video_clip.w < 1920:
                    video_clip = video_clip.resize(width=1920)
                
                video_clip = video_clip.crop(
                    x_center=video_clip.w/2,
                    y_center=video_clip.h/2,
                    width=1920,
                    height=1080
                )
                
                # Loop if necessary
                if video_clip.duration < duration:
                    video_clip = video_clip.loop(duration=duration)
                else:
                    video_clip = video_clip.subclip(0, duration)
                
                img_clip = video_clip
            
            # Set audio
            img_clip = img_clip.set_audio(audio_clip)
            
            # Add fade in/out
            if i == 0:
                img_clip = img_clip.fadein(1)
            if i == len(audio_segments) - 1:
                img_clip = img_clip.fadeout(1)
            
            clips.append(img_clip)
            
            print(f"    ✅ Segment {i+1} processed ({duration:.1f}s)")
        
        # Concatenate all clips
        print("\n  Concatenating segments...")
        final_video = concatenate_videoclips(clips, method="compose")
        
        # Add channel logo if provided
        if channel_logo and os.path.exists(channel_logo):
            print("\n  Adding channel logo...")
            try:
                from PIL import Image
                
                # Load and resize logo
                logo_img = Image.open(channel_logo)
                
                # Convert to RGBA if not already
                if logo_img.mode != 'RGBA':
                    logo_img = logo_img.convert('RGBA')
                
                # Resize logo (150x150 pixels)
                logo_size = 150
                logo_img = logo_img.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                
                # Save temporary logo
                temp_logo_path = SEGMENTS_DIR / 'logo_resized.png'
                logo_img.save(temp_logo_path)
                
                # Create logo clip
                logo_clip = ImageClip(str(temp_logo_path))
                logo_clip = logo_clip.set_duration(final_video.duration)
                
                # Position: bottom-right corner with padding
                logo_clip = logo_clip.set_position((1920 - logo_size - 30, 1080 - logo_size - 30))
                
                # Add subtle fade in/out
                logo_clip = logo_clip.fadein(1).fadeout(1)
                
                # Composite logo over video
                final_video = CompositeVideoClip([final_video, logo_clip])
                
                print("    ✅ Logo added successfully")
                
            except Exception as e:
                print(f"    ⚠️ Failed to add logo: {e}")
        
        # Process background music if provided
        if background_music and os.path.exists(background_music):
            print("\n  Adding background music...")
            try:
                # Load background music
                bg_music = AudioFileClip(background_music)
                
                # Loop music if shorter than video
                if bg_music.duration < final_video.duration:
                    # Calculate how many loops needed
                    loops_needed = int(final_video.duration / bg_music.duration) + 1
                    bg_music_list = [bg_music] * loops_needed
                    bg_music = concatenate_audioclips(bg_music_list)
                
                # Trim to video duration
                bg_music = bg_music.subclip(0, final_video.duration)
                
                # Reduce volume to 15% (very low, won't interfere with narration)
                bg_music = bg_music.volumex(0.15)
                
                # Mix with original audio (narration)
                original_audio = final_video.audio
                
                # Composite audios
                from moviepy.audio.AudioClip import CompositeAudioClip
                final_audio = CompositeAudioClip([original_audio, bg_music])
                
                # Set final audio
                final_video = final_video.set_audio(final_audio)
                
                print("    ✅ Background music added (volume: 15%)")
                
            except Exception as e:
                print(f"    ⚠️ Failed to add music: {e}")
        
        # Export
        output_path = OUTPUT_DIR / f"{self.video_id}.mp4"
        
        print(f"\n  💾 Rendering final video...")
        print(f"     Duration: {final_video.duration:.1f}s")
        print(f"     Resolution: 1920x1080")
        
        features = []
        if background_music:
            features.append("background music")
        if channel_logo:
            features.append("channel logo")
        
        if features:
            print(f"     Features: {', '.join(features)}")
        
        self.telegram.send_message(
            "🎬 <b>Creating Final Video</b>\n\n"
            f"⏱️ Duration: {final_video.duration:.1f} seconds\n"
            "📹 Resolution: 1920x1080\n"
            f"🎵 Music: {'Yes (low volume)' if background_music else 'No'}\n"
            f"🖼️ Logo: {'Yes (bottom-right)' if channel_logo else 'No'}\n\n"
            "🎞️ Rendering... This may take a while."
        )
        
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec='libx264',
            audio_codec='aac',
            preset='medium',
            bitrate='5000k',
            threads=4
        )
        
        # Close clips
        final_video.close()
        for clip in clips:
            clip.close()
        
        print(f"\n✅ Video created: {output_path}")
        return str(output_path)
    
    def request_thumbnail(self, timeout=1200):
        """Request thumbnail from user via Telegram"""
        print("\n🖼️ Requesting thumbnail...")
        
        self.telegram.send_message(
            "🖼️ <b>THUMBNAIL CUSTOMIZADA</b>\n\n"
            "📺 <b>Última etapa antes do upload!</b>\n\n"
            "📤 Envie agora a imagem da thumbnail:\n\n"
            "💡 <b>Recomendações:</b>\n"
            "• Resolução mínima: 1280x720 (HD)\n"
            "• Ideal: 1920x1080 (Full HD)\n"
            "• Formato: JPG ou PNG\n"
            "• Texto grande e legível\n"
            "• Cores vibrantes\n"
            "• Relacionada ao vídeo\n\n"
            f"⏰ Você tem {timeout//60} minutos\n\n"
            "⏭️ Digite <b>/skip</b> para usar thumbnail automática do YouTube"
        )
        
        start_time = time.time()
        last_reminder = 0
        
        while time.time() - start_time < timeout:
            # Check for cancellation
            elapsed = time.time() - start_time
            if elapsed - last_reminder >= 5:
                if self.telegram.check_for_cancel():
                    raise WorkflowCancelled("Workflow cancelled by user")
            
            # Reminder every 3 minutes
            if int(elapsed) // 180 > last_reminder:
                remaining = int((timeout - elapsed) / 60)
                self.telegram.send_message(
                    f"⏳ Ainda aguardando thumbnail...\n"
                    f"⏰ {remaining} minutos restantes\n\n"
                    f"⏭️ Digite /skip para usar thumbnail automática"
                )
                last_reminder = int(elapsed) // 180
            
            updates = self.telegram.get_updates(timeout=10)
            
            for update in updates:
                if 'message' not in update:
                    continue
                
                message = update['message']
                
                # Check for skip command
                text = message.get('text', '').strip().lower()
                if text in ['/skip', 'skip', '/pular', 'pular']:
                    self.telegram.send_message(
                        "⏭️ <b>Thumbnail Pulada</b>\n\n"
                        "Usando thumbnail automática do YouTube."
                    )
                    return None
                
                # Check for cancellation
                if text in ['/cancel', '/cancelar', 'cancel', 'cancelar']:
                    self.telegram.cancelled = True
                    cancel_data = {
                        'cancelled': True,
                        'timestamp': datetime.now().isoformat()
                    }
                    with open(self.telegram.cancel_flag_file, 'w') as f:
                        json.dump(cancel_data, f, indent=2)
                    
                    self.telegram.send_message("🛑 <b>WORKFLOW CANCELADO</b>")
                    raise WorkflowCancelled("Workflow cancelled by user")
                
                # Check for photo
                if 'photo' in message:
                    photo = message['photo'][-1]
                    file_id = photo['file_id']
                    
                    output_path = OUTPUT_DIR / 'thumbnail_custom.jpg'
                    result = self.telegram.download_media(file_id, output_path)
                    
                    if result:
                        self.telegram.send_message(
                            "✅ <b>Thumbnail Recebida!</b>\n\n"
                            "Fazendo upload do vídeo com sua thumbnail..."
                        )
                        return str(output_path)
                
                # Check for document (high-res image)
                elif 'document' in message:
                    document = message['document']
                    mime_type = document.get('mime_type', '')
                    
                    if mime_type.startswith('image/'):
                        file_id = document['file_id']
                        ext = mime_type.split('/')[-1]
                        
                        output_path = OUTPUT_DIR / f'thumbnail_custom.{ext}'
                        result = self.telegram.download_media(file_id, output_path)
                        
                        if result:
                            self.telegram.send_message(
                                "✅ <b>Thumbnail Recebida!</b>\n\n"
                                "Fazendo upload do vídeo com sua thumbnail..."
                            )
                            return str(output_path)
            
            time.sleep(2)
        
        self.telegram.send_message(
            "⏰ <b>Timeout</b>\n\n"
            "Usando thumbnail automática do YouTube."
        )
        return None
    
    def upload_to_youtube(self, video_path, thumbnail_path=None):
        """Upload video to YouTube with optional custom thumbnail"""
        print("\n📤 Uploading to YouTube...")
        
        self.telegram.send_message(
            "📤 <b>Uploading to YouTube</b>\n\n"
            "Please wait..."
        )
        
        try:
            # Load credentials
            creds_dict = json.loads(YOUTUBE_CREDENTIALS)
            credentials = Credentials.from_authorized_user_info(creds_dict)
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Prepare metadata
            body = {
                'snippet': {
                    'title': self.title[:100],  # YouTube limit
                    'description': self.description,
                    'tags': self.tags,
                    'categoryId': '22'  # People & Blogs (or '27' for Education)
                },
                'status': {
                    'privacyStatus': 'public',
                    'selfDeclaredMadeForKids': False
                }
            }
            
            # Upload video
            media = MediaFileUpload(video_path, resumable=True)
            request = youtube.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media
            )
            
            print("  Uploading video...")
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    print(f"    Progress: {progress}%")
            
            video_id = response['id']
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            print(f"\n✅ Video uploaded successfully!")
            print(f"🔗 URL: {url}")
            
            # Upload thumbnail if provided
            if thumbnail_path and os.path.exists(thumbnail_path):
                print("\n🖼️ Uploading custom thumbnail...")
                try:
                    thumbnail_media = MediaFileUpload(thumbnail_path)
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=thumbnail_media
                    ).execute()
                    print("✅ Thumbnail uploaded!")
                    
                    self.telegram.send_message(
                        f"🎉 <b>VIDEO PUBLISHED!</b>\n\n"
                        f"📺 {self.title}\n"
                        f"🔗 {url}\n\n"
                        f"✅ Video uploaded to YouTube!\n"
                        f"✅ Custom thumbnail applied!\n\n"
                        f"🎬 Production complete!"
                    )
                except Exception as e:
                    error_msg = str(e)
                    print(f"⚠️ Thumbnail upload failed: {error_msg}")
                    
                    # Check if it's a verification issue
                    if 'forbidden' in error_msg.lower() or 'permission' in error_msg.lower():
                        self.telegram.send_message(
                            f"🎉 <b>VIDEO PUBLISHED!</b>\n\n"
                            f"📺 {self.title}\n"
                            f"🔗 {url}\n\n"
                            f"✅ Video uploaded successfully!\n\n"
                            f"⚠️ <b>Thumbnail NOT uploaded</b>\n\n"
                            f"❗ <b>Verificação necessária:</b>\n"
                            f"Seu canal precisa ser verificado por telefone para usar thumbnails customizadas.\n\n"
                            f"📱 <b>Como resolver:</b>\n"
                            f"1. Acesse: https://www.youtube.com/verify\n"
                            f"2. Verifique seu número de telefone\n"
                            f"3. Aguarde aprovação (pode levar 24h)\n\n"
                            f"🖼️ <b>Fazer upload manual agora:</b>\n"
                            f"1. Vá para: https://studio.youtube.com/video/{video_id}/edit\n"
                            f"2. Clique em 'Thumbnail' no lado direito\n"
                            f"3. Faça upload da imagem que você enviou\n\n"
                            f"💡 Após verificar o canal, thumbnails futuras serão automáticas!"
                        )
                        
                        # Also save thumbnail info for manual upload
                        thumbnail_info = {
                            'video_id': video_id,
                            'video_url': url,
                            'thumbnail_path': thumbnail_path,
                            'upload_url': f"https://studio.youtube.com/video/{video_id}/edit",
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        thumb_log_file = OUTPUT_DIR / 'pending_thumbnails.json'
                        pending_thumbs = []
                        
                        if thumb_log_file.exists():
                            with open(thumb_log_file, 'r') as f:
                                pending_thumbs = json.load(f)
                        
                        pending_thumbs.append(thumbnail_info)
                        
                        with open(thumb_log_file, 'w') as f:
                            json.dump(pending_thumbs, f, indent=2)
                        
                    else:
                        self.telegram.send_message(
                            f"🎉 <b>VIDEO PUBLISHED!</b>\n\n"
                            f"📺 {self.title}\n"
                            f"🔗 {url}\n\n"
                            f"✅ Video uploaded!\n"
                            f"⚠️ Thumbnail upload failed: {error_msg}\n\n"
                            f"🖼️ Upload manual:\n"
                            f"https://studio.youtube.com/video/{video_id}/edit\n\n"
                            f"🎬 Production complete!"
                        )
            else:
                self.telegram.send_message(
                    f"🎉 <b>VIDEO PUBLISHED!</b>\n\n"
                    f"📺 {self.title}\n"
                    f"🔗 {url}\n\n"
                    f"✅ Video uploaded to YouTube!\n"
                    f"📸 Using automatic thumbnail\n\n"
                    f"🎬 Production complete!"
                )
            
            return url
            
        except Exception as e:
            print(f"❌ Upload failed: {e}")
            self.telegram.send_message(f"❌ YouTube upload failed: {e}")
            raise
    
    async def run(self):
        """Main production workflow"""
        try:
            self.telegram.send_message(
                f"🎬 <b>Production Started</b>\n\n"
                f"🎯 Video: {self.title}\n"
                f"🆔 ID: {self.video_id}\n\n"
                f"Starting audio generation..."
            )
            
            # Step 1: Generate audio
            audio_path = await self.generate_audio()
            
            # Step 2: Segment audio
            audio_segments = self.segment_audio(audio_path)
            
            # Step 3: Collect media
            media_list = self.collect_media(audio_segments)
            
            # Step 4: Request background music (NEW!)
            background_music = self.request_background_music(timeout=600)  # 10 minutes
            
            # Step 5: Request channel logo (NEW!)
            channel_logo = self.request_channel_logo(timeout=600)  # 10 minutes
            
            # Step 6: Create video with music and logo
            self.telegram.send_message("🎥 Creating final video with all features...")
            video_path = self.create_video(audio_segments, media_list, background_music, channel_logo)
            
            # Step 7: Request thumbnail
            thumbnail_path = self.request_thumbnail(timeout=1200)  # 20 minutes
            
            # Step 8: Upload to YouTube with thumbnail
            url = self.upload_to_youtube(video_path, thumbnail_path)
            
            print("\n✅ Production completed successfully!")
            return True
            
        except Exception as e:
            print(f"\n❌ Production failed: {e}")
            self.telegram.send_message(f"❌ <b>Production Failed</b>\n\n{e}")
            raise

def run_production(video_data, collector=None):
    """Main entry point called by workflow_manager"""
    print("="*60)
    print("🎬 WWII History Video Production")
    print("="*60)
    
    print(f"\n🆔 Video ID: {video_data['video_id']}")
    print(f"📝 Title: {video_data['title']}")
    print(f"📊 Script: {video_data['word_count']} words")
    print()
    
    async def run_async():
        producer = VideoProducer(video_data)
        return await producer.run()
    
    try:
        result = asyncio.run(run_async())
        return result
    except WorkflowCancelled:
        print("\n🛑 PRODUÇÃO CANCELADA PELO USUÁRIO")
        if collector:
            collector.send_message(
                "🛑 <b>Produção Cancelada</b>\n\n"
                "O workflow foi encerrado conforme solicitado."
            )
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
