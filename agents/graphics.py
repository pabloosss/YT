from __future__ import annotations

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
                    f"Camera: {camera}. Lighting: {lighting}. No text, coherent visual style, 16:9."
                )
            else:
                prompt = self.ai.ask(
                    instructions=(
                        "Jesteś art directorem. Tworzysz pojedynczy precyzyjny prompt do generatora obrazu. "
                        "Dbaj o spójność między ujęciami. Nie dodawaj tekstu. Odpowiadaj tylko promptem."
                    ),
                    prompt=(
                        f"Temat: {topic}\nOpis ujęcia: {visual}\nKamera: {camera}\n"
                        f"Światło: {lighting}\nFormat: 16:9."
                    ),
                )
            prompts.append({"shot": shot.get("shot"), "prompt": prompt})
        return prompts
