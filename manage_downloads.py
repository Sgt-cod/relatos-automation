#!/usr/bin/env python3
"""
Gerenciador de Downloads Pendentes
Pode ser executado manualmente ou via comando Telegram
"""

import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
PENDING_FILE = Path('productions/pending_downloads.json')


class DownloadManager:
    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        self.chat_id = TELEGRAM_CHAT_ID
    
    def send_message(self, text, reply_markup=None):
        """Envia mensagem pelo Telegram"""
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
            print(f"Erro ao enviar mensagem: {e}")
            return None
    
    def load_pending(self):
        """Carrega lista de downloads pendentes"""
        if not PENDING_FILE.exists():
            return {}
        
        with open(PENDING_FILE, 'r') as f:
            return json.load(f)
    
    def save_pending(self, data):
        """Salva lista de downloads pendentes"""
        with open(PENDING_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def list_pending(self):
        """Lista todos os downloads pendentes"""
        pending = self.load_pending()
        
        if not pending:
            message = "✅ <b>Nenhum download pendente</b>\n\nTodos os vídeos foram confirmados!"
            self.send_message(message)
            return
        
        message = f"📋 <b>DOWNLOADS PENDENTES</b>\n\n"
        message += f"Total: {len(pending)} vídeo(s)\n\n"
        
        for video_id, info in pending.items():
            timestamp = datetime.fromisoformat(info['timestamp'])
            age = datetime.now() - timestamp
            
            status = "✅ Confirmado" if info.get('confirmed') else "⏳ Aguardando"
            
            message += f"🎬 <b>{info['title']}</b>\n"
            message += f"🆔 ID: <code>{video_id}</code>\n"
            message += f"📦 Tamanho: {info['size_mb']:.1f}MB\n"
            message += f"⏰ Criado: {age.days}d {age.seconds//3600}h atrás\n"
            message += f"📊 Status: {status}\n"
            message += f"🔗 <a href='{info['download_url']}'>Download</a>\n"
            message += "─────────────────\n\n"
        
        # Adiciona botões de ação
        keyboard = {
            "inline_keyboard": [
                [{"text": "🗑️ Limpar Confirmados", "callback_data": "cleanup_confirmed"}],
                [{"text": "⚠️ Limpar Expirados (>24h)", "callback_data": "cleanup_expired"}]
            ]
        }
        
        self.send_message(message, keyboard)
    
    def cleanup_confirmed(self):
        """Remove vídeos já confirmados"""
        pending = self.load_pending()
        confirmed_count = 0
        
        to_remove = []
        for video_id, info in pending.items():
            if info.get('confirmed'):
                video_path = info['video_path']
                
                # Remove arquivo se ainda existir
                if os.path.exists(video_path):
                    try:
                        os.remove(video_path)
                        print(f"🗑️ Removido: {video_path}")
                    except Exception as e:
                        print(f"⚠️ Erro ao remover {video_path}: {e}")
                
                to_remove.append(video_id)
                confirmed_count += 1
        
        # Remove da lista
        for video_id in to_remove:
            del pending[video_id]
        
        self.save_pending(pending)
        
        self.send_message(
            f"✅ <b>Limpeza Concluída</b>\n\n"
            f"🗑️ {confirmed_count} vídeo(s) confirmado(s) removido(s)\n"
            f"📋 {len(pending)} ainda pendente(s)"
        )
    
    def cleanup_expired(self, hours=24):
        """Remove vídeos expirados (>24h sem confirmação)"""
        pending = self.load_pending()
        expired_count = 0
        cutoff = datetime.now() - timedelta(hours=hours)
        
        to_remove = []
        for video_id, info in pending.items():
            timestamp = datetime.fromisoformat(info['timestamp'])
            
            # Se não confirmado e expirado
            if not info.get('confirmed') and timestamp < cutoff:
                video_path = info['video_path']
                
                # Remove arquivo
                if os.path.exists(video_path):
                    try:
                        os.remove(video_path)
                        print(f"🗑️ Removido (expirado): {video_path}")
                    except Exception as e:
                        print(f"⚠️ Erro: {e}")
                
                to_remove.append(video_id)
                expired_count += 1
        
        # Remove da lista
        for video_id in to_remove:
            del pending[video_id]
        
        self.save_pending(pending)
        
        self.send_message(
            f"⚠️ <b>Limpeza de Expirados</b>\n\n"
            f"🗑️ {expired_count} vídeo(s) expirado(s) removido(s)\n"
            f"⏰ Limite: {hours} horas\n"
            f"📋 {len(pending)} ainda pendente(s)"
        )
    
    def confirm_download(self, video_id):
        """Confirma download manualmente via ID"""
        pending = self.load_pending()
        
        if video_id not in pending:
            self.send_message(
                "❌ <b>ID Inválido</b>\n\n"
                f"Vídeo <code>{video_id}</code> não encontrado.\n\n"
                "Use /list para ver downloads pendentes."
            )
            return False
        
        info = pending[video_id]
        video_path = info['video_path']
        
        # Marca como confirmado
        info['confirmed'] = True
        info['confirmed_at'] = datetime.now().isoformat()
        
        # Remove arquivo
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
                print(f"🗑️ Vídeo removido: {video_path}")
                
                self.send_message(
                    "✅ <b>Download Confirmado!</b>\n\n"
                    f"📺 {info['title']}\n"
                    f"📦 {info['size_mb']:.1f}MB\n\n"
                    "🗑️ Vídeo removido do servidor"
                )
            except Exception as e:
                self.send_message(f"⚠️ Erro ao remover: {e}")
        else:
            self.send_message("⚠️ Arquivo já removido")
        
        # Remove da lista
        del pending[video_id]
        self.save_pending(pending)
        
        return True


def main():
    """Função principal - pode ser chamada via GitHub Actions"""
    import sys
    
    manager = DownloadManager()
    
    if len(sys.argv) < 2:
        print("Uso: python manage_downloads.py [list|cleanup|confirm|expired]")
        print("  list     - Lista downloads pendentes")
        print("  cleanup  - Remove downloads confirmados")
        print("  expired  - Remove downloads expirados (>24h)")
        print("  confirm ID - Confirma download por ID")
        return
    
    command = sys.argv[1].lower()
    
    if command == "list":
        manager.list_pending()
    
    elif command == "cleanup":
        manager.cleanup_confirmed()
    
    elif command == "expired":
        manager.cleanup_expired()
    
    elif command == "confirm" and len(sys.argv) == 3:
        video_id = sys.argv[2]
        manager.confirm_download(video_id)
    
    else:
        print("Comando inválido!")


if __name__ == '__main__':
    main()
