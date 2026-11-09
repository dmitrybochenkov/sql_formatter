import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from formatter_modules import formatter_config as c
from formatter_modules.corporate_profile import CORPORATE
from formatter_modules.sqlfluff_config_adapter import build_config, active_rules


class UserConfigurationTests(unittest.TestCase):
    def test_shipped_and_missing_parameters_equal_corporate(self):
        self.assertEqual(c.parse_personal((Path(__file__).resolve().parents[2]/'config_templates'/'personal.example.toml').read_bytes()), CORPORATE)
        self.assertEqual(c.validate({'schema_version': 1}), CORPORATE)

    def test_all_supported_values_are_resolved(self):
        for section, defaults in c.PERSONAL_DEFAULTS.items():
            for key in defaults:
                values = {'case': ['upper','lower','preserve'], 'commas': ['leading','trailing'],
                          'spacing': [[],list(c.CLAUSES)], 'where':[True,False],
                          'group_by':['multiline','inline','preserve']}[section]
                for value in values:
                    with self.subTest(section=section,key=key,value=value):
                        settings=c.validate({'schema_version':1, section:{key:value}})
                        expected=tuple(sorted(value)) if section=='spacing' else value
                        self.assertEqual(settings.get(section,key),expected)

    def test_invalid_types_values_unknown_and_versions(self):
        cases=[{}, {'schema_version':True}, {'schema_version':2}, {'schema_version':'1'},
               {'schema_version':1,'extra':{}}, {'schema_version':1,'case':[]},
               {'schema_version':1,'case':{'extra':'upper'}}]
        for section, defaults in c.PERSONAL_DEFAULTS.items():
            for key in defaults:
                for value in (None, 1, {}, 'unsupported'):
                    cases.append({'schema_version':1,section:{key:value}})
        cases += [{'schema_version':1,'spacing':{'blank_line_before':['where','where']}},
                  {'schema_version':1,'spacing':{'blank_line_before':['over']}}]
        for data in cases:
            with self.subTest(data=data),self.assertRaises(c.ConfigurationError):c.validate(data)

    def test_toml_errors_bom_copy_and_unicode_comments(self):
        for raw in (b'\xff', b'schema_version=1\nschema_version=1',b'[case',b''):
            with self.assertRaises(c.ConfigurationError):c.parse_personal(raw)
        self.assertEqual(c.parse_personal(b'\xef\xbb\xbfschema_version=1\n'),CORPORATE)
        self.assertEqual(c.parse_personal('# настройки\nschema_version=1'.encode()),CORPORATE)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'копия.toml';p.write_bytes((Path(__file__).resolve().parents[2]/'config_templates'/'personal.example.toml').read_bytes())
            with patch.object(c,'personal_path',return_value=p):self.assertEqual(c.load_personal(),CORPORATE)
            p.unlink()
            with patch.object(c,'personal_path',return_value=p):self.assertIsNone(c.load_personal())

    def test_semantic_comparison_normalizes_order(self):
        settings=c.validate({'schema_version':1,'spacing':{'blank_line_before':list(reversed(c.PERSONAL_DEFAULTS['spacing']['blank_line_before']))}})
        self.assertEqual(c.differences(settings,CORPORATE),())
        changed=c.validate({'schema_version':1,'where':{'insert_1_equals_1':False}})
        self.assertEqual(c.differences(changed,CORPORATE),('where.insert_1_equals_1',))
        self.assertNotEqual(changed.fingerprint,CORPORATE.fingerprint)

    def test_independent_corporate_and_immutable_scope(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('file discovery')):
            self.assertEqual(build_config().get('dialect'),'teradata')
        settings=c.validate({'schema_version':1,'case':{'keywords':'lower'}})
        with c.use_settings(settings):
            self.assertEqual(c.current_settings(),settings)
            with c.use_settings(CORPORATE):self.assertEqual(c.current_settings(),CORPORATE)
        self.assertEqual(c.current_settings(),CORPORATE)
        with self.assertRaises(AttributeError):settings.values=()

    def test_cp_rules_exact_mapping_and_preserve_exclusion(self):
        for mode in ('upper','lower','preserve'):
            settings=c.validate({'schema_version':1,'case':dict.fromkeys(c.PERSONAL_DEFAULTS['case'],mode)})
            with c.use_settings(settings):
                self.assertEqual(len(active_rules()),0 if mode=='preserve' else 5)
                config=build_config(case=True)
                self.assertEqual(config.get('templater'),'raw')
                self.assertEqual(config.get('max_line_length'),120)

    def test_proof_cache_namespace_includes_effective_policy(self):
        from formatter_modules.formatter_request import request_scope, proof_memo
        calls=[]
        @proof_memo()
        def value(source):
            calls.append(c.current_settings().fingerprint)
            return c.current_settings().get('case','keywords')
        @request_scope
        def run():
            self.assertEqual(value('x'),'upper')
            with c.use_settings(c.validate({'schema_version':1,'case':{'keywords':'lower'}})):
                self.assertEqual(value('x'),'lower')
            self.assertEqual(value('x'),'upper')
        run();self.assertEqual(len(calls),2)
