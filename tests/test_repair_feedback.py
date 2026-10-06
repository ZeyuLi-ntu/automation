import tempfile,unittest
from pathlib import Path
from market_rates.common import save
from market_rates.repair_feedback import write_summary

class RepairFeedbackTests(unittest.TestCase):
    def test_duplicates_are_not_counted_and_failed_tasks_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'board'/'UOB';source.mkdir(parents=True)
            state=dict(status='needs_review',source_root=str(source),attempts=[dict(actions=[dict(task='row',method='原图拆图')])],remaining=[dict(task='row',error='数字不一致')])
            save(source/'automatic-repair.json',state)
            save(root/'board'/'UOB-qualified'/'automatic-repair.json',state)
            text=write_summary(root).read_text(encoding='utf-8-sig')
            self.assertEqual(text.count('：仍需处理'),1)
            self.assertIn('数字不一致',text)
            self.assertIn('自动修复结果.txt',text)

    def test_empty_summary_does_not_claim_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            text=write_summary(tmp).read_text(encoding='utf-8-sig')
            self.assertIn('不代表任务已完成',text)
