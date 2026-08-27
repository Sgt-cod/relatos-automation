"""
find_intervention_moments.py

Passo 2 do generate.yml: dentro da janela de destaque já cortada
(highlight_cut.mp4), pede pro Gemini escolher N_INTERVENTIONS momentos
específicos, bem espaçados, onde a intervenção do personagem mascarado
encaixaria bem — e escreve um mini-roteiro curto para cada um.

O personagem: comentarista anônimo, mascarado, tom irônico/debochado,
"anti-sistema" — crítico de qualquer poder estabelecido, sem favorecer
esquerda nem direita. As salvaguardas de conteúdo (só usar o que está na
transcrição, não fabricar falas, não atacar caráter pessoal) seguem o
mesmo princípio das que já usamos no roteiro de introdução — aqui reforçadas
porque agora são vários trechos por vídeo, com tom mais afiado, sobre
pessoas e eventos reais.

Saída: interventions.json — lista de
    {"timestamp_sec": float (relativo ao VÍDEO ORIGINAL, mesma base do
     transcript.json), "topic": str, "script_text": str}
ordenada cronologicamente.
"""

import os
import json

from gemini_client import call_gemini
from pipeline_config import N_INTERVENTIONS

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

PERSONA_INSTRUCTIONS = (
    "Você escreve falas curtas para um personagem mascarado, anônimo, "
    "com persona de comentarista revolucionário/anti-sistema — irônico, "
    "debochado, cético em relação a qualquer poder estabelecido. Ele "
    "critica tanto a esquerda quanto a direita igualmente — o alvo dele "
    "é o sistema político como um todo e suas contradições, não um "
    "partido ou pessoa específica.\n\n"
    "Regras obrigatórias:\n"
    "- A fala deve soar claramente como sátira/opinião — não como uma "
    "afirmação factual disfarçada de notícia.\n"
    "- Baseie a piada/crítica em algo que ESTÁ na transcrição abaixo — "
    "não invente declarações, dados ou eventos que não estejam nela.\n"
    "- Pode ser afiado e engraçado, mas não pode ser difamatório: não "
    "acuse ninguém de crime ou má-fé além do que já é fato de "
    "conhecimento público refletido na própria transcrição.\n"
    "- Ataque o discurso, as ideias, as contradições — nunca "
    "características pessoais (aparência, família, vida privada).\n"
    "- Não use rótulos político-ideológicos genéricos como arma (ex.: "
    "não chame ninguém de 'comunista' ou 'fascista' como ofensa vazia) — "
    "a crítica tem que vir de algo concreto dito na transcrição.\n"
    "- 2 a 3 frases, ritmo rápido e cortante, ~10-15 segundos falados.\n"
)


def find_intervention_timestamps(transcript_excerpt_with_times: str, n: int) -> list:
    """Pede pro Gemini N momentos bem espaçados dentro da janela de destaque."""
    prompt = (
        f"Você vai analisar a transcrição de um trecho de vídeo político, "
        f"com marcações de tempo em segundos. Escolha {n} momentos "
        f"DIFERENTES e bem espaçados ao longo do trecho onde um "
        f"comentário irônico/crítico encaixaria bem logo em seguida — "
        f"momentos com uma afirmação marcante, uma contradição, um "
        f"clichê de discurso político, uma promessa vaga, ou um dado "
        f"citado que renderia boa ironia.\n\n"
        f"Responda APENAS em JSON, uma lista no formato exato:\n"
        f'[{{"timestamp_sec": <número>, "topic": "<do que se trata, 1 frase>"}}, ...]\n\n'
        f"Transcrição:\n{transcript_excerpt_with_times}"
    )
    resp_text = call_gemini(prompt, GEMINI_API_KEY)
    cleaned = resp_text.strip().strip("`").replace("json\n", "", 1)
    return json.loads(cleaned)


def write_intervention_script(topic: str, transcript_excerpt: str) -> str:
    prompt = (
        PERSONA_INSTRUCTIONS
        + f"\nMomento específico sendo comentado: {topic}\n\n"
        + f"Trecho da transcrição nesse momento:\n{transcript_excerpt}\n\n"
        + "Responda apenas com a fala do personagem, sem aspas, sem markdown."
    )
    return call_gemini(prompt, GEMINI_API_KEY).strip()


def get_excerpt_near(transcript: list, timestamp_sec: float, window_sec: float = 25) -> str:
    segs = [
        s for s in transcript
        if timestamp_sec - window_sec <= s["start"] <= timestamp_sec + window_sec
    ]
    return "\n".join(s["text"] for s in segs)


def main():
    with open("transcript.json") as f:
        transcript = json.load(f)
    with open("source_meta.json") as f:
        source_meta = json.load(f)

    window = source_meta["highlight_window"]
    windowed_transcript = [
        s for s in transcript if window["start_sec"] <= s["start"] <= window["end_sec"]
    ]
    transcript_text = "\n".join(
        f"[{s['start']:.0f}s] {s['text']}" for s in windowed_transcript
    )

    moments = find_intervention_timestamps(transcript_text, N_INTERVENTIONS)

    interventions = []
    for m in moments:
        excerpt = get_excerpt_near(transcript, m["timestamp_sec"])
        script_text = write_intervention_script(m["topic"], excerpt)
        interventions.append({
            "timestamp_sec": m["timestamp_sec"],
            "topic": m["topic"],
            "script_text": script_text,
        })

    interventions.sort(key=lambda x: x["timestamp_sec"])  # ordem cronológica

    with open("interventions.json", "w") as f:
        json.dump(interventions, f, ensure_ascii=False, indent=2)

    print(f"{len(interventions)} intervenções planejadas:")
    for i, it in enumerate(interventions):
        print(f"  {i + 1}. [{it['timestamp_sec']:.0f}s] {it['topic']}\n     \"{it['script_text']}\"")


if __name__ == "__main__":
    main()
