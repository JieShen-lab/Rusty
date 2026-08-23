from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import initialized_database
from rusty.services.ai_client import AIResponse
from rusty.services.ai_request_executor import AIRequestExecutor
from rusty.services.prompt_slot_service import PROMPT_SLOT_KEYS, PromptSlotService
from rusty.services.structured_model_service import StructuredModelService


class RecordingClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, model, api_key, messages):
        self.calls.append(messages)
        return AIResponse(next(self.responses), {}, 1)


def add_local_model(database_path: Path) -> int:
    from rusty.db import session

    with session(database_path) as connection:
        return int(connection.execute(
            """INSERT INTO ai_models(display_name,provider,base_url,model_name,is_default)
               VALUES('Local','openai_compatible','http://127.0.0.1:11434/v1','test',1)"""
        ).lastrowid)


class CanonicalAIRegressionTests(unittest.TestCase):
    def test_executor_injects_only_global_system_and_rejects_caller_system(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database = initialized_database(Path(directory) / "rusty.db")
            add_local_model(database)
            client = RecordingClient(["OK", "OK"])
            executor = AIRequestExecutor(database, ai_client=client)

            executor.execute([{"role": "user", "content": "task"}])
            self.assertEqual("system", client.calls[0][0]["role"])
            self.assertEqual(
                PromptSlotService(database).get_global_system_prompt(),
                client.calls[0][0]["content"],
            )
            self.assertEqual(1, sum(item["role"] == "system" for item in client.calls[0]))
            with self.assertRaisesRegex(ValueError, "cannot provide a system"):
                executor.execute([{"role": "system", "content": "second system"}])

            result = executor.test_connection(1)
            self.assertTrue(result.ok)
            self.assertEqual("system", client.calls[1][0]["role"])

    def test_prompt_service_exposes_exactly_six_nonempty_seeded_slots(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database = initialized_database(Path(directory) / "rusty.db")
            service = PromptSlotService(database)
            slots = service.list_slots()
            self.assertEqual(PROMPT_SLOT_KEYS, {slot.slot_key for slot in slots})
            self.assertEqual(6, len(slots))
            self.assertTrue(all(slot.content.strip() for slot in slots))
            with self.assertRaisesRegex(ValueError, "cannot be empty"):
                service.update_slot("global_system", "   ")

    def test_structured_repair_reuses_executor_without_a_second_system(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database = initialized_database(Path(directory) / "rusty.db")
            add_local_model(database)
            client = RecordingClient(["not json", '{"ok": true}'])
            executor = AIRequestExecutor(database, ai_client=client)
            result = StructuredModelService(database, executor=executor).run(
                messages=[{"role": "user", "content": "return json"}],
                output_schema={"type": "object", "required": ["ok"]},
                validator=lambda value: value if value.get("ok") is True else (_ for _ in ()).throw(ValueError("ok")),
            )
            self.assertTrue(result.value["ok"])
            self.assertEqual(2, len(client.calls))
            self.assertTrue(all(sum(item["role"] == "system" for item in call) == 1 for call in client.calls))


if __name__ == "__main__":
    unittest.main()
