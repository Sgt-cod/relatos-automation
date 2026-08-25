"""
telegram_approval.py

Checkpoint humano do pipeline, com aprovação INDIVIDUAL de cada item
(vídeo do avatar / thumbnail), sem depender de webhook externo — usa
polling (getUpdates), do mesmo jeito que o resto das suas pipelines.

Fluxo:
1. send_for_approval() manda DUAS mensagens no Telegram: o vídeo do
   avatar (com botões Aprovar/Rejeitar) e a thumbnail (com seus próprios
   botões Aprovar/Rejeitar). Registra tudo em pending/{video_id}.json.

2. check_approvals(), chamado em polling a cada 5 min, processa:
   - Cliques de aprovação/rejeição em cada item.
   - Ao REJEITAR um item, o bot pede um substituto (responder a mensagem
     com um vídeo/imagem) e mostra um botão "Cancelar publicação".
   - Se o usuário responder com mídia enquanto um item está aguardando
     substituto, o arquivo é baixado do Telegram, subido como asset de
     release, e o item passa a "approved" automaticamente (usando o
     substituto).
   - Se o usuário clicar "Cancelar publicação", o vídeo inteiro é
     descartado (nada é publicado).
   - Quando AMBOS os itens (vídeo e thumbnail) estão "approved", o
     video_id entra na lista de aprovados retornada por check_approvals().
"""

import os
import json
import requests

from github_storage import upload_to_github_release, download_file

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
TELEGRAM_FILE_API = "https://api.telegram.org/file/bot{token}/{file_path}"
PENDING_DIR = "pending"
OFFSET_FILE = os.path.join(PENDING_DIR, ".telegram_offset")


# ---------------------------------------------------------------------------
# Envio inicial (Workflow A)
# ---------------------------------------------------------------------------

