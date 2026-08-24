"""
pipeline_config.py

Configuração compartilhada entre find_and_download.py e generate_script.py.
"""

# Preencha com os Channel IDs reais (não é o @handle nem o nome do canal).
# Como pegar o Channel ID: abra o canal no YouTube > clique nos 3 pontos
# ou veja o código-fonte da página / use a API channels.list com
# forHandle=@nomedocanal e leia o campo "id" da resposta.
CHANNELS = {
    "CNN Brasil": "UCvdwhh_fDyWccR42-rReZLw",
    "G1": "UCaGmdJSSiR7fkh2A-c6emsA",
    "Estadão": "CHANNEL_ID_AQUI",  # pegue pelo navegador — ver GUIA_APIS.md
    "Folha de S.Paulo": "CHANNEL_ID_AQUI",  # pegue pelo navegador — ver GUIA_APIS.md
    "Metrópoles": "CHANNEL_ID_AQUI",  # pegue pelo navegador — ver GUIA_APIS.md
}

SEARCH_KEYWORDS = ["entrevista"]

# Só considera vídeos publicados nos últimos N dias, para não pegar
# entrevistas antigas repetidamente.
MAX_VIDEO_AGE_DAYS = 3

# Duração mínima/máxima do vídeo original para considerar como candidato
# (evita cortes/shorts que já vêm curtos demais, e lives de horas).
MIN_SOURCE_DURATION_SEC = 4 * 60
MAX_SOURCE_DURATION_SEC = 60 * 60

# Duração alvo do corte final
CLIP_DURATION_SEC = 6.5 * 60

STATE_DIR = "state"
PROCESSED_VIDEOS_FILE = f"{STATE_DIR}/processed_videos.json"
