@echo off
setlocal
cd /d "%~dp0"

if exist ".env" (
    copy /Y ".env" ".env.backup" >nul
    echo Istniejacy .env zapisano jako .env.backup
)

(
echo AI_PROVIDER=ollama
echo AI_STUDIO_DEMO=false
echo OLLAMA_URL=http://127.0.0.1:11434
echo OLLAMA_MODEL=qwen3:30b
echo OLLAMA_TIMEOUT=900
echo OLLAMA_KEEP_ALIVE=15m
echo.
echo OPENAI_API_KEY=
echo OPENAI_MODEL=gpt-5.6
echo.
echo PROJECTS_DIR=projects
echo GENERATE_MEDIA=false
echo FFMPEG_PATH=ffmpeg
) > ".env"

echo.
echo Gotowe. AI Content Studio zostal ustawiony na lokalna Ollame:
echo qwen3:30b
echo.
echo Teraz uruchom run_windows.bat
pause
