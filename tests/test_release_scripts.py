from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
installer=module('install_skills');publisher=module('publish_github');packager=module('package_release')
calibration=module('calibrate_judge');prepare=module('prepare_codex_demo')

class ReleaseScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def release(self):
        root=self.root/'source';root.mkdir();(root/'README.md').write_text('safe release')
        (root/'RELEASE_MANIFEST.json').write_text(json.dumps({'schema_version':1,'name':'codex-eval-lab','files':{'README.md':hashlib.sha256(b'safe release').hexdigest()}}))
        return root
    def test_installer_copies_all_skills_and_references(self):
        out=self.root/'skills';result=installer.install(out)
        self.assertEqual(len(result['installed']),4)
        for name in installer.SKILLS:
            self.assertTrue((out/name/'SKILL.md').is_file())
            self.assertTrue((out/name/'references/PROTOCOL.md').is_file())
            runtime=json.loads((out/name/'references/installation.json').read_text())
            self.assertEqual(runtime['module'],'codex_eval_lab')
            self.assertIn('Machine-local runtime',(out/name/'SKILL.md').read_text())
            self.assertTrue((out/name/'.eval-lab-install.json').is_file())
    def test_install_does_not_overwrite_one_conflict_or_partially_install(self):
        out=self.root/'skills';(out/'hillclimb').mkdir(parents=True);(out/'hillclimb/KEEP').write_text('keep')
        with self.assertRaises(ValueError):installer.install(out)
        self.assertEqual((out/'hillclimb/KEEP').read_text(),'keep');self.assertFalse((out/'build-eval').exists())
    def test_install_refuses_incomplete_source(self):
        with self.assertRaises(ValueError):installer.install(self.root/'out',self.root/'missing')
    def test_install_refuses_symlink(self):
        actual=self.root/'actual';actual.mkdir();alias=self.root/'alias';alias.symlink_to(actual,target_is_directory=True)
        with self.assertRaises(ValueError):installer.install(alias/'skills')
    def test_calibration_perfect(self):
        r=calibration.calibrate([{'id':'a','human':'yes','judge':'yes'},{'id':'b','human':'no','judge':'no'}])
        self.assertEqual(r['agreement'],1);self.assertEqual(r['cohens_kappa'],1)
    def test_calibration_undefined_single_category(self):
        self.assertIsNone(calibration.calibrate([{'id':'a','human':'yes','judge':'yes'}])['cohens_kappa'])
    def test_calibration_confusion(self):
        r=calibration.calibrate([{'id':'a','human':'yes','judge':'no'},{'id':'b','human':'no','judge':'yes'}])
        self.assertEqual(r['agreement'],0);self.assertEqual(r['cohens_kappa'],-1)
    def test_calibration_duplicates(self):
        with self.assertRaises(ValueError):calibration.calibrate([{'id':'a','human':'x','judge':'x'}]*2)
    def test_calibration_rejects_empty(self):
        with self.assertRaises(ValueError):calibration.calibrate([])
    def test_calibration_rejects_numeric_labels(self):
        with self.assertRaises(ValueError):calibration.calibrate([{'id':'a','human':1,'judge':1}])
    def test_publish_dry_run_uses_no_commands(self):
        root=self.release()
        with patch.object(publisher,'run',side_effect=AssertionError('must not invoke')):
            r=publisher.publish(root,'trevordcampbell/codex-eval-lab',True)
        self.assertEqual(r['visibility'],'private');self.assertEqual(r['files'],1)
    def test_publisher_rejects_modified_release(self):
        root=self.release();(root/'README.md').write_text('changed')
        with self.assertRaises(ValueError):publisher.verified_files(root)
    def test_publisher_missing_tool_fails_before_auth(self):
        root=self.release()
        with patch.object(publisher.shutil,'which',return_value=None),self.assertRaises(ValueError):publisher.publish(root,'owner/new')
    def test_publisher_owner_mismatch(self):
        import subprocess
        root=self.release()
        outputs=[subprocess.CompletedProcess([],0,'',''),subprocess.CompletedProcess([],0,json.dumps({'login':'different','id':1}),'')]
        with patch.object(publisher.shutil,'which',return_value='tool'),patch.object(publisher,'run',side_effect=outputs),self.assertRaises(ValueError):publisher.publish(root,'owner/new')
    def test_publisher_existing_repository_refused(self):
        import subprocess
        root=self.release()
        outputs=[subprocess.CompletedProcess([],0,'',''),subprocess.CompletedProcess([],0,json.dumps({'login':'owner','id':1}),''),subprocess.CompletedProcess([],0,'{}','')]
        with patch.object(publisher.shutil,'which',return_value='tool'),patch.object(publisher,'run',side_effect=outputs),self.assertRaises(ValueError):publisher.publish(root,'owner/new')
    def test_publisher_invalid_target(self):
        for bad in ['../target','https://github.com/a/b','owner/repo;rm','--flag','owner/name/extra']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):publisher.publish(self.release() if not (self.root/'source').exists() else self.root/'source',bad,True)
    def test_release_path_traversal_rejected(self):
        root=self.release();m=root/'RELEASE_MANIFEST.json';data=json.loads(m.read_text());data['files']={'../escape':'hash'};m.write_text(json.dumps(data))
        with self.assertRaises(ValueError):publisher.verified_files(root)
    def test_publish_ignores_unmanifested_private_file(self):
        root=self.release();(root/'secret-token.txt').write_text('never stage this')
        self.assertEqual(publisher.verified_files(root),[Path('README.md')])
    def test_prepare_real_codex_suite(self):
        out=self.root/'suite';prepare.prepare(out)
        self.assertIn('backend = "codex"',(out/'eval.toml').read_text());self.assertFalse((out/'demo_optimizer.py').exists())
        self.assertNotIn('demo_optimizer',(out/'eval.toml').read_text())
    def test_prepare_never_overwrites(self):
        with self.assertRaises(ValueError):prepare.prepare(self.root)
    def test_package_must_be_outside_source(self):
        with self.assertRaises(ValueError):packager.package(ROOT,ROOT/'bad-release')
    def test_release_allowlist_omits_private_state(self):
        root=self.root/'repo';root.mkdir()
        for name in packager.TOP:(root/name).write_text('required')
        (root/'src').mkdir();(root/'src/code.py').write_text('pass')
        (root/'src/.env').write_text('secret');(root/'state.sqlite3').write_text('private');(root/'secrets.txt').write_text('private')
        selected={p.relative_to(root).as_posix() for p in packager.release_files(root)}
        self.assertIn('src/code.py',selected);self.assertNotIn('src/.env',selected);self.assertNotIn('secrets.txt',selected)
    def test_package_manifest_and_hashes(self):
        root=self.root/'repo';root.mkdir()
        for name in packager.TOP:(root/name).write_text('required')
        result=packager.package(root,self.root/'release')
        with zipfile.ZipFile(result['archive']) as z:
            data=json.loads(z.read('codex-eval-lab/RELEASE_MANIFEST.json'))
            for name,sha in data['files'].items():self.assertEqual(hashlib.sha256(z.read('codex-eval-lab/'+name)).hexdigest(),sha)
        with self.assertRaises(ValueError):packager.package(root,self.root/'release')
    def test_package_includes_only_documentation_svg_figures(self):
        root=self.root/'repo';root.mkdir()
        for name in packager.TOP:(root/name).write_text('required')
        svg='<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
        names=['docs/assets/workflow.svg','docs/other.svg','examples/figure.svg',
               'docs/assets/nested/figure.svg','docs/assets/.env.svg']
        for name in names:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(svg)
        # Secret-like filenames must still fail instead of entering the archive.
        with self.assertRaises(ValueError):packager.release_files(root)
        (root/'docs/assets/.env.svg').unlink()
        result=packager.package(root,self.root/'release')
        with zipfile.ZipFile(result['archive']) as z:
            data=json.loads(z.read('codex-eval-lab/RELEASE_MANIFEST.json'))
            self.assertEqual(z.read('codex-eval-lab/docs/assets/workflow.svg'),svg.encode())
            self.assertEqual(data['files']['docs/assets/workflow.svg'],hashlib.sha256(svg.encode()).hexdigest())
            for name in names[1:]:self.assertNotIn(name,data['files'])
    def test_package_rejects_symlinked_documentation_svg(self):
        root=self.root/'repo';root.mkdir()
        for name in packager.TOP:(root/name).write_text('required')
        target=self.root/'private.svg';target.write_text('<svg/>')
        assets=root/'docs/assets';assets.mkdir(parents=True)
        (assets/'figure.svg').symlink_to(target)
        with self.assertRaises(ValueError):packager.release_files(root)

if __name__=='__main__':unittest.main()

class AutomationExamplePackagingTests(unittest.TestCase):
    def test_source_release_preserves_rust_and_oracle_specifications(self):
        names = {p.relative_to(ROOT).as_posix() for p in packager.release_files(ROOT)}
        self.assertIn('examples/rust-log-aggregation/app/aggregate.rs', names)
        self.assertIn('examples/rust-log-aggregation/winner/aggregate.rs', names)
        self.assertIn('examples/automation/specification.txt', names)
        self.assertIn('docs/AUTOMATION.md', names)

    def test_plugin_bundle_preserves_executable_examples_and_skill_metadata(self):
        builder = module('build_plugin')
        with tempfile.TemporaryDirectory() as tmp:
            result = builder.build(ROOT, Path(tmp) / 'plugin')
            root = Path(result['plugin'])
            self.assertTrue((root / 'examples/automation/specification.txt').is_file())
            self.assertTrue((root / 'examples/rust-log-aggregation/app/aggregate.rs').is_file())
            self.assertTrue((root / 'skills/build-eval/agents/openai.yaml').is_file())
