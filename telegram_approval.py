"""
telegram_approval.py

Checkpoint humano do pipeline. Diferente da versão anterior (dois
workflows separados, dependendo do cron de 5 em 5 min rodar em dia),
esta versão segue o mesmo padrão da outra pipeline do usuário: TUDO
roda dentro do MESMO job do GitHub Actions, com um loop de espera
bloqueante que consulta o Telegram a cada poucos segundos.

Isso evita depender de workflows agendados (`schedule`) do GitHub
Actions disparando no horário certo — o que não é garantido: o próprio
GitHub avisa que execuções agendadas podem atrasar ou ser puladas em
períodos de carga alta. Um loop dentro de um único job não tem esse
problema.

Fluxo:
1. send_for_approval() manda o vídeo do avatar e a thumbnail como duas
   mensagens separadas no Telegram, cada uma com seus próprios botões
   de Aprovar/Rejeitar.
2. wait_for_approval() entra num loop (até `timeout` segundos, padrão
   1h) consultando getUpdates a cada poucos segundos. Processa:
   - Aprovação/rejeição de cada item.
   - Ao REJEITAR um item, pede um substituto (responder com
     vídeo/imagem) e mostra um botão "Cancelar publicação".
   - Mídia enviada como substituto é baixada localmente (sem precisar
     re-hospedar em nenhum storage — tudo no mesmo job) e aprova esse
     item automaticamente.
   - Se nem tudo for decidido dentro do timeout, o workflow é
     CANCELADO (nada é publicado) — diferente da outra pipeline do
     usuário, que publica automaticamente após 1h; aqui, dado que o
     conteúdo é sensível (notícia/entrevista política), o padrão seguro
     é cancelar, não publicar sem revisão.
"""

import os
import time
import json
import requests


class TelegramApproval:
    def __init__(self):
        self.bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = os.environ["TELEGRAM_CHAT_ID"]
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.offset = self._obter_offset_inicial()

    def _obter_offset_inicial(self) -> int:
        """
        Pula qualquer update antigo (de testes anteriores, cliques não
        processados etc.) — só processa o que chegar A PARTIR de agora.
        """
        try:
            resp = requests.get(f"{self.base_url}/getUpdates", params={"offset": -1}, timeout=10)
            result = resp.json()
            if result.get("ok") and result.get("result"):
                return result["result"][-1]["update_id"] + 1
        except Exception:
            pass
        return 0

    # -- Envio -------------------------------------------------------------

    def send_message(self, text: str, reply_markup: dict | None = None) -> None:
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            requests.post(f"{self.base_url}/sendMessage", json=payload, timeout=15)
        except Exception as e:
            print(f"[telegram] Falha ao enviar mensagem: {e}")

    def send_video(self, path: str, caption: str, reply_markup: dict | None = None) -> None:
        data = {"chat_id": self.chat_id, "caption": caption, "parse_mode": "Markdown"}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        with open(path, "rb") as f:
            resp = requests.post(
                f"{self.base_url}/sendVideo", data=data, files={"video": f}, timeout=120
            )
        resp.raise_for_status()

    def send_photo(self, path: str, caption: str, reply_markup: dict | None = None) -> None:
        data = {"chat_id": self.chat_id, "caption": caption, "parse_mode": "Markdown"}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        with open(path, "rb") as f:
            resp = requests.post(
                f"{self.base_url}/sendPhoto", data=data, files={"photo": f}, timeout=60
            )
        resp.raise_for_status()

    def answer_callback(self, callback_id: str, text: str) -> None:
        try:
            requests.post(
                f"{self.base_url}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": text},
                timeout=10,
            )
        except Exception:
            pass

    def _download_telegram_file(self, file_id: str, output_path: str) -> str:
        resp = requests.get(f"{self.base_url}/getFile", params={"file_id": file_id}, timeout=15)
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]

        file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        file_resp = requests.get(file_url, timeout=120)
        file_resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(file_resp.content)
        return output_path

    def get_updates(self) -> list:
        try:
            resp = requests.get(
                f"{self.base_url}/getUpdates",
                params={"offset": self.offset, "timeout": 1},
                timeout=15,
            )
            result = resp.json()
            if not result.get("ok"):
                return []
            updates = result.get("result", [])
            if updates:
                self.offset = updates[-1]["update_id"] + 1
            return updates
        except Exception as e:
            print(f"[telegram] Falha ao buscar updates: {e}")
            return []


# ---------------------------------------------------------------------------
# Fluxo de aprovação
# ---------------------------------------------------------------------------

