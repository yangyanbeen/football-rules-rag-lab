"""Regression checks for conversation input, query rewriting, and worker validation."""

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from answer_eval_core import REFUSAL, canonical, config, digest
import task13_audit_client as client
from task13_query_rewrite import MAX_HISTORY_BYTES, bounded_history, read_history, resolve_question


FOLLOWUP = '宽和高分别是多少？'
STANDALONE = '足球球门开口的宽和高分别是多少？'
PREVIOUS = [('请说明足球球门的尺寸。', '球门宽7.32米，高2.44米。')]


class ConversationTests(unittest.TestCase):
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
            generate.return_value = {'message': {'content': json.dumps({'query': STANDALONE})}}
            question, info = resolve_question(FOLLOWUP, turns, config())
            self.assertEqual((STANDALONE, 'rewritten'), (question, info['outcome']))
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
        rewritten = '足球球门开口的高度是多少？'
        unchanged_reply = {'message': {'content': json.dumps({'query': question})}}
        rewritten_reply = {'message': {'content': json.dumps({'query': rewritten})}}
        with patch('answer_json_chat.generate', side_effect=[unchanged_reply, rewritten_reply]) as generate:
            query, info = resolve_question(question, bounded_history(PREVIOUS), config())
        self.assertEqual(2, generate.call_count)
        self.assertEqual((rewritten, 'rewritten'), (query, info['outcome']))

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
