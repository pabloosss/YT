from __future__ import annotations

from collections.abc import Callable

from agents.graphics import GraphicsAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.showrunner import ShowrunnerAgent
from agents.voice import VoiceAgent
from core.openai_gateway import OpenAIGateway
from core.project_store import ProjectStore


StatusCallback = Callable[[str, str], None]


class ContentPipeline:
    def __init__(self, store: ProjectStore, ai: OpenAIGateway):
        self.store = store
        self.research_agent = ResearchAgent(ai)
        self.script_agent = ScriptAgent(ai)
        self.showrunner_agent = ShowrunnerAgent(ai)
        self.graphics_agent = GraphicsAgent(ai)
        self.voice_agent = VoiceAgent()

    def run(self, topic: str, status: StatusCallback | None = None):
        status = status or (lambda _agent, _state: None)
        project = self.store.create(topic)

        status("Research", "RUNNING")
        research = self.research_agent.run(topic=topic)
        project.write_text("01_research.md", research)
        status("Research", "DONE")

        status("Scenariusz", "RUNNING")
        script = self.script_agent.run(topic=topic, research=research)
        project.write_text("02_script.txt", script)
        status("Scenariusz", "DONE")

        status("Showrunner", "RUNNING")
        shots = self.showrunner_agent.run(topic=topic, script=script)
        project.write_json("03_shots.json", shots)
        status("Showrunner", "DONE")

        status("Grafika", "RUNNING")
        prompts = self.graphics_agent.run(topic=topic, shots=shots)
        project.write_json("04_image_prompts.json", prompts)
        status("Grafika", "DONE")

        status("Lektor", "RUNNING")
        self.voice_agent.run(script=script, project_path=project.path)
        project.write_text("05_narration.txt", script)
        status("Lektor", "DONE")

        return project
