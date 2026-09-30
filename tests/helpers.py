from pathlib import Path
import json
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def make_fixture(parent: Path, *, cases_per_split: int = 6, repetitions: int = 1):
    suite = parent / "suite"
    app = parent / "app"
    state = parent / "state"
    suite.mkdir()
    app.mkdir()
    (app / "app.py").write_text('import json,sys\nr=json.load(sys.stdin)\njson.dump({"output":0,"usage":{"cost_usd":0},"model":"fixture"},sys.stdout)\n')
    (suite / "grader.py").write_text('import json,sys\nr=json.load(sys.stdin)\njson.dump({"metrics":{"quality":float(r["output"]==r["expected"])},"usage":{"cost_usd":0}},sys.stdout)\n')
    cfg = (ROOT / "examples/routing/eval.toml").read_text()
    cfg = cfg.replace('name = "routing-demo"', 'name = "fixture"').replace('repetitions = 2', f'repetitions = {repetitions}')
    cfg = cfg.replace('accuracy','quality').replace('min_validation_groups = 8', 'min_validation_groups = 2').replace('bootstrap_samples = 2000','bootstrap_samples = 500')
    cfg = cfg[:cfg.index('# This fixture')] + '[optimizer]\nbackend = "command"\ncommand = ["{python}", "-S", "{suite}/demo_optimizer.py"]\ntimeout_s = 5\n'
    (suite / 'eval.toml').write_text(cfg)
    (suite / 'demo_optimizer.py').write_text('import json,sys\nfrom pathlib import Path\nr=json.load(sys.stdin)\ns=Path("app.py").read_text().replace(\'"output":0\',\'"output":1\')\njson.dump({"hypothesis":"Use the correct constant for this test fixture","edits":[{"path":"app.py","content":s}],"notes":"test"},sys.stdout)\n')
    cases=[]
    for split in ('train','validation','test'):
        for i in range(cases_per_split):
            cases.append({'id':f'{split}-{i}', 'input':{'split_marker':f'SECRET-{split}-{i}', 'n':i}, 'expected':1, 'tags':['constant'], 'split':split})
    (suite/'cases.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in cases))
    return suite, app, state


def start_fixture(parent: Path, **kwargs):
    from codex_eval_lab.engine import initialize
    suite,app,state=make_fixture(parent,**kwargs)
    initialize(suite,app,state,approvals={'cases':True,'grader':True,'execution':True})
    return suite,app,state
