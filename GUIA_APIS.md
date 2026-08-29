# Miniguia: obtendo YOUTUBE_API_KEY, GEMINI_API_KEY e MODAL_ENDPOINT_URL

---

## 1. YOUTUBE_API_KEY

Usada por `find_and_download.py` para buscar vídeos via YouTube Data API v3.

1. Acesse o **Google Cloud Console**: https://console.cloud.google.com/
2. No topo, crie um projeto novo (ou use um existente) — ex.: "pipeline-youtube".
3. No menu lateral, vá em **APIs e Serviços > Biblioteca**.
4. Busque por **"YouTube Data API v3"** e clique em **Ativar**.
5. Vá em **APIs e Serviços > Credenciais**.
6. Clique em **+ Criar Credenciais > Chave de API**.
7. Copie a chave gerada (formato `AIza...`).
8. **Restrinja a chave** (recomendado, evita uso indevido se vazar):
   - Clique na chave criada > em "Restrições de API", selecione **Restringir chave** e marque só "YouTube Data API v3".
9. Salve essa chave como `YOUTUBE_API_KEY` nos **Secrets do GitHub** (ver seção final).

**Gratuidade**: a API tem cota diária gratuita de 10.000 "unidades" (uma busca simples custa ~100 unidades), o que dá margem confortável para o volume da sua pipeline. Não precisa de cartão de crédito para esse uso.

---

## 2. GEMINI_API_KEY

Usada por `find_and_download.py` (identificar trecho de tensão) e `generate_script.py` (escrever o roteiro do avatar).

1. Acesse o **Google AI Studio**: https://aistudio.google.com/
2. Faça login com sua conta Google.
3. No menu lateral, clique em **Get API key**.
4. Clique em **Create API key** (a AI Studio associa a chave a um projeto do Google Cloud automaticamente — pode deixar ela criar um projeto novo).
5. Copie a chave gerada.
6. Salve como `GEMINI_API_KEY` nos Secrets do GitHub.

**Ponto de atenção (2026)**: o Google está migrando de "chaves padrão" para "chaves de autenticação" (*auth keys*) — chaves criadas hoje na AI Studio já nascem no formato novo automaticamente, então não deve exigir ação extra da sua parte. Só fique atento se em algum momento a chave for rejeitada com erro relacionado a "standard key deprecated": nesse caso, basta gerar uma nova pela mesma tela.

**Gratuidade**: existe tier gratuito (algo em torno de 10 requisições/minuto e algumas centenas de requisições/dia para o modelo Flash, variável por conta — o valor exato aparece no seu painel em `aistudio.google.com/rate-limit`). Para o volume da sua pipeline (poucas chamadas por vídeo gerado), deve caber tranquilamente sem precisar habilitar billing.

---

## 3. MODAL_ENDPOINT_URL

Diferente das outras duas, essa não é uma "chave" que você copia de um painel — é a **URL gerada quando você publica** a função `modal_avatar.py`. Normalmente isso se faz via terminal (`modal deploy`), mas como você trabalha 100% pelo navegador, dá pra fazer o GitHub Actions rodar esse deploy por você. Já deixei o workflow pronto (`deploy_modal.yml`).

### Passo a passo (tudo pelo navegador)

