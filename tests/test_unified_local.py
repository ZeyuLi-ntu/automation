import sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from scripts.run_all import project_lock,preflight
from market_rates.common import save

class UnifiedLocalTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='win32','Windows local runner')
    def test_second_runner_rejected_and_lock_released_after_error(self):
        with TemporaryDirectory() as temp,patch('scripts.run_all.ROOT',Path(temp)):
            with self.assertRaisesRegex(ValueError,'stop'):
                with project_lock():
                    with self.assertRaisesRegex(RuntimeError,'已有全量任务'):
                        with project_lock():pass
                    raise ValueError('stop')
            with project_lock():pass
    def test_cloud_model_configuration_rejected_before_launch(self):
        with TemporaryDirectory() as temp,patch('scripts.run_all.ROOT',Path(temp)),patch('scripts.run_all.runtimes',return_value={}):
            config=Path(temp)/'config';config.mkdir()
            save(config/'project.local.json',dict(models=dict(provider='ollama',base_url='https://example.com')))
            with self.assertRaisesRegex(ValueError,'只允许本机Ollama'):preflight()
