from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy

from market_rates import model_adapter, ollama_adapter
from market_rates.extraction_contract import response_schema


class LocalModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "evidence"
        self.root.mkdir()
        # Adapter tests use a PNG signature; an actual model is never called.
        (self.root / "tile.png").write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-test-bytes")
        self.pages = [{"id": "page1", "bank": "DEMO", "url": "https://example.invalid",
                       "text": "ONLY_TEXT_LANE", "images": ["tile.png"]}]
        self.config = {"models": {"provider": "ollama"}}
        self.empty = {"offers": [], "inventory": [{"page_id": "page1", "row_count": 0, "notes": "fixture"}],
                      "coverage_complete": True, "unreadable": []}

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, lane="llm", config=None):
        with patch.dict("os.environ", {}, clear=True):
            return ollama_adapter.build_payload(lane, self.pages, self.root, config or self.config, "2026-09-24")

    def test_local_default_and_sequential(self):
        self.assertEqual(model_adapter.provider({}), "ollama")
        self.assertEqual(model_adapter.workers({}), 1)

    def test_cloud_configuration_cannot_enable_remote_calls(self):
        with patch('urllib.request.urlopen') as network:
            for name in ['openai', 'unknown']:
                config={'models':{'provider':name}}
                for operation in [model_adapter.provider,model_adapter.workers,model_adapter.preflight]:
                    with self.assertRaises(ValueError):operation(config)
                with self.assertRaises(ValueError):model_adapter.extract('llm',self.pages,self.root,config,'2026-09-24')
            network.assert_not_called()

    def test_no_cloud_fallback_on_local_failure(self):
        with patch("market_rates.ollama_adapter.extract", side_effect=RuntimeError("offline")), \
             patch("market_rates.openai_adapter.extract") as cloud:
            with self.assertRaises(RuntimeError): model_adapter.extract("llm", self.pages, self.root, {}, "2026-09-24")
            cloud.assert_not_called()

    def test_independent_modalities_without_key(self):
        text = self.payload("llm"); vision = self.payload("vlm")
        self.assertIn("ONLY_TEXT_LANE", json.dumps(text))
        self.assertNotIn("ONLY_TEXT_LANE", json.dumps(vision))
        self.assertFalse(any("images" in m for m in text["messages"]))
        self.assertTrue(any("images" in m for m in vision["messages"]))
        self.assertEqual(text["format"], response_schema(self.pages))
        self.assertEqual(text["options"]["num_ctx"], 16384)

    def test_remote_and_cloud_models_rejected(self):
        with patch.dict("os.environ", {}, clear=True):
            for url in ["https://ollama.com", "http://127.0.0.1.evil.test", "http://localhost/path", "http://user@localhost:11434"]:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    ollama_adapter.settings({"models": {"base_url": url}})
            with self.assertRaises(ValueError): ollama_adapter.settings({"models": {"vision_model": "qwen3.5:cloud"}})

    def test_local_alias_pointing_to_cloud_rejected(self):
        with patch("market_rates.ollama_adapter.request_json", return_value={"capabilities": ["completion", "vision"], "remote_host": "https://ollama.com"}):
            with self.assertRaises(ValueError): ollama_adapter.check_model({}, "local-looking-alias", vision=True)

    def test_text_only_model_cannot_be_vlm(self):
        with patch("market_rates.ollama_adapter.request_json", return_value={"capabilities": ["completion"]}):
            with self.assertRaises(ValueError): ollama_adapter.check_model({}, "text-only", vision=True)

    def test_same_model_preflight_checked_once_with_vision(self):
        with patch.dict("os.environ", {}, clear=True), patch("market_rates.ollama_adapter.check_model", return_value={"name": "qwen3.5:4b"}) as check:
            result = ollama_adapter.preflight({})
        check.assert_called_once_with({}, "qwen3.5:4b", vision=True)
        self.assertTrue(result["same_model_two_modalities"])

    def test_text_limit_fails_before_model_call(self):
        with self.assertRaises(ValueError): self.payload(config={"models": {"max_text_chars": 2}})

    def test_image_limit_fails_instead_of_dropping_images(self):
        self.pages[0]["images"] *= 3
        with self.assertRaises(ValueError): self.payload("vlm")

    def test_missing_and_non_png_images_rejected(self):
        self.pages[0]["images"] = []
        with self.assertRaises(ValueError): self.payload("vlm")
        (self.root / "demo.svg").write_text("<svg/>")
        self.pages[0]["images"] = ["demo.svg"]
        with self.assertRaises(ValueError): self.payload("vlm")

    def test_context_budget_fails_before_sending(self):
        with self.assertRaises(ValueError): self.payload(config={"models": {"num_ctx": 4200}})

    def test_complete_response_has_local_metadata(self):
        response = {"done": True, "done_reason": "stop", "model": "qwen3.5:4b",
                    "message": {"content": json.dumps(self.empty)}, "prompt_eval_count": 300, "eval_count": 100}
        with patch.dict("os.environ", {}, clear=True), patch("market_rates.ollama_adapter.check_model"), \
             patch("market_rates.ollama_adapter.request_json", return_value=response) as call:
            result, meta = model_adapter.extract("llm", self.pages, self.root, self.config, "2026-09-24")
        self.assertEqual(result, self.empty)
        self.assertEqual(meta["provider"], "ollama")
        self.assertFalse(meta["cloud_fallback"])
        self.assertEqual(call.call_args.args[1], "/api/chat")
        self.assertTrue((self.root.parent / meta["raw_response_file"]).exists())

    def test_truncated_response_rejected(self):
        response = {"done": True, "done_reason": "length", "message": {"content": json.dumps(self.empty)}}
        with patch("market_rates.ollama_adapter.check_model"), patch("market_rates.ollama_adapter.request_json", return_value=response):
            with self.assertRaises(RuntimeError): ollama_adapter.extract("llm", self.pages, self.root, self.config, "2026-09-24")

    def test_empty_response_is_failure_with_raw_response_saved(self):
        evidence = self.root / "evidence"; evidence.mkdir()
        response = {"done": True, "done_reason": "stop", "message": {"role": "assistant", "content": ""}}
        with patch("market_rates.ollama_adapter.check_model"), patch("market_rates.ollama_adapter.request_json", return_value=response):
            with self.assertRaisesRegex(ValueError, "空content"):
                ollama_adapter.extract("llm", self.pages, evidence, self.config, "2026-09-24")
        self.assertEqual(len(list(self.root.glob("ollama-llm-response-*.json"))), 1)

    def test_invalid_structure_rejected(self):
        invalid = deepcopy(self.empty); invalid["coverage_complete"] = "true"
        with self.assertRaises(ValueError): ollama_adapter.validate_extraction(invalid)
        invalid = deepcopy(self.empty); invalid["inventory"][0]["row_count"] = -1
        with self.assertRaises(ValueError): ollama_adapter.validate_extraction(invalid)
        invalid = deepcopy(self.empty); invalid["inventory"].append(invalid["inventory"][0])
        with self.assertRaises(ValueError): ollama_adapter.validate_extraction(invalid)

    def test_redirect_to_remote_is_blocked(self):
        with self.assertRaises(ValueError): ollama_adapter.NoRedirect().redirect_request(None, None, 302, "", {}, "https://external.test")

    def test_runtime_status_distinguishes_cpu_and_gpu(self):
        with patch("market_rates.ollama_adapter.request_json", return_value={"models": [
            {"name": "cpu", "size_vram": 0, "context_length": 16384},
            {"name": "gpu", "size_vram": 4000000000, "context_length": 16384}]}):
            rows = ollama_adapter.runtime_status({})
        self.assertFalse(rows[0]["gpu_in_use"])
        self.assertTrue(rows[1]["gpu_in_use"])


if __name__ == "__main__":
    unittest.main()
