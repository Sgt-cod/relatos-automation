#!/usr/bin/env python3
"""
Workflow Manager - Coleta informações via Telegram e inicia produção
Roda dentro do GitHub Actions, sem necessidade de servidor externo
FUNCIONALIDADE: Permite cancelar workflow via comando /cancel
FUNCIONALIDADE: Suporta roteiros longos (múltiplas partes + arquivo TXT)
"""

import os
import json
import time
import requests
import sys
from datetime import datetime
from pathlib import Path

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Directories
PRODUCTIONS_DIR = Path('productions')
PRODUCTIONS_DIR.mkdir(exist_ok=True)

# Cancel flag file
CANCEL_FLAG_FILE = Path('productions/cancel_flag.json')

class WorkflowCancelled(Exception):
    """Exception raised when workflow is cancelled by user"""
    pass

class TelegramCollector:
    """Coleta informações via Telegram de forma interativa"""
    
    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        self.chat_id = TELEGRAM_CHAT_ID
        self.update_offset = self._get_last_update_id()
        self.cancelled = False
    
    def _get_last_update_id(self):
        """Obtém o último update_id para não processar mensagens antigas"""
        try:
            url = f"{self.base_url}/getUpdates"
            response = requests.get(url, params={'offset': -1}, timeout=5)
            result = response.json()
            
            if result.get('ok') and result.get('result'):
                return result['result'][0]['update_id'] + 1
            return 0
        except:
            return 0
    
    def send_message(self, text, reply_markup=None):
        """Envia mensagem para o usuário"""
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
            result = response.json()
            if result.get('ok'):
                print(f"✅ Mensagem enviada")
                return True
            else:
                print(f"⚠️ Erro ao enviar: {result}")
                return False
        except Exception as e:
            print(f"❌ Erro: {e}")
            return False
    
    def check_for_cancel(self):
        """Verifica se usuário enviou comando /cancel"""
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
                        
                        with open(CANCEL_FLAG_FILE, 'w') as f:
                            json.dump(cancel_data, f, indent=2)
                        
                        self.send_message(
                            "🛑 <b>WORKFLOW CANCELADO</b>\n\n"
                            "A produção foi cancelada com sucesso.\n"
                            "O workflow será encerrado."
                        )
                        
                        return True
            
            return False
            
        except Exception as e:
            print(f"⚠️ Erro ao verificar cancelamento: {e}")
            return False
    
    def wait_for_message(self, timeout=600, check_cancel_interval=5):
        """Aguarda mensagem do usuário (com verificação de cancelamento)"""
        print(f"⏳ Aguardando resposta (timeout: {timeout}s)...")
        
        start_time = time.time()
        last_reminder = 0
        last_cancel_check = 0
        
        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            if elapsed - last_cancel_check >= check_cancel_interval:
                if self.check_for_cancel():
                    raise WorkflowCancelled("Workflow cancelled by user")
                last_cancel_check = elapsed
            
            if int(elapsed) // 120 > last_reminder:
                remaining = int((timeout - elapsed) / 60)
                self.send_message(
                    f"⏰ Ainda aguardando sua resposta...\n"
                    f"⏱️ {remaining} minutos restantes\n\n"
                    f"💡 Use /cancel para cancelar a produção"
                )
                last_reminder = int(elapsed) // 120
            
            try:
                url = f"{self.base_url}/getUpdates"
                params = {
                    'offset': self.update_offset,
                    'timeout': 10
                }
                
                response = requests.get(url, params=params, timeout=15)
                result = response.json()
                
                if not result.get('ok'):
                    time.sleep(3)
                    continue
                
                updates = result.get('result', [])
                
                for update in updates:
                    self.update_offset = update['update_id'] + 1
                    
                    if 'message' in update:
                        message = update['message']
                        
                        if str(message['chat']['id']) != str(self.chat_id):
                            continue
                        
                        text = message.get('text', '').strip()
                        
                        if text.lower() in ['/cancel', '/cancelar', 'cancel', 'cancelar']:
                            self.cancelled = True
                            cancel_data = {
                                'cancelled': True,
                                'timestamp': datetime.now().isoformat()
                            }
                            with open(CANCEL_FLAG_FILE, 'w') as f:
                                json.dump(cancel_data, f, indent=2)
                            
                            self.send_message("🛑 <b>WORKFLOW CANCELADO</b>")
                            raise WorkflowCancelled("Workflow cancelled by user")
                        
                        if text:
                            print(f"✅ Resposta recebida: {text[:50]}...")
                            return text
            
            except WorkflowCancelled:
                raise
            except Exception as e:
                print(f"⚠️ Erro ao buscar updates: {e}")
                time.sleep(5)
        
        print("⏰ Timeout - sem resposta")
        return None
    
    def collect_script_multipart(self, timeout=900):
        """Coleta roteiro com suporte a múltiplas partes e arquivo TXT"""
        print("\n📝 Coletando roteiro (suporte a múltiplas partes e arquivo)")
        
        self.send_message(
            "4️⃣ <b>ROTEIRO DE NARRAÇÃO</b>\n\n"
            "Você pode enviar de 2 formas:\n\n"
            "📝 <b>Opção 1: Texto Direto</b>\n"
            "Cole o roteiro como mensagem(ns).\n"
            "Se for longo, envie em partes e digite: <b>PRONTO</b>\n\n"
            "📄 <b>Opção 2: Arquivo TXT (RECOMENDADO)</b>\n"
            "Envie arquivo .txt como documento.\n"
            "Sem limite de tamanho!\n\n"
            "💡 Ou digite /cancel para cancelar"
        )
        
        roteiro_partes = []
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            remaining_time = int(timeout - (time.time() - start_time))
            
            if remaining_time <= 0:
                break
            
            try:
                url = f"{self.base_url}/getUpdates"
                params = {
                    'offset': self.update_offset,
                    'timeout': min(30, remaining_time)
                }
                
                response = requests.get(url, params=params, timeout=35)
                result = response.json()
                
                if not result.get('ok'):
                    time.sleep(3)
                    continue
                
                updates = result.get('result', [])
                
                for update in updates:
                    self.update_offset = update['update_id'] + 1
                    
                    if 'message' not in update:
                        continue
                    
                    message = update['message']
                    
                    if str(message['chat']['id']) != str(self.chat_id):
                        continue
                    
                    # VERIFICAR ARQUIVO TXT
                    if 'document' in message:
                        document = message['document']
                        file_name = document.get('file_name', '')
                        
                        if file_name.endswith('.txt'):
                            print(f"📄 Arquivo TXT detectado: {file_name}")
                            self.send_message("📄 Arquivo recebido! Processando...")
                            
                            try:
                                file_id = document['file_id']
                                file_info_url = f"{self.base_url}/getFile"
                                file_resp = requests.get(file_info_url, params={'file_id': file_id}, timeout=10)
                                file_data = file_resp.json()
                                
                                if file_data.get('ok'):
                                    file_path = file_data['result']['file_path']
                                    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                                    
                                    content_resp = requests.get(download_url, timeout=30)
                                    roteiro_completo = content_resp.text
                                    
                                    return roteiro_completo
                            except Exception as e:
                                print(f"❌ Erro ao baixar arquivo: {e}")
                                self.send_message(f"❌ Erro ao processar arquivo. Envie como texto.")
                                continue
                    
                    # VERIFICAR TEXTO
                    text = message.get('text', '').strip()
                    
                    if not text:
                        continue
                    
                    # Cancelamento
                    if text.lower() in ['/cancel', '/cancelar', 'cancel', 'cancelar']:
                        raise WorkflowCancelled("User cancelled")
                    
                    # Finalização
                    if text.upper() in ['PRONTO', 'DONE', 'FIM', 'FINISH']:
                        if not roteiro_partes:
                            self.send_message("⚠️ Nenhum roteiro foi enviado ainda!")
                            continue
                        
                        roteiro_completo = '\n'.join(roteiro_partes)
                        return roteiro_completo
                    
                    # Adicionar parte
                    roteiro_partes.append(text)
                    palavras_atuais = sum(len(p.split()) for p in roteiro_partes)
                    
                    self.send_message(
                        f"✅ <b>Parte {len(roteiro_partes)} recebida!</b>\n\n"
                        f"📊 Palavras até agora: {palavras_atuais}\n\n"
                        f"➕ Envie mais partes se necessário\n"
                        f"✔️ Ou digite <b>PRONTO</b> quando terminar"
                    )
            
            except WorkflowCancelled:
                raise
            except Exception as e:
                print(f"⚠️ Erro: {e}")
                time.sleep(5)
        
        # Timeout ou finalizado
        if roteiro_partes:
            return '\n'.join(roteiro_partes)
        
        return None
    
    def collect_video_info(self):
        """Coleta título, descrição e roteiro via Telegram"""
        print("\n" + "="*60)
        print("📱 COLETANDO INFORMAÇÕES VIA TELEGRAM")
        print("="*60)
        
        try:
            if CANCEL_FLAG_FILE.exists():
                CANCEL_FLAG_FILE.unlink()
            
            self.send_message(
                "🎬 <b>Produção Diária de Vídeo WWII</b>\n\n"
                "Vamos criar um novo vídeo histórico!\n\n"
                "Responda às próximas perguntas para começar.\n"
                "⏱️ Você tem 10 minutos para cada resposta.\n\n"
                "🛑 Use <b>/cancel</b> a qualquer momento para cancelar"
            )
            
            time.sleep(2)
            
            # TÍTULO
            self.send_message(
                "1️⃣ <b>TÍTULO DO VÍDEO</b>\n\n"
                "Envie o título do seu vídeo sobre WWII.\n\n"
                "<i>Exemplo: The Forgotten Heroes of D-Day</i>\n\n"
                "💡 Ou envie /cancel para cancelar"
            )
            
            titulo = self.wait_for_message(timeout=600)
            
            if not titulo:
                self.send_message("❌ Tempo esgotado. Produção cancelada.")
                return None
            
            self.send_message(f"✅ Título recebido!\n\n<b>{titulo}</b>")
            time.sleep(2)
            
            # DESCRIÇÃO
            self.send_message(
                "2️⃣ <b>DESCRIÇÃO DO VÍDEO</b>\n\n"
                "Envie a descrição que aparecerá no YouTube.\n\n"
                "<i>Pode ser de 2 a 3 parágrafos explicando o conteúdo.</i>\n\n"
                "💡 Ou envie /cancel para cancelar"
            )
            
            descricao = self.wait_for_message(timeout=600)
            
            if not descricao:
                self.send_message("❌ Tempo esgotado. Produção cancelada.")
                return None
            
            self.send_message(f"✅ Descrição recebida!\n\n<i>{descricao[:100]}...</i>")
            time.sleep(2)
            
            # TAGS
            self.send_message(
                "3️⃣ <b>TAGS DO VÍDEO</b>\n\n"
                "Envie as tags separadas por vírgula.\n\n"
                "<i>Exemplo: WWII, D-Day, History, Documentary, Normandy</i>\n\n"
                "💡 Ou envie /cancel para cancelar"
            )
            
            tags_text = self.wait_for_message(timeout=600)
            
            if not tags_text:
                self.send_message("❌ Tempo esgotado. Produção cancelada.")
                return None
            
            tags = [tag.strip() for tag in tags_text.split(',')]
            self.send_message(f"✅ Tags recebidas: {len(tags)} tags")
            time.sleep(2)
            
            # ROTEIRO (NOVA FUNÇÃO)
            roteiro = self.collect_script_multipart(timeout=900)
            
            if not roteiro:
                self.send_message("❌ Roteiro não recebido. Produção cancelada.")
                return None
            
            palavra_count = len(roteiro.split())
            tempo_estimado = palavra_count / 150
            preview = roteiro[:200] + '...' if len(roteiro) > 200 else roteiro
            
            self.send_message(
                f"✅ <b>Roteiro recebido!</b>\n\n"
                f"📊 <b>Estatísticas:</b>\n"
                f"• Palavras: {palavra_count}\n"
                f"• Duração estimada: {tempo_estimado:.1f} minutos\n"
                f"• Segmentos (~30s): {int(tempo_estimado * 2)}\n\n"
                f"📝 <b>Prévia:</b>\n<i>{preview}</i>\n\n"
                f"🎬 Iniciando produção..."
            )
            
            video_data = {
                'video_id': f"video_{int(time.time())}",
                'timestamp': datetime.now().isoformat(),
                'title': titulo,
                'description': descricao,
                'tags': tags,
                'script': roteiro,
                'status': 'collected',
                'word_count': palavra_count,
                'estimated_duration': tempo_estimado
            }
            
            production_file = PRODUCTIONS_DIR / f"{video_data['video_id']}.json"
            with open(production_file, 'w', encoding='utf-8') as f:
                json.dump(video_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n✅ Informações coletadas: {production_file}")
            
            return video_data
        
        except WorkflowCancelled:
            print("🛑 Workflow cancelado pelo usuário")
            return None

def main():
    """Função principal do workflow"""
    print("="*60)
    print("🎬 WORKFLOW MANAGER - WWII Video Production")
    print("="*60)
    print(f"⏰ Iniciado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN não configurado!")
        return 1
    
    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID não configurado!")
        return 1
    
    print("✅ Variáveis de ambiente OK")
    print()
    
    try:
        collector = TelegramCollector()
        video_data = collector.collect_video_info()
        
        if not video_data:
            print("\n❌ Falha ao coletar informações. Workflow cancelado.")
            return 1
        
        print("\n✅ Informações coletadas com sucesso!")
        print(f"🎯 Título: {video_data['title']}")
        print(f"📝 Roteiro: {video_data['word_count']} palavras")
        print(f"⏱️ Duração estimada: {video_data['estimated_duration']:.1f} min")
        print()
        
        print("="*60)
        print("🎥 INICIANDO PRODUÇÃO DO VÍDEO")
        print("="*60)
        print()
        
        import create_video
        
        success = create_video.run_production(video_data, collector)
        
        if success:
            print("\n🎉 PRODUÇÃO CONCLUÍDA COM SUCESSO!")
            return 0
        else:
            print("\n❌ Falha na produção do vídeo")
            return 1
    
    except WorkflowCancelled:
        print("\n🛑 WORKFLOW CANCELADO PELO USUÁRIO")
        return 2
    
    except Exception as e:
        print(f"\n❌ Erro durante a produção: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            collector = TelegramCollector()
            collector.send_message(
                f"❌ <b>Erro na Produção</b>\n\n"
                f"Ocorreu um erro:\n\n"
                f"<code>{str(e)}</code>"
            )
        except:
            pass
        
        return 1

if __name__ == '__main__':
    sys.exit(main())
