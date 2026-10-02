from pathlib import Path
from tempfile import TemporaryDirectory

from core.config import Settings
from core.openai_gateway import OpenAIGateway
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore


def main():
    with TemporaryDirectory() as temp:
        settings = Settings(
            openai_api_key="",
            openai_model="gpt-5.6-sol",
            demo_mode=True,
            projects_dir=Path(temp),
            ffmpeg_path="ffmpeg",
        )
        pipeline = ContentPipeline(ProjectStore(settings.projects_dir), OpenAIGateway(settings))
        project = pipeline.run("Test AI Content Studio")

        required = [
            "project.json",
            "01_research.md",
            "02_script.txt",
            "03_shots.json",
            "04_image_prompts.json",
            "05_narration.txt",
        ]
        missing = [name for name in required if not (project.path / name).exists()]
        if missing:
            raise SystemExit(f"Brakuje plików: {missing}")

        print("SMOKE TEST OK")
        print(project.path)


if __name__ == "__main__":
    main()
