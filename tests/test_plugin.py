from __future__ import annotations
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab.plugin_server import PacketStore, RESOURCE_URI, build_server, calibration_summary
from codex_eval_lab.review import create_packet
from codex_eval_lab.review_ui import render_standalone_review, render_mcp_review, write_standalone_review
from codex_eval_lab.util import LabError

ROOT = Path(__file__).resolve().parents[1]


def packet():
    return create_packet([
        {"id":"tune-1", "group":"one", "partition":"tuning", "input":"<img src=x onerror=alert(1)>",
         "output":"</script><script>window.PWNED=true</script>", "trace":[{"content":"visible tuning"}]},
        {"id":"private-1", "group":"two", "partition":"validation", "input":"PRIVATE_VALIDATION_INPUT",
         "output":"PRIVATE_VALIDATION_OUTPUT", "trace":[{"content":"PRIVATE_VALIDATION_TRACE"}]},
    ], reviewer="PRIVATE_REVIEWER", source={"kind":"recorded","reference":"PRIVATE_SOURCE"})


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.packet=packet();self.path=self.root/'run.packet.json';self.path.write_text(json.dumps(self.packet))
    def tearDown(self): self.temp.cleanup()

    def test_catalog_and_ui_are_minimized(self):
        store=PacketStore(self.root)
        catalog=store.list_review_packets()
        self.assertEqual(catalog['packets'][0]['tuning_trace_count'],1)
        summary,meta=store.open_review(self.packet['sha256'])
        for sentinel in ('PRIVATE_','visible tuning','<img'):
            self.assertNotIn(sentinel,json.dumps(summary))
        self.assertNotIn('PRIVATE_',json.dumps(meta));self.assertIn('visible tuning',json.dumps(meta))
        self.assertFalse(summary['approval'])

    def test_explicit_paths_only_and_snapshot_copy(self):
        store=PacketStore(packets=(self.path,))
        self.path.unlink()
        _,meta=store.open_review(self.packet['sha256'])
        meta['codex-eval-lab/review']['packet']['traces'][0]['trace'][0]['content']='MUTATED'
        self.assertIn('visible tuning',json.dumps(store.open_review(self.packet['sha256'])))
        with self.assertRaises(LabError):store.open_review(str(self.path))
        with self.assertRaises(LabError):store.open_review('../../private')

    def test_root_does_not_recurse_or_read_unrelated_json(self):
        (self.root/'unrelated.json').write_text('invalid secret file')
        folder=self.root/'nested';folder.mkdir();(folder/'other.packet.json').write_text('invalid')
        self.assertEqual(len(PacketStore(self.root).list_review_packets()['packets']),1)

    def test_path_scope_and_symlinks(self):
        with tempfile.TemporaryDirectory() as outside:
            path=Path(outside)/'packet.json';path.write_text(json.dumps(self.packet))
            with self.assertRaises(LabError):PacketStore(self.root,packets=(path,))
            (self.root/'link.packet.json').symlink_to(path)
            with self.assertRaises(LabError):PacketStore(self.root)

    def test_tampered_packet_is_rejected(self):
        self.packet['traces'][0]['output']='tampered';self.path.write_text(json.dumps(self.packet))
        with self.assertRaises(LabError):PacketStore(self.root)

    def test_standalone_is_offline_and_escaped(self):
        result=render_standalone_review(self.packet)
        self.assertNotIn('PRIVATE_',result)
        self.assertNotIn('</script><script>window.PWNED',result)
        self.assertIn('\\u003c/script\\u003e',result)
        self.assertIn('Content-Security-Policy',result)
        self.assertIn("connect-src &#x27;none&#x27;",result)
        self.assertIn('annotation_draft',result)
        self.assertNotIn('app.connect(',result)
        out=self.root/'review.html';write_standalone_review(self.packet,out)
        with self.assertRaises(LabError):write_standalone_review(self.packet,out)

    def test_mcp_resource_contains_no_packet(self):
        result=render_mcp_review()
        self.assertNotIn('PRIVATE_',result);self.assertNotIn(self.packet['sha256'],result)
        self.assertNotIn('<script src=',result)
        self.assertIn('sha256-',result)

    def test_aggregate_projection_never_promotes_unverified_readiness(self):
        from codex_eval_lab.calibration import calibrate
        from tests.review_helpers import review_fixture,calibration_args
        report=calibrate(**calibration_args(review_fixture()))
        report['ready']=True;report['readiness_eligible']=True;report['threshold_basis']='lower_bound'
        report['criteria']['grounded']['validation']['disagreements']=[{'reason':'PRIVATE_REASON'}]
        summary=calibration_summary(report)
        self.assertFalse(summary['ready']);self.assertTrue(summary['reported_ready'])
        self.assertNotIn('PRIVATE_REASON',json.dumps(summary))
        self.assertIn('bounds',summary['criteria']['grounded']['validation'])
        report['criteria']['grounded']['validation']['failure_recall']=1.1
        with self.assertRaises(LabError):calibration_summary(report)

    def test_optional_dependency_not_required_for_core_check(self):
        result=subprocess.run([sys.executable,'-m','codex_eval_lab.plugin_server','--packet',str(self.path),'--check'],capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(ROOT/'src')},timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['packets'][0]['packet_id'],self.packet['sha256'])


