"""
telegram_approval.py

Checkpoint humano do pipeline, SEM depender de webhook externo (Cloudflare,
Vercel, etc.). Usa o modelo de polling do próprio Telegram (getUpdates),
que é pull-based — encaixa com o resto das suas pipelines, que também
funcionam por polling/cron.

Duas responsabilidades neste arquivo:

1. send_for_approval()  -> chamado pelo workflow "generate.yml" depois de
   montar o vídeo. Envia a thumbnail + roteiro no Telegram com botões
   inline de Aprovar/Rejeitar, e registra o vídeo como "pendente".

2. check_approvals()    -> chamado pelo workflow "check_approval.yml",
   que roda em cron curto (ex.: a cada 5 min). Consulta o Telegram por
   respostas novas via getUpdates, cruza com os vídeos pendentes, e
   devolve a lista do que foi aprovado/rejeitado nessa checagem.

Estado entre execuções (que vídeos estão pendentes, qual foi o último
update_id processado no Telegram) fica salvo como arquivos JSON dentro do
próprio repositório, em `pending/`. O workflow B lê esse estado, publica o
que foi aprovado, remove pendências resolvidas e faz commit de volta —
sem precisar de banco de dados ou serviço externo.
"""

import os
import json
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
PENDING_DIR = "pending"
OFFSET_FILE = os.path.join(PENDING_DIR, ".telegram_offset")


def send_for_approval(script_text: str, thumbnail_path: str, video_id: str) -> None:
    """
    Envia o roteiro + thumbnail para o Telegram com botões inline, e
    registra o vídeo em pending/{video_id}.json como aguardando resposta.
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    caption = (
        f"🎬 *Novo vídeo pronto para revisão*\n\n"
        f"*Roteiro do avatar:*\n{script_text}\n\n"
        f"ID: `{video_id}`"
    )
    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar e publicar", "callback_data": f"approve:{video_id}"},
            {"text": "❌ Rejeitar", "callback_data": f"reject:{video_id}"},
        ]]
    }

    with open(thumbnail_path, "rb") as photo:
        resp = requests.post(
            TELEGRAM_API.format(token=token, method="sendPhoto"),
            data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(reply_markup),
            },
            files={"photo": photo},
            timeout=30,
        )
    resp.raise_for_status()

    os.makedirs(PENDING_DIR, exist_ok=True)
    with open(os.path.join(PENDING_DIR, f"{video_id}.json"), "w") as f:
        json.dump({"video_id": video_id, "status": "waiting"}, f)


def _load_offset() -> int:
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0


def _save_offset(offset: int) -> None:
    os.makedirs(PENDING_DIR, exist_ok=True)
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)


def check_approvals() -> list:
    """
    Consulta o Telegram por atualizações novas desde a última checagem
    (via offset salvo em pending/.telegram_offset), processa cliques de
    botão (callback_query) e retorna uma lista de decisões:

        [{"video_id": "...", "approved": True}, ...]

    Também responde ao Telegram (answerCallbackQuery) para tirar o
    "carregando" do botão, e avança o offset para não reprocessar a
    mesma resposta na próxima execução.
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
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

        callback = update.get("callback_query")
        if not callback:
            continue

        data = callback.get("data", "")
        if ":" not in data:
            continue

        action, video_id = data.split(":", 1)
        pending_path = os.path.join(PENDING_DIR, f"{video_id}.json")
        if not os.path.exists(pending_path):
            continue  # já processado antes, ou vídeo desconhecido

        approved = action == "approve"
        decisions.append({"video_id": video_id, "approved": approved})

        # Remove o pendente (resolvido, seja aprovado ou rejeitado)
        os.remove(pending_path)

        # Confirma ao Telegram que o clique foi processado
        requests.post(
            TELEGRAM_API.format(token=token, method="answerCallbackQuery"),
            json={
                "callback_query_id": callback["id"],
                "text": "Publicando..." if approved else "Descartado.",
            },
            timeout=15,
        )

    _save_offset(max_update_id + 1)
    return decisions


if __name__ == "__main__":
    # Teste manual: roda uma checagem e imprime o que encontrou
    print(check_approvals())
