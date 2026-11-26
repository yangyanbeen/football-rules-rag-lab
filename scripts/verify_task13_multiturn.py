"""Regression checks for conversation input, query rewriting, and worker validation."""

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from answer_eval_core import REFUSAL, canonical, config, digest
from citation_catalog_guard import safe_render
import task13_audit_client as client
from task13_core import local_corpus
from task13_history_actions import history_action, transform_previous_answer
from task13_query_rewrite import MAX_HISTORY_BYTES, bounded_history, read_history, resolve_question


FOLLOWUP = '宽和高分别是多少？'
STANDALONE = '足球球门开口的宽和高分别是多少？'
PREVIOUS = [('请说明足球球门的尺寸。', '球门宽7.32米，高2.44米。')]


class ConversationTests(unittest.TestCase):
    def test_intent_route_leaves_new_questions_to_retrieval(self):
        self.assertEqual('table', history_action('请把刚才的答案整理成表格。'))
        self.assertEqual('points', history_action('把上一轮回答列成要点'))
        self.assertEqual('sources', history_action('刚才的答案引用了哪些来源？'))
        self.assertEqual('unsupported', history_action('把刚才的回答翻译成英文'))
        self.assertIsNone(history_action('把越位规则整理成表格'))
        self.assertIsNone(history_action('上一条回答里所说的球门有多高？'))

    def test_previous_answer_formats_reuse_only_verified_evidence(self):
        corpus = local_corpus()
        answer, citations = safe_render(['L01-03'], corpus)
        with patch('task13_history_actions.local_corpus', return_value=corpus):
            result = transform_previous_answer('table', [(STANDALONE, answer)])
            self.assertEqual('answered', result['status'])
            self.assertEqual(citations, result['citations'])
            self.assertIn('| L01-03 |', result['answer'])
            self.assertIn('2.44', result['answer'])
            points = transform_previous_answer('points', [('整理成表格', result['answer'])])
            self.assertEqual(citations, points['citations'])
            sources = transform_previous_answer('sources', [('列成要点', points['answer'])])
            self.assertEqual(citations, sources['citations'])
            self.assertIn(citations[0]['source_url'], sources['answer'])
            for history in ([], [(STANDALONE, answer.replace('2.44', '24.4', 1))],
                            [(STANDALONE, answer), ('别的问题', REFUSAL)]):
                self.assertEqual('no_previous_evidence', transform_previous_answer('table', history)['status'])

    def test_followups_skip_formatting_turns_and_stop_at_the_new_topic(self):
        order = [*PREVIOUS, ('换个话题，越位位置是什么？', '新话题证据'),
                 ('整理成表格', '表格'), ('列出来源', '来源')]
        self.assertEqual([['换个话题，越位位置是什么？', '新话题证据']], bounded_history(order))

    def test_only_completed_recent_turns_enter_private_request(self):
        turns = bounded_history([('早期问题', '早期回答'), ('体育规则'*200, '正文'*700),
                                 ('这份知识库有球门尺寸吗？', REFUSAL), ('未完成', None)])
        self.assertEqual(2, len(turns))
        self.assertLessEqual(len(turns[0][0].encode()), 600)
        self.assertLessEqual(len(turns[0][1].encode()), 900)
        self.assertEqual('', turns[1][1])
        self.assertEqual(turns, read_history(io.BytesIO(canonical(turns))))
        for data in (canonical([{'question':'示例'}]), b'x'*(MAX_HISTORY_BYTES + 1)):
            with self.assertRaises(ValueError):
                read_history(io.BytesIO(data))

    def test_rewritten_query_and_model_failure(self):
        turns = bounded_history(PREVIOUS)
        with patch('answer_json_chat.generate') as generate:
            generate.return_value = {'message': {'content': json.dumps({'subject': '足球球门开口'})}}
            question, info = resolve_question(FOLLOWUP, turns, config())
            self.assertEqual(('足球球门开口：' + FOLLOWUP, 'rewritten'), (question, info['outcome']))
            messages = generate.call_args.args[1]
            self.assertEqual({'history': turns, 'question': FOLLOWUP}, json.loads(messages[-1]['content']))
            generate.side_effect = TimeoutError('model unavailable')
            question, info = resolve_question(FOLLOWUP, turns, config())
            self.assertEqual((FOLLOWUP, 'fallback', 'TimeoutError'), (question, info['outcome'], info['error']))

    def test_original_version_refusal_policy_is_preserved(self):
        question = '请核实2026/27赛季IFAB官方规则的现行有效性。'
        with patch('answer_json_chat.generate') as generate:
            query, info = resolve_question(question, bounded_history(PREVIOUS), config())
        generate.assert_not_called()
        self.assertEqual((question, 'unchanged'), (query, info['outcome']))

    def test_unresolved_pronoun_is_retried_before_retrieval(self):
        question = '那它的高度呢？'
        rewritten = '足球球门开口的高度呢？'
        unchanged_reply = {'message': {'content': json.dumps({'subject': None})}}
        rewritten_reply = {'message': {'content': json.dumps({'subject': '足球球门开口'})}}
        with patch('answer_json_chat.generate', side_effect=[unchanged_reply, rewritten_reply]) as generate:
            query, info = resolve_question(question, bounded_history(PREVIOUS), config())
        self.assertEqual(2, generate.call_count)
        self.assertEqual((rewritten, 'rewritten'), (query, info['outcome']))

    def test_refusal_keeps_subject_without_treating_refusal_as_evidence(self):
        history = bounded_history([('人工草坪的颜色有什么限制？', REFUSAL)])
        with patch('answer_json_chat.generate') as generate:
            query, info = resolve_question('那它的表面通常是什么？', history, config())
        self.assertEqual('人工草坪的表面通常是什么？', query)
        self.assertEqual('rewritten', info['outcome'])
        generate.assert_not_called()

    def test_refused_followup_chain_walks_back_to_explicit_subject(self):
        history = bounded_history([
            ('人工草坪的颜色有什么限制？', REFUSAL),
            ('那它的表面通常是什么？', REFUSAL),
        ])
        with patch('answer_json_chat.generate') as generate:
            query, info = resolve_question('那它的材质通常是什么？', history, config())
        self.assertEqual('人工草坪的材质通常是什么？', query)
        self.assertEqual('rewritten', info['outcome'])
        generate.assert_not_called()

    def test_topic_change_preserves_the_new_question(self):
        question = '普通场上队员能否戴手套？'
        turns = bounded_history(PREVIOUS)
        with patch('answer_json_chat.generate') as generate:
            generate.return_value = {'message': {'content': json.dumps({'subject': None})}}
            query, info = resolve_question(question, turns, config())
            self.assertEqual((question, 'unchanged'), (query, info['outcome']))
            generate.reset_mock()
            explicit = '换个话题，' + question
            query, info = resolve_question(explicit, turns, config())
        generate.assert_not_called()
        self.assertEqual((explicit, 'unchanged'), (query, info['outcome']))

    def test_worker_gets_bounded_history_on_stdin_and_validates_effective_query(self):
        ref = {'path': 'worker.json'}
        packet = {'status': 'answered', 'trace_id': 'trace', 'private_trace': ref}
        result = {'status': 'answered', 'trace_id': 'trace', 'question': STANDALONE, 'error': None,
                  'query_resolution': {'original_question_sha256': digest(FOLLOWUP.encode()), 'history_turns': 1,
                                       'outcome': 'rewritten', 'seconds': 0.1, 'error': None}}
        process = SimpleNamespace(returncode=0, stdout=json.dumps(packet), stderr='')
        with (patch.object(client.subprocess, 'run', return_value=process) as run,
              patch.object(client, 'read', return_value=result), patch.object(client, 'record', return_value=ref),
              patch.object(client, 'validate_private') as validate, patch.object(client, 'write_new') as failure):
            self.assertIs(result, client.call_worker(FOLLOWUP, history=PREVIOUS)[0])
            command = run.call_args.args[0]
            self.assertIn('--history-stdin', command)
            self.assertNotIn(PREVIOUS[0][0], ' '.join(command))
            self.assertEqual(bounded_history(PREVIOUS), json.loads(run.call_args.kwargs['input']))
            validate.assert_called_once_with(result, STANDALONE, True)

            result['query_resolution']['history_turns'] = 2
            with self.assertRaises(RuntimeError):
                client.call_worker(FOLLOWUP, history=PREVIOUS)
            self.assertEqual('invalid_worker_packet', failure.call_args.args[1]['kind'])

            del result['query_resolution']
            client.call_worker(STANDALONE)
            self.assertNotIn('--history-stdin', run.call_args.args[0])
            self.assertNotIn('input', run.call_args.kwargs)
            validate.assert_called_with(result, STANDALONE, True)


if __name__ == '__main__':
    unittest.main()
