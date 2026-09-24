"""
find_intervention_moments.py

Passo 2 do generate.yml: monta o roteiro completo do personagem
mascarado pra este vídeo, em três partes:

1. ABERTURA (tela cheia, antes de tudo): cumprimento + breve contexto do
   que vem a seguir ("hoje vamos acompanhar..."), variando o tom a cada
   vídeo.
2. INTERVENÇÕES CRÍTICAS (N_MID_INTERVENTIONS, padrão 3): dentro da
   janela de destaque já cortada, o Gemini escolhe momentos específicos,
   bem espaçados, onde a intervenção do personagem encaixaria bem — e
   escreve um mini-roteiro irônico/crítico pra cada um. Essas aparecem
   em PiP sobre o vídeo de base, congelado naquele instante.
3. DESPEDIDA (tela cheia, depois de tudo): fechamento mantendo o tom
   cético/anti-sistema, sem necessariamente amarrar num evento específico.

O personagem: comentarista anônimo, mascarado, tom irônico/debochado,
"anti-sistema" — crítico de qualquer poder estabelecido, sem favorecer
esquerda nem direita. As salvaguardas de conteúdo (só usar o que está na
transcrição, não fabricar falas, não atacar caráter pessoal) valem pra
TODAS as falas, inclusive abertura/despedida.

Saída: interventions.json —
    {
      "opening": {"script_text": str},
      "mid": [{"timestamp_sec": float, "topic": str, "script_text": str}, ...],
      "closing": {"script_text": str}
    }
"""

import os
import json

from gemini_client import call_gemini
from pipeline_config import N_MID_INTERVENTIONS

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

PERSONA_INSTRUCTIONS = (
    "Você escreve falas curtas, magnéticas e incisivas para um personagem de direita, "
    "comentarista político e analista de oposição ao atual governo de esquerda. "
    "Sua persona é a de um crítico ferrenho da hipocrisia institucional, da seletividade "
    "moral e da corrupção estrutural enraizada na esquerda.\n\n"
    
    "Diretrizes de Conteúdo e Visão Crítica:\n"
    "- Foque na exposição implacável do 'duplo padrão' e da régua moral elástica: cobram "
    "de adversários o que normalizam, acobertam ou justificam quando praticado por aliados.\n"
    "- Aponte sem meias-palavras a cumplicidade da grande mídia, dos aparelhos ideológicos "
    "e da militância adaptada ao poder.\n"
    "- Use analogias ácidas para contrastar o discurso salvacionista da esquerda com a realidade "
    "econômica, fiscal e moral da gestão atual.\n\n"
    
    "Vocabulário-Chave Obrigatório (use com naturalidade no contexto):\n"
    "- Termos recorrentes: 'esquerdista', 'narrativa', 'passador de pano', 'duplo padrão', "
    "'aparelhamento', 'seletividade', 'moralismo de palanque', 'tratoraço', 'gastança'.\n\n"
    
    "Regras Estritas de Estilo:\n"
    "- Frases curtas, cortantes e de alto impacto, ideais para cortes rápidos, Reels, TikTok ou YouTube Shorts.\n"
    "- Evite divagações acadêmicas; vá direto ao ponto com contundência e ironia refinada.\n"
    "- Nunca faça concessões vazias ao governo; a crítica deve ser frontal, inteligente e bem fundamentada nos fatos do debate público.\n\n"
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
        + "\n- Formato: 2 a 3 frases, ritmo rápido e cortante, ~10-15 "
          "segundos falados.\n"
        + f"\nMomento específico sendo comentado: {topic}\n\n"
        + f"Trecho da transcrição nesse momento:\n{transcript_excerpt}\n\n"
        + "Responda apenas com a fala do personagem, sem aspas, sem markdown."
    )
    return call_gemini(prompt, GEMINI_API_KEY).strip()


def write_opening_script(source_meta: dict) -> str:
    prompt = (
        PERSONA_INSTRUCTIONS
        + "\nEssa é a ABERTURA do vídeo, em tela cheia, antes de qualquer "
          "outro conteúdo aparecer. Precisa ter duas partes:\n"
          "1. Um cumprimento característico do personagem — VARIE o "
          "cumprimento a cada vídeo, não repita sempre a mesma frase. "
          "Exemplos de TOM (não copie literalmente sempre): 'Olá, "
          "compatriotas', 'Olá, habitantes dessa terra esquisita'.\n"
          "2. Uma frase curta contextualizando o que vem a seguir, citando "
          "naturalmente do que se trata o conteúdo (ex.: uma entrevista, "
          "um discurso, um trecho de podcast, uma coletiva) e quem "
          "aparece — baseado nas informações abaixo.\n"
          "- Formato: 2 a 3 frases no total, ~10-15 segundos falados.\n\n"
        + f"Veículo/fonte: {source_meta['channel']}\n"
        + f"Título original do conteúdo: {source_meta['title']}\n\n"
        + "Responda apenas com a fala do personagem, sem aspas, sem markdown."
    )
    return call_gemini(prompt, GEMINI_API_KEY).strip()


def write_closing_script(topics: list) -> str:
    topics_text = "; ".join(topics)
    prompt = (
        PERSONA_INSTRUCTIONS
        + "\nEssa é a DESPEDIDA do vídeo, em tela cheia, depois de todo o "
          "conteúdo. Deve fechar mantendo o tom assertivo e indignado em "
          "relação às políticas de utópicas e hipócritas de esquerda — não precisa "
          "necessariamente amarrar em um evento específico, mas pode "
          "referenciar de leve os temas abordados se fizer sentido.\n"
          "- Formato: 2 a 3 frases, ~10-15 segundos falados.\n\n"
        + f"Temas abordados no vídeo: {topics_text}\n\n"
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

    print("Escolhendo momentos de intervenção...")
    moments = find_intervention_timestamps(transcript_text, N_MID_INTERVENTIONS)

    mid_interventions = []
    for m in moments:
        excerpt = get_excerpt_near(transcript, m["timestamp_sec"])
        script_text = write_intervention_script(m["topic"], excerpt)
        mid_interventions.append({
            "timestamp_sec": m["timestamp_sec"],
            "topic": m["topic"],
            "script_text": script_text,
        })
    mid_interventions.sort(key=lambda x: x["timestamp_sec"])  # ordem cronológica

    print("Escrevendo abertura...")
    opening_script = write_opening_script(source_meta)

    print("Escrevendo despedida...")
    closing_script = write_closing_script([it["topic"] for it in mid_interventions])

    result = {
        "opening": {"script_text": opening_script},
        "mid": mid_interventions,
        "closing": {"script_text": closing_script},
    }

    with open("interventions.json", "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nAbertura:\n  \"{opening_script}\"\n")
    print(f"{len(mid_interventions)} intervenções críticas planejadas:")
    for i, it in enumerate(mid_interventions):
        print(f"  {i + 1}. [{it['timestamp_sec']:.0f}s] {it['topic']}\n     \"{it['script_text']}\"")
    print(f"\nDespedida:\n  \"{closing_script}\"")


if __name__ == "__main__":
    main()
