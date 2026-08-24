"""
check_approvals_step.py

Passo de wiring chamado pelo check_approval.yml. Roda telegram_approval.
check_approvals(), e se algum vídeo foi aprovado nessa checagem, expõe
essa informação para os próximos passos do workflow via
GITHUB_OUTPUT (has_approved=true/false) e grava qual video_id foi
aprovado, para publish_youtube.py usar.

Pressupõe que os arquivos finais de cada vídeo pendente (final_video.mp4,
thumbnail.jpg, título, descrição) foram salvos em
pending/{video_id}/ pelo workflow de geração — ajuste os caminhos no
generate.yml/generate_script.py se preferir outra convenção de pastas.
"""

import os
from telegram_approval import check_approvals


def main():
    decisions = check_approvals()
    approved = [d for d in decisions if d["approved"]]

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_approved={'true' if approved else 'false'}\n")

    if approved:
        # Publica só o primeiro aprovado nessa execução; se houver mais de
        # um, os demais serão pegos na próxima checagem (5 min depois).
        video_id = approved[0]["video_id"]
        with open("approved_video_id.txt", "w") as f:
            f.write(video_id)
        print(f"Aprovado para publicação: {video_id}")
    else:
        print("Nenhuma aprovação nova nessa checagem.")


if __name__ == "__main__":
    main()
