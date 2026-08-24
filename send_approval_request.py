"""
send_approval_request.py

Passo de wiring chamado pelo generate.yml (passo 7): lê o roteiro gerado
e chama telegram_approval.send_for_approval().
"""

from telegram_approval import send_for_approval

if __name__ == "__main__":
    with open("script.txt") as f:
        script_text = f.read().strip()

    with open("video_id.txt") as f:
        video_id = f.read().strip()

    send_for_approval(
        script_text=script_text,
        thumbnail_path="thumbnail.jpg",
        video_id=video_id,
    )
    print(f"Pedido de aprovação enviado para o vídeo {video_id}.")
