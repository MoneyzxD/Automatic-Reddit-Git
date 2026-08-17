# Reddit Stories Automation Pipeline

Pipeline 100% gratuito para geração automática de vídeos de histórias do Reddit
em 3 idiomas: **Português (BR)**, **Inglês** e **Espanhol**.

## Stack gratuita

| Etapa | Ferramenta | Custo |
|-------|-----------|-------|
| Extração | Reddit JSON público | Grátis |
| Voz | edge-tts (Microsoft Edge) | Grátis |
| Fallback voz | gTTS (Google TTS) | Grátis |
| LLM | Ollama (local) | Grátis |
| Legendas | Whisper + stable-ts | Grátis |
| Vídeo | FFmpeg | Grátis |
| Thumbnails | Pillow | Grátis |
| Banco | SQLite | Grátis |

## Instalação rápida

```bash
# 1. Clonar e entrar na pasta
cd reddit_pipeline

# 2. Instalar dependências Python
pip install -r requirements.txt

# 3. Instalar FFmpeg no sistema
sudo apt install ffmpeg          # Linux
brew install ffmpeg              # macOS

# 4. (Opcional) Instalar Ollama para adaptação com LLM
# Baixe em: https://ollama.ai
# Depois: ollama pull llama3

# 5. Configurar ambiente
cp .env.example .env

# 6. Rodar pipeline
python main.py

# Testar sem gerar arquivos
python main.py --dry-run

# Apenas português
python main.py --lang pt
```

## Saída por execução

Para cada história aprovada, o pipeline gera **3 vídeos** (um por idioma):

```
data/exports/pt/{date}_{story_id}.mp4
data/exports/en/{date}_{story_id}.mp4
data/exports/es/{date}_{story_id}.mp4
```

Cada vídeo acompanha thumbnail `.jpg` e metadados `.json`.

## Etapas do pipeline

1. **Extractor** → busca histórias via Reddit JSON público (sem API key)
2. **Filter** → pontuação 0–100 por engajamento, emoção e segurança
3. **Adapter** → reescreve com Ollama local (fallback: regras Python)
4. **Splitter** → divide histórias longas em partes de 3–7 min
5. **Voice** → narração com edge-tts (fallback: gTTS)
6. **Subtitle** → legendas SRT com Whisper + stable-ts
7. **Video** → renderização FFmpeg 1080×1920 (9:16)
8. **Thumbnail** → geração com Pillow
9. **Metadata** → títulos, tags e descrições SEO
10. **Publisher** → [Fase 2] publicação automática YouTube

## Estrutura de pastas

Gerada automaticamente por `setup_structure.py`.