**1. Criar a conta e pegar um token de API da Modal**
1. Acesse https://modal.com/ e crie uma conta (login com GitHub ou Google — sem precisar instalar nada).
2. No painel da Modal, vá em **Settings > API Tokens** (ou acesse diretamente https://modal.com/settings/tokens).
3. Clique em **New Token** (ou "Create new token").
4. A Modal vai mostrar um **Token ID** e um **Token Secret** — copie os dois (o secret só aparece uma vez).

**2. Salvar o token como Secrets no GitHub**
1. No seu repositório, vá em **Settings > Secrets and variables > Actions**.
2. Clique em **New repository secret** e crie:
   - `MODAL_TOKEN_ID` — cole o Token ID.
   - `MODAL_TOKEN_SECRET` — cole o Token Secret.

**3. Subir o arquivo `modal_avatar.py` e o workflow `deploy_modal.yml`**
- Se ainda não fez isso, suba os dois arquivos pro repositório pela interface web do GitHub (botão **Add file > Upload files**, ou criando/colando o conteúdo direto na tela de edição). O `deploy_modal.yml` precisa ficar exatamente em `.github/workflows/deploy_modal.yml`.

**4. Rodar o deploy**
1. No repositório, vá na aba **Actions**.
2. Na lista à esquerda, clique em **Deploy Modal (avatar lipsync)**.
3. Clique no botão **Run workflow** (canto direito) > **Run workflow** de novo para confirmar.
4. Aguarde a execução terminar (ícone verde ✓).

**5. Pegar a URL gerada**
1. Clique na execução que acabou de rodar.
2. Abra o step **"Mostrar a URL do endpoint"** — ele imprime a URL no formato:
   ```
   https://SEU-WORKSPACE--avatar-lipsync-generate-endpoint.modal.run
   ```
3. Copie essa URL.

**6. Salvar como Secret final**
1. Volte em **Settings > Secrets and variables > Actions > New repository secret**.
2. Crie `MODAL_ENDPOINT_URL` com a URL copiada.

### Importante
- Esse deploy só precisa ser feito **uma vez** — a URL fica fixa e permanente. Só rode de novo se editar `modal_avatar.py` (o workflow já está configurado para rodar automaticamente nesse caso, então nem precisa clicar o botão de novo).
- Por padrão, o endpoint fica **público** (qualquer um com a URL pode chamar). Para uso pessoal isso é aceitável, mas a Modal também suporta *Proxy Auth Tokens* para travar o acesso — posso te mostrar como configurar isso se preferir mais segurança.

---

## Onde colocar as chaves no fim das contas

Todas vão nos **Secrets do repositório no GitHub** (não no código, nunca):

1. No seu repositório, vá em **Settings > Secrets and variables > Actions**.
2. Clique em **New repository secret**.
3. Crie um secret para cada uma:
   - `YOUTUBE_API_KEY`
   - `GEMINI_API_KEY`
   - `MODAL_ENDPOINT_URL`
   - `FISH_AUDIO_API_KEY` e `FISH_AUDIO_VOICE_ID`
   - `AGNES_API_KEY`
   - `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`
   - `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` (veja seção 4 abaixo)

Os workflows já estão escritos para ler esses secrets automaticamente via `${{ secrets.NOME_DO_SECRET }}`.

---

## 4. YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET e YOUTUBE_REFRESH_TOKEN

Essas três autorizam `publish_youtube.py` a publicar vídeos na sua conta. É o processo mais longo dos quatro, mas dá pra fazer 100% pelo navegador usando o **Google OAuth Playground** (uma ferramenta oficial do Google para gerar tokens sem precisar rodar nada localmente).

### 4.1 Criar o Client ID / Client Secret

1. No mesmo projeto do Google Cloud que você já usou para a `YOUTUBE_API_KEY`, vá em **APIs e Serviços > Tela de consentimento OAuth** (*OAuth consent screen*).
2. Se ainda não configurou, escolha **Externo** (*External*) como tipo de usuário, preencha nome do app, e-mail de suporte e e-mail de contato do desenvolvedor. Salve.
3. Na aba **Público-alvo** (ou "Audience"), em **Usuários de teste**, adicione o seu próprio e-mail do Gmail (o mesmo dono do canal do YouTube).
4. Vá em **APIs e Serviços > Credenciais > + Criar Credenciais > ID do cliente OAuth**.
5. Em **Tipo de aplicativo**, escolha **App da Web** (*Web application*) — é obrigatório ser esse tipo, não "Desktop", para funcionar com o Playground no próximo passo.
6. Em **URIs de redirecionamento autorizados**, adicione exatamente:
   ```
   https://developers.google.com/oauthplayground
   ```
7. Clique em **Criar**. Copie o **Client ID** e o **Client Secret** exibidos — salve como `YOUTUBE_CLIENT_ID` e `YOUTUBE_CLIENT_SECRET` nos Secrets do GitHub.

### 4.2 Publicar o app (evita o token expirar a cada 7 dias)

Por padrão, apps em modo "Testing" recebem um `refresh_token` que **expira em 7 dias** — inviável para uma pipeline automática. Para evitar isso:

1. Ainda na **Tela de consentimento OAuth**, procure o status de publicação (*Publishing status*) e clique em **Publicar app** (*Publish App*).
2. O Google vai avisar que o app "não foi verificado" — para uso pessoal isso é normal e não impede o funcionamento. Você só verá uma tela de aviso ("Google não verificou este app") na primeira vez que autorizar, no próximo passo — clique em **Avançado > Acessar [nome do app] (não seguro)** para prosseguir.
3. Verificação completa só seria necessária se você fosse distribuir o app publicamente para terceiros — não é o seu caso.

### 4.3 Gerar o Refresh Token via OAuth Playground

1. Acesse https://developers.google.com/oauthplayground/
2. Clique no ícone de **engrenagem** (canto superior direito).
3. Marque **Use your own OAuth credentials**.
4. Cole o **OAuth Client ID** e **OAuth Client secret** que você gerou no passo 4.1.
5. Feche as configurações.
6. Na coluna da esquerda, na caixa de busca, procure **YouTube Data API v3**.
7. Marque o escopo:
   ```
   https://www.googleapis.com/auth/youtube.upload
   ```
8. Clique em **Authorize APIs**.
9. Faça login com a conta Google dona do canal do YouTube. Vai aparecer a tela de "app não verificado" — clique em **Avançado > Acessar (nome do app) (não seguro)** e depois **Permitir**.
10. Você volta pro Playground, na etapa **Step 2 — Exchange authorization code for tokens**. Clique em **Exchange authorization code for tokens**.
11. Os campos **Refresh token** e **Access token** são preenchidos. Copie o **Refresh token** — esse é o valor de `YOUTUBE_REFRESH_TOKEN`.
12. Salve como Secret no GitHub.

### 4.4 Limpeza (recomendado, opcional)

Depois de pegar o refresh token, você pode voltar em **Credenciais > (seu Client ID) > URIs de redirecionamento** e remover `https://developers.google.com/oauthplayground` da lista, por segurança — o token já foi gerado e continua válido independente disso.

---

## 5. CHANNELS (Channel IDs dos veículos monitorados)

Usado por `pipeline_config.py`, define quais canais o `find_and_download.py` monitora. Não é uma "API key", mas segue a mesma lógica de precisar ser obtido manualmente uma vez.

Já preenchi dois com confiança (conferi a descrição oficial do canal antes de usar):
- CNN Brasil: `UCvdwhh_fDyWccR42-rReZLw`
- G1: `UCaGmdJSSiR7fkh2A-c6emsA`

Faltam Estadão, Folha de S.Paulo e Metrópoles. Como fontes de terceiros às vezes trazem IDs desatualizados ou de canais "parecidos" (ex.: um canal secundário do mesmo veículo), o jeito mais seguro é pegar direto na página oficial:

1. Abra o canal oficial no YouTube (ex.: `youtube.com/@estadao`).
2. Clique em **"...mais"** na descrição do canal.
3. Clique em **"Compartilhar canal"** (*Share channel*).
4. Clique em **"Copiar ID do canal"** (*Copy channel ID*).
5. Cole o valor (formato `UCxxxxxxxxxxxxxxxxxxxxxx`) em `pipeline_config.py`, substituindo o `CHANNEL_ID_AQUI` correspondente.

Vale fazer esse mesmo processo para conferir os dois que já preenchi, se quiser ter certeza absoluta antes de rodar em produção.

---

## 6. YOUTUBE_COOKIES (necessário para o download não ser bloqueado)

O YouTube costuma bloquear downloads feitos por `yt-dlp` quando a requisição vem de um servidor de nuvem (como os runners do GitHub Actions), com o erro "Sign in to confirm you're not a bot". A forma padrão de contornar isso é autenticar o `yt-dlp` com cookies de uma sessão real, logada no navegador.

### Passo a passo (pelo navegador)

1. Instale a extensão **"Get cookies.txt LOCALLY"** no Chrome/Edge (ou equivalente no Firefox) — disponível na loja oficial de extensões do navegador.
2. Faça login normalmente em https://www.youtube.com com sua conta Google.
3. Com a aba do YouTube aberta, clique no ícone da extensão e exporte os cookies no formato **Netscape** (é o padrão da extensão) — ela gera um arquivo `cookies.txt`.
4. Abra esse arquivo num editor de texto e copie **todo o conteúdo**.
5. No GitHub, vá em **Settings > Secrets and variables > Actions > New repository secret**.
6. Nome: `YOUTUBE_COOKIES`. Cole o conteúdo completo do arquivo como valor.

### Pontos de atenção

- **Use uma conta secundária/descartável**, não sua conta pessoal principal — cookies de sessão dão acesso equivalente a estar logado, e automações desse tipo podem levar a conta a ser temporariamente limitada pelo YouTube se detectar padrão de uso incomum.
- Cookies de sessão **expiram/são invalidados com o tempo** (login em novo dispositivo, logout, alguns meses de inatividade da extensão). Se o erro "Sign in to confirm..." voltar a aparecer depois de um tempo funcionando, o cookie provavelmente expirou — repita o processo para gerar um novo.
- O uso de cookies não muda a análise de direitos autorais que já conversamos: continua valendo priorizar fontes com licença mais aberta (lives oficiais, canais institucionais) para reduzir risco de problema com os veículos de imprensa.
