"""
pipeline_config.py

Configuração compartilhada entre find_and_download.py,
find_intervention_moments.py e outros módulos.
"""

# Preencha com os Channel IDs reais (não é o @handle nem o nome do canal).
# Como pegar o Channel ID: abra o canal no YouTube > clique nos 3 pontos
# ou veja o código-fonte da página / use a API channels.list com
# forHandle=@nomedocanal e leia o campo "id" da resposta.
# Não precisa ficar limitado a veículos de notícia — canais oficiais de
# políticos, do Congresso, de partidos, de podcasts políticos etc. também
# servem, já que a busca agora cobre conteúdo político em geral, não só
# entrevistas de imprensa.
CHANNELS = {
    "CNN Brasil": "UCvdwhh_fDyWccR42-rReZLw",
    "G1": "UCaGmdJSSiR7fkh2A-c6emsA",
    "Estadão": "CHANNEL_ID_AQUI",  # pegue pelo navegador — ver GUIA_APIS.md
    "Folha de S.Paulo": "CHANNEL_ID_AQUI",  # pegue pelo navegador — ver GUIA_APIS.md
    "Metrópoles": "CHANNEL_ID_AQUI",  # pegue pelo navegador — ver GUIA_APIS.md
}

# Ampliado de só "entrevista" para cobrir conteúdo político em geral —
# discursos, debates, coletivas, sessões legislativas etc. A busca tenta
# cada palavra-chave por canal, então quanto mais termos, mais chance de
# achar algo novo, mas também mais chamadas à API (a cota diária do
# YouTube Data API ainda é confortável para esse volume).
SEARCH_KEYWORDS = [
    "entrevista",
    "discurso",
    "debate",
    "coletiva de imprensa",
    "pronunciamento",
    "sessão do congresso",
]

# Só considera vídeos publicados nos últimos N dias, para não pegar
# conteúdo repetido em execuções sucessivas.
MAX_VIDEO_AGE_DAYS = 3

# Duração mínima/máxima do vídeo ORIGINAL para considerar como candidato
# (evita cortes/shorts curtos demais, e sessões de horas que estourariam
# o tempo de transcrição em CPU dentro do job do GitHub Actions).
MIN_SOURCE_DURATION_SEC = 4 * 60
MAX_SOURCE_DURATION_SEC = 60 * 60

# Duração alvo do trecho de destaque cortado do vídeo original — agora é
# uma janela mais longa que antes, já que várias intervenções do
# personagem acontecem ao longo dela, não só uma introdução.
HIGHLIGHT_DURATION_SEC = 12 * 60

# Quantas intervenções CRÍTICAS (no meio do vídeo, em PiP) por vídeo
# publicado — não conta abertura nem despedida, que são sempre 1 cada,
# em tela cheia.
N_MID_INTERVENTIONS = 3

# Taxa de quadros (fps) fixa aplicada a TODOS os trechos de vídeo antes de
# concatenar. Os vídeos-fonte (assets/presenter*.mp4 e o vídeo baixado do
# YouTube) quase sempre têm fps nativos diferentes entre si — e como a
# concatenação final usa "-c copy" (sem reencodar), um descompasso de fps
# entre os trechos causa o vídeo tocar em câmera lenta/rápida em alguns
# pedaços (o áudio, por ter timeline própria, toca normal — daí o
# descompasso). Forçar todo mundo pro mesmo fps antes de concatenar evita
# isso.
TARGET_FPS = 30

STATE_DIR = "state"
PROCESSED_VIDEOS_FILE = f"{STATE_DIR}/processed_videos.json"
