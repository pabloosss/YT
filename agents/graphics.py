from __future__ import annotations

from pathlib import Path

from agents.base import BaseAgent


class GraphicsAgent(BaseAgent):
    name = "Grafika"

    def run(self, *, topic: str, shots: list[dict]) -> list[dict]:
        prompts = []
        for shot in shots:
            visual = shot.get("visual", "")
            camera = shot.get("camera", "")
            lighting = shot.get("lighting", "")

            if self.ai.demo_mode:
                prompt = (
                    f"Cinematic YouTube visual about {topic}. {visual}. "
                    f"Camera: {camera}. Lighting: {lighting}. "
                    "No text, coherent visual style across the whole video, landscape composition."
                )
            else:
                prompt = self.ai.ask(
                    instructions=(
                        "Jesteś art directorem. Tworzysz pojedynczy precyzyjny prompt do generatora obrazu. "
                        "Dbaj o spójność stylistyczną między ujęciami. Nie dodawaj tekstu do obrazu. "
                        "Odpowiadaj wyłącznie promptem."
                    ),
                    prompt=(
                        f"Temat: {topic}\nOpis ujęcia: {visual}\nKamera: {camera}\n"
                        f"Światło: {lighting}\nFormat docelowy: poziomy YouTube."
                    ),
                )
            prompts.append({"shot": shot.get("shot"), "prompt": prompt})
        return prompts

    def render(
        self,
        *,
        prompts: list[dict],
        project_path: Path,
        model: str,
        size: str,
        quality: str,
    ) -> list[Path]:
        images_dir = project_path / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        results: list[Path] = []

        if self.ai.demo_mode:
            return self._render_demo_placeholders(prompts, images_dir)

        for index, item in enumerate(prompts, start=1):
            shot_number = item.get("shot") or index
            target = images_dir / f"shot_{int(shot_number):03d}.png"
            self.ai.generate_image(
                prompt=str(item["prompt"]),
                output_path=target,
                model=model,
                size=size,
                quality=quality,
            )
            results.append(target)

        return results

    @staticmethod
    def _render_demo_placeholders(prompts: list[dict], images_dir: Path) -> list[Path]:
        try:
            from PIL import Image, ImageDraw
        except ImportError as exc:
            raise RuntimeError("Tryb demo grafiki wymaga Pillow.") from exc

        results: list[Path] = []
        for index, item in enumerate(prompts, start=1):
            shot_number = item.get("shot") or index
            target = images_dir / f"shot_{int(shot_number):03d}.png"

            image = Image.new("RGB", (1280, 720), (24, 24, 28))
            draw = ImageDraw.Draw(image)
            draw.text((60, 60), f"AI CONTENT STUDIO · SHOT {shot_number}", fill=(235, 235, 235))
            prompt = str(item.get("prompt", ""))
            lines = [prompt[i:i + 80] for i in range(0, min(len(prompt), 560), 80)]
            y = 150
            for line in lines:
                draw.text((60, y), line, fill=(210, 210, 210))
                y += 34
            image.save(target)
            results.append(target)

        return results