@unittest.skipUnless(importlib.util.find_spec('mcp'),'optional mcp SDK not installed')
class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_modern_client_dispatch_preserves_tool_contract(self):
        from mcp import Client, StdioServerParameters
        params=StdioServerParameters(command=sys.executable,args=["-m","codex_eval_lab.plugin_server"],env={"PYTHONPATH":str(ROOT/"src")})
        async with Client(params) as client:
            self.assertIn("io.modelcontextprotocol/ui",client.server_capabilities.extensions)
            tools=(await client.list_tools()).tools
            self.assertEqual({tool.name for tool in tools},{'list_review_packets','open_review','get_calibration_summary'})
            result=await client.call_tool('list_review_packets',{})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content['packets'],[])
            entrypoint=await client.call_tool('open_review',{})
            self.assertFalse(entrypoint.is_error)
            self.assertEqual(entrypoint.meta['codex-eval-lab/review']['catalog'],[])
            denied=await client.call_tool('open_review',{'packet_id':'a'*64,'include_private':True})
            self.assertTrue(denied.is_error)
            resource=await client.read_resource(RESOURCE_URI)
            self.assertEqual(resource.contents[0].meta['ui']['csp']['connectDomains'],[])

    async def test_stdio_protocol_read_only_and_resource_metadata(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'packet.json';p=packet();path.write_text(json.dumps(p))
            params=StdioServerParameters(command=sys.executable,args=['-m','codex_eval_lab.plugin_server','--packet',str(path)],env={'PYTHONPATH':str(ROOT/'src')})
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    # Legacy handshake clients discover UI via the tool metadata;
                    # extension capability negotiation is tested on modern Client.
                    tools=(await session.list_tools()).tools
                    self.assertEqual({t.name for t in tools},{'list_review_packets','open_review','get_calibration_summary'})
                    for tool in tools:self.assertTrue(tool.annotations.read_only_hint);self.assertFalse(tool.annotations.open_world_hint)
                    entry_tool=next(tool for tool in tools if tool.name=='open_review')
                    self.assertEqual(entry_tool.title,'Trace Review')
                    self.assertEqual(entry_tool.input_schema['required'],[])
                    self.assertEqual(entry_tool.meta['ui']['resourceUri'],RESOURCE_URI)
                    entrypoint=await session.call_tool('open_review',{})
                    self.assertFalse(entrypoint.is_error)
                    self.assertEqual(entrypoint.structured_content['packet_count'],1)
                    self.assertIsNone(entrypoint.meta['codex-eval-lab/review']['packet'])
                    self.assertNotIn('visible tuning',json.dumps(entrypoint.meta))
                    catalog=await session.call_tool('list_review_packets',{})
                    self.assertEqual(catalog.structured_content['packets'][0]['packet_id'],p['sha256'])
                    result=await session.call_tool('open_review',{'packet_id':p['sha256']})
                    self.assertFalse(result.is_error)
                    self.assertNotIn('PRIVATE_',result.model_dump_json())
                    self.assertIn('visible tuning',json.dumps(result.meta))
                    self.assertNotIn('visible tuning',json.dumps(result.structured_content))
                    denied=await session.call_tool('open_review',{'packet_id':p['sha256'],'include_private':True})
                    self.assertTrue(denied.is_error)
                    for value in [[],{},17,True,'../../private','A'*64]:
                        invalid=await session.call_tool('open_review',{'packet_id':value})
                        self.assertTrue(invalid.is_error)
                    denied=await session.call_tool('run_eval',{})
                    self.assertTrue(denied.is_error)
                    resource=await session.read_resource(RESOURCE_URI)
                    self.assertEqual(resource.contents[0].mime_type,'text/html;profile=mcp-app')
                    self.assertEqual(resource.contents[0].meta['ui']['csp']['connectDomains'],[])


class PackageTests(unittest.TestCase):
    def test_relocated_reproducible_plugin(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('plugin_builder',ROOT/'scripts/build_plugin.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as temp:
            one=mod.build(ROOT,Path(temp)/'one');two=mod.build(ROOT,Path(temp)/'two')
            self.assertEqual(one['sha256'],two['sha256'])
            catalog=json.loads((Path(one["catalog"])/".agents/plugins/marketplace.json").read_text())
            self.assertEqual(catalog["plugins"][0]["source"]["path"],"./plugins/codex-eval-lab")
            self.assertEqual(catalog["name"],"codex-eval-lab-local")
            bundled=Path(one['plugin'])
            for name in ['docs/PROTOCOL.md','docs/SECURITY.md','examples/routing/eval.toml','scripts/demo.py','scripts/install_skills.py']:
                self.assertTrue((bundled/name).is_file(),name)
            result=subprocess.run([sys.executable,str(ROOT/'scripts/validate_plugin.py'),one['plugin']],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            with self.assertRaises(ValueError):mod.build(ROOT,Path(temp)/'one')
