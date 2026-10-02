from pathlib import Path
from tempfile import TemporaryDirectory

from core.config import Settings
from core.openai_gateway import OpenAIGateway
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore


def main():
    with TemporaryDirectory() as temp:
        settings = Settings(
            ai_provider="demo",
            openai_api_key="",
            openai_model="gpt-5.6",

            ollama_url="http://127.0.0.1:11434",
            ollama_model="qwen3:30b",
            ollama_timeout=900,
            ollama_keep_alive="15m",
            ollama_num_ctx=8192,
            ollama_num_predict=2048,
            ollama_num_thread=0,
            ollama_think=True,
            ollama_unload_after_request=False,

            demo_mode=True,
            projects_dir=Path(temp),
            ffmpeg_path="ffmpeg",

            generate_media=False,
            image_model="gpt-image-2",
            image_size="1536x1024",
            image_quality="low",
            tts_model="gpt-4o-mini-tts",
            tts_voice="coral",
            tts_instructions="Mów naturalnie po polsku.",
        )

        pipeline = ContentPipeline(
            ProjectStore(settings.projects_dir),
            OpenAIGateway(settings),
            settings,
        )
        project = pipeline.run("Test AI Content Studio")

        required = [
            "project.json",
            "01_research.md",
            "02_script.txt",
            "03_shots.json",
            "04_image_prompts.json",
            "05_narration.txt",
            "06_quality.json",
            "07_youtube.json",
            "pipeline_result.json",
        ]

        missing = [
            name
            for name in required
            if not (project.path / name).exists()
        ]

        if missing:
            raise SystemExit(f"Brakuje plików: {missing}")

        print("SMOKE TEST OK")
        print(project.path)


if __name__ == "__main__":
    main()