def send_for_approval(
    bot: TelegramApproval,
    video_id: str,
    script_text: str,
    avatar_video_path: str,
    thumbnail_path: str,
) -> None:
    video_caption = f"🎬 *Vídeo do avatar* (ID: `{video_id}`)\n\n*Roteiro:*\n{script_text}"
    video_markup = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar vídeo", "callback_data": f"approve_video:{video_id}"},
            {"text": "❌ Rejeitar vídeo", "callback_data": f"reject_video:{video_id}"},
        ]]
    }
    bot.send_video(avatar_video_path, video_caption, video_markup)

    thumb_caption = f"🖼️ *Thumbnail* (ID: `{video_id}`)"
    thumb_markup = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar thumbnail", "callback_data": f"approve_thumb:{video_id}"},
            {"text": "❌ Rejeitar thumbnail", "callback_data": f"reject_thumb:{video_id}"},
        ]]
    }
    bot.send_photo(thumbnail_path, thumb_caption, thumb_markup)


def wait_for_approval(
    bot: TelegramApproval,
    video_id: str,
    avatar_video_path: str,
    thumbnail_path: str,
    timeout: int = 3600,
) -> dict:
    """
    Loop bloqueante até timeout segundos. Retorna:
      {"decision": "approved", "video_path": ..., "thumbnail_path": ...}
      {"decision": "cancelled"}
      {"decision": "timeout"}
    """
    state = {
        "video_status": "waiting",
        "thumb_status": "waiting",
        "awaiting_replacement": None,  # None | "video" | "thumbnail"
        "video_override": None,
        "thumb_override": None,
    }

    start = time.time()
    print(f"⏳ Aguardando aprovação no Telegram (timeout: {timeout // 60} min)...")

    while time.time() - start < timeout:
        for update in bot.get_updates():
            callback = update.get("callback_query")
            if callback:
                data = callback.get("data", "")
                if ":" not in data:
                    continue
                action, cb_video_id = data.split(":", 1)
                if cb_video_id != video_id:
                    continue

                if action == "cancel":
                    bot.answer_callback(callback["id"], "Publicação cancelada.")
                    bot.send_message(f"🚫 Publicação cancelada (ID: `{video_id}`).")
                    return {"decision": "cancelled"}

                if action == "approve_video":
                    state["video_status"] = "approved"
                    bot.answer_callback(callback["id"], "Vídeo aprovado.")
                elif action == "reject_video":
                    state["video_status"] = "rejected"
                    state["awaiting_replacement"] = "video"
                    bot.answer_callback(callback["id"], "Vídeo rejeitado.")
                    bot.send_message(
                        f"❌ Vídeo rejeitado (ID: `{video_id}`).\n\n"
                        f"Envie um vídeo de substituição nesta conversa, ou "
                        f"clique abaixo para cancelar a publicação.",
                        reply_markup={"inline_keyboard": [[
                            {"text": "🚫 Cancelar publicação", "callback_data": f"cancel:{video_id}"}
                        ]]},
                    )
                elif action == "approve_thumb":
                    state["thumb_status"] = "approved"
                    bot.answer_callback(callback["id"], "Thumbnail aprovada.")
                elif action == "reject_thumb":
                    state["thumb_status"] = "rejected"
                    state["awaiting_replacement"] = "thumbnail"
                    bot.answer_callback(callback["id"], "Thumbnail rejeitada.")
                    bot.send_message(
                        f"❌ Thumbnail rejeitada (ID: `{video_id}`).\n\n"
                        f"Envie uma imagem de substituição nesta conversa, ou "
                        f"clique abaixo para cancelar a publicação.",
                        reply_markup={"inline_keyboard": [[
                            {"text": "🚫 Cancelar publicação", "callback_data": f"cancel:{video_id}"}
                        ]]},
                    )
                continue

            message = update.get("message")
            if not message or not state["awaiting_replacement"]:
                continue

            if state["awaiting_replacement"] == "video" and "video" in message:
                local_path = "avatar_override.mp4"
                bot._download_telegram_file(message["video"]["file_id"], local_path)
                state["video_override"] = local_path
                state["video_status"] = "approved"
                state["awaiting_replacement"] = None
                bot.send_message(f"✅ Vídeo de substituição recebido (ID: `{video_id}`).")

            elif state["awaiting_replacement"] == "thumbnail" and "photo" in message:
                local_path = "thumbnail_override.jpg"
                bot._download_telegram_file(message["photo"][-1]["file_id"], local_path)
                state["thumb_override"] = local_path
                state["thumb_status"] = "approved"
                state["awaiting_replacement"] = None
                bot.send_message(f"✅ Thumbnail de substituição recebida (ID: `{video_id}`).")

        if state["video_status"] == "approved" and state["thumb_status"] == "approved":
            return {
                "decision": "approved",
                "video_path": state["video_override"] or avatar_video_path,
                "thumbnail_path": state["thumb_override"] or thumbnail_path,
            }

        time.sleep(4)

    bot.send_message(
        f"⏰ Tempo esgotado aguardando aprovação (ID: `{video_id}`). "
        f"Publicação cancelada — nenhum vídeo foi ao ar."
    )
    return {
        "decision": "approved",
        "video_path": state["video_override"] or avatar_video_path,
        "thumbnail_path": state["thumb_override"] or thumbnail_path,
    }
