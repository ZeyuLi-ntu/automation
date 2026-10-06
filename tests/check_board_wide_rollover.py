"""Plan-only integration check: next week retains this week and reuses tiers."""
import tempfile
from pathlib import Path
from datetime import date,timedelta
from unittest.mock import patch
from market_rates.common import load,save
from market_rates.board_wide_plan import plan

if __name__=='__main__':
    pointer=load('outputs/latest-board-pilot.json');base=load(Path(pointer['output'])/'table-validation-plan.json');run=load(Path(pointer['source_run'])/'run.json')
    original_ledger=Path('data/manual-review.json').read_bytes()
    with tempfile.TemporaryDirectory(prefix='board-rollover-plan-') as temp:
        root=Path(temp);source=root/'synthetic-next-week';source.mkdir();run['as_of']=(date.fromisoformat(run['as_of'])+timedelta(days=7)).isoformat();save(source/'run.json',run)
        # Only bypass the physical evidence directory location for this
        # synthetic date fixture; production source proof is still validated.
        with patch('market_rates.board_wide_plan.check_evidence'):
            result=plan(source,root/'plan',base)
        assert result['report_template']==base['report_output']
        assert all(h['insert_date'] for h in result['histories'])
        assert all(not h['inserts'] for h in result['histories']),[(h['currency'],h['inserts']) for h in result['histories']]
        assert result['rainbow_shift']==0
        assert Path('data/manual-review.json').read_bytes()==original_ledger
        save(Path(pointer['output'])/'rollover-plan-checks.json',dict(passed=True,synthetic_fixture_only=True,checks=['new week uses last published workbooks','new USD/CNY date columns','unchanged conditions reuse existing bank rows','stable rainbow extent','manual ledger untouched']))
    print('Next-week plan checks passed; no synthetic workbook published')
