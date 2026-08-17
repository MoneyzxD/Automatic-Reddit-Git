"""
pipeline/
=========
Módulos do Reddit Stories Automation Pipeline.

Ordem de execução:
    1. extractor.py   → extrai histórias via Reddit JSON público
    2. filter.py      → filtra e pontua histórias
    3. adapter.py     → adapta e reescreve o script
    4. splitter.py    → divide histórias longas em partes
    5. voice.py       → gera narração (edge-tts / gTTS)
    6. subtitle.py    → gera legendas SRT (Whisper + stable-ts)
    7. video.py       → renderiza vídeo (FFmpeg)
    8. thumbnail.py   → gera thumbnails (Pillow)
    9. metadata.py    → gera metadados SEO
   10. organizer.py   → organiza arquivos por idioma/data
   11. publisher.py   → [MAPEADO] publicação futura YouTube
"""