def send_for_approval(
    video_id: str,
    script_text: str,
    avatar_video_path: str,
    thumbnail_path: str,
    avatar_video_url: str,
    thumbnail_url: str,
    interview_url: str,
    source_title: str,
    source_channel: str,
) -> None:
    """
    Envia o vídeo do avatar e a thumbnail como duas mensagens separadas,
    cada uma com seus próprios botões de aprovação, e registra o estado
    pendente em pending/{video_id}.json.
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    # --- Mensagem 1: vídeo do avatar ---
    video_caption = (
        f"🎬 *Vídeo do avatar* (ID: `{video_id}`)\n\n"
        f"*Roteiro:*\n{script_text}"
    )
    video_markup = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar vídeo", "callback_data": f"approve_video:{video_id}"},
            {"text": "❌ Rejeitar vídeo", "callback_data": f"reject_video:{video_id}"},
        ]]
    }
    with open(avatar_video_path, "rb") as video_file:
        resp = requests.post(
            TELEGRAM_API.format(token=token, method="sendVideo"),
            data={
                "chat_id": chat_id,
                "caption": video_caption,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(video_markup),
            },
            files={"video": video_file},
            timeout=60,
        )
    resp.raise_for_status()

    # --- Mensagem 2: thumbnail ---
    thumb_caption = f"🖼️ *Thumbnail* (ID: `{video_id}`)"
    thumb_markup = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar thumbnail", "callback_data": f"approve_thumb:{video_id}"},
            {"text": "❌ Rejeitar thumbnail", "callback_data": f"reject_thumb:{video_id}"},
        ]]
    }
    with open(thumbnail_path, "rb") as photo_file:
        resp = requests.post(
            TELEGRAM_API.format(token=token, method="sendPhoto"),
            data={
                "chat_id": chat_id,
                "caption": thumb_caption,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(thumb_markup),
            },
            files={"photo": photo_file},
            timeout=60,
        )
    resp.raise_for_status()

    os.makedirs(PENDING_DIR, exist_ok=True)
    state = {
        "video_id": video_id,
        "script_text": script_text,
        "source_title": source_title,
        "source_channel": source_channel,
        "avatar_video_url": avatar_video_url,
        "thumbnail_url": thumbnail_url,
        "interview_url": interview_url,
        "video_status": "waiting",     # waiting | approved | rejected
        "thumb_status": "waiting",
        "video_override_url": None,
        "thumb_override_url": None,
        "awaiting_replacement": None,  # None | "video" | "thumbnail"
        "cancelled": False,
    }
    with open(os.path.join(PENDING_DIR, f"{video_id}.json"), "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Helpers de estado
# ---------------------------------------------------------------------------

def _load_pending(video_id: str) -> dict | None:
    path = os.path.join(PENDING_DIR, f"{video_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save_pending(video_id: str, state: dict) -> None:
    path = os.path.join(PENDING_DIR, f"{video_id}.json")
    with open(path, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _remove_pending(video_id: str) -> None:
    path = os.path.join(PENDING_DIR, f"{video_id}.json")
    if os.path.exists(path):
        os.remove(path)


def _load_offset() -> int:
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0


def _save_offset(offset: int) -> None:
    os.makedirs(PENDING_DIR, exist_ok=True)
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)


def _find_awaiting_video_id() -> str | None:
    """Acha (se houver) um video_id com algum item aguardando substituto."""
    if not os.path.isdir(PENDING_DIR):
        return None
    for fname in os.listdir(PENDING_DIR):
        if not fname.endswith(".json") or fname.startswith("."):
            continue
        video_id = fname[: -len(".json")]
        state = _load_pending(video_id)
        if state and state.get("awaiting_replacement"):
            return video_id
    return None


# ---------------------------------------------------------------------------
# Ações do bot
# ---------------------------------------------------------------------------

def _send_message(token: str, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(TELEGRAM_API.format(token=token, method="sendMessage"), json=payload, timeout=15)


def _prompt_for_replacement(token: str, chat_id: str, video_id: str, item_label: str) -> None:
    cancel_markup = {
        "inline_keyboard": [[
            {"text": "🚫 Cancelar publicação", "callback_data": f"cancel:{video_id}"},
        ]]
    }
    _send_message(
        token, chat_id,
        f"❌ {item_label} rejeitado(a) (ID: `{video_id}`).\n\n"
        f"Envie um arquivo de substituição nesta conversa (vídeo ou imagem, "
        f"conforme o item), ou clique abaixo para cancelar a publicação.",
        reply_markup=cancel_markup,
    )


def _download_telegram_file(token: str, file_id: str, output_path: str) -> str:
    resp = requests.get(
        TELEGRAM_API.format(token=token, method="getFile"),
        params={"file_id": file_id},
        timeout=15,
    )
    resp.raise_for_status()
    file_path = resp.json()["result"]["file_path"]

    file_url = TELEGRAM_FILE_API.format(token=token, file_path=file_path)
    return download_file(file_url, output_path)


# ---------------------------------------------------------------------------
# Checagem principal (Workflow B, em polling)
# ---------------------------------------------------------------------------

def check_approvals() -> list:
    """
    Consulta o Telegram por atualizações novas, processa cliques de botão
    e mensagens de substituição, e retorna as decisões finais:

        [{"video_id": "...", "approved": True}, ...]   # ambos itens ok
        [{"video_id": "...", "approved": False}, ...]  # cancelado
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    offset = _load_offset()

    resp = requests.get(
        TELEGRAM_API.format(token=token, method="getUpdates"),
        params={"offset": offset, "timeout": 0},
        timeout=30,
    )
    resp.raise_for_status()
    updates = resp.json().get("result", [])

    decisions = []
    max_update_id = offset - 1

    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])

        # --- Cliques de botão ---
        callback = update.get("callback_query")
        if callback:
            data = callback.get("data", "")
            if ":" not in data:
                continue
            action, video_id = data.split(":", 1)
            state = _load_pending(video_id)

            if state is None:
                continue  # já processado / desconhecido

            if action == "cancel":
                _remove_pending(video_id)
                decisions.append({"video_id": video_id, "approved": False})
                requests.post(
                    TELEGRAM_API.format(token=token, method="answerCallbackQuery"),
                    json={"callback_query_id": callback["id"], "text": "Publicação cancelada."},
                    timeout=15,
                )
                _send_message(token, chat_id, f"🚫 Publicação cancelada (ID: `{video_id}`).")
                continue

            if action == "approve_video":
                state["video_status"] = "approved"
                ack_text = "Vídeo aprovado."
            elif action == "reject_video":
                state["video_status"] = "rejected"
                state["awaiting_replacement"] = "video"
                ack_text = "Vídeo rejeitado."
            elif action == "approve_thumb":
                state["thumb_status"] = "approved"
                ack_text = "Thumbnail aprovada."
            elif action == "reject_thumb":
                state["thumb_status"] = "rejected"
                state["awaiting_replacement"] = "thumbnail"
                ack_text = "Thumbnail rejeitada."
            else:
                continue

            requests.post(
                TELEGRAM_API.format(token=token, method="answerCallbackQuery"),
                json={"callback_query_id": callback["id"], "text": ack_text},
                timeout=15,
            )

            if state.get("awaiting_replacement"):
                item_label = "Vídeo" if state["awaiting_replacement"] == "video" else "Thumbnail"
                _prompt_for_replacement(token, chat_id, video_id, item_label)

            _save_pending(video_id, state)

            if state["video_status"] == "approved" and state["thumb_status"] == "approved":
                decisions.append({"video_id": video_id, "approved": True})

            continue

        # --- Mensagens com mídia (possível substituto) ---
        message = update.get("message")
        if not message:
            continue

        video_id = _find_awaiting_video_id()
        if not video_id:
            continue  # nenhum item aguardando substituto no momento

        state = _load_pending(video_id)
        if not state:
            continue

        awaiting = state.get("awaiting_replacement")

        if awaiting == "video" and "video" in message:
            file_id = message["video"]["file_id"]
            local_path = f"/tmp/{video_id}_video_override.mp4"
            _download_telegram_file(token, file_id, local_path)
            override_url = upload_to_github_release(local_path, f"{video_id}_avatar_override.mp4")

            state["video_override_url"] = override_url
            state["video_status"] = "approved"
            state["awaiting_replacement"] = None
            _save_pending(video_id, state)
            _send_message(token, chat_id, f"✅ Vídeo de substituição recebido (ID: `{video_id}`).")

        elif awaiting == "thumbnail" and "photo" in message:
            # Telegram manda várias resoluções da mesma foto; pega a maior.
            file_id = message["photo"][-1]["file_id"]
            local_path = f"/tmp/{video_id}_thumb_override.jpg"
            _download_telegram_file(token, file_id, local_path)
            override_url = upload_to_github_release(local_path, f"{video_id}_thumbnail_override.jpg")

            state["thumb_override_url"] = override_url
            state["thumb_status"] = "approved"
            state["awaiting_replacement"] = None
            _save_pending(video_id, state)
            _send_message(token, chat_id, f"✅ Thumbnail de substituição recebida (ID: `{video_id}`).")

        else:
            continue  # mídia não bate com o tipo esperado no momento

        if state["video_status"] == "approved" and state["thumb_status"] == "approved":
            decisions.append({"video_id": video_id, "approved": True})

    _save_offset(max_update_id + 1)
    return decisions


if __name__ == "__main__":
    print(check_approvals())
