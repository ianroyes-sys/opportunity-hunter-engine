"""Isolated, offline state-machine tests: no browser, network or live pipeline."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import opportunity_engine as engine


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='opportunity-engine-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'hunter'
        self.omega = Path(self.temp.name) / 'omega'
        (self.root / 'pipeline/opportunities').mkdir(parents=True)
        self.write('CATEGORIES.json', {'categories': {'summits': {'enabled': True, 'keywords': ['summit']}}})

    def write(self, name, data):
        path = self.root / 'pipeline' / name
        path.write_text(json.dumps(data))
        return path

    def candidate(self, name='trip', state='vetted', extra='', style='bullet'):
        key = 'https://example.org/trips/' + name + '|2026'
        prefix = '- ' if style == 'bullet' else ''
        label = '**Status:**' if style == 'bold' else 'Status:'
        (self.root / 'pipeline/opportunities' / (name + '.md')).write_text(
            f'# {name}\n- Candidate key: {key}\n- Source: https://example.org/trips/{name}\n'
            f'{prefix}{label} {state}\n- Category: summit\n{extra}')
        return key

    def state(self):
        return engine.snapshot(self.root, self.omega)

    def outcome(self, key, state, **kwargs):
        values = dict(key=key, state=state, reason='', evidence='', confirmation='', user_request='', retry_minutes=0)
        values.update(kwargs)
        return engine.record(self.root, self.omega, argparse.Namespace(**values))

    def intake(self, **kwargs):
        value = dict(name='Creator trip', sourceUrl='https://example.org/new-trip', category='summit',
                     cycle='2026', eligibility='US adult creators', evidence=[{'url':'https://example.org/new-trip','excerpt':'Travel covered; US adults may apply.'}],
                     openStatus='open', effort='low')
        value.update(kwargs)
        path = Path(self.temp.name) / 'intake.json'
        path.write_text(json.dumps(value))
        return engine.add(self.root, self.omega, path)

    def test_negative_submission_prose_never_becomes_submission(self):
        for text in ('not submitted', 'vetted — not submitted', 'held; application not submitted', 'draft, never applied'):
            with self.subTest(text=text):
                self.assertNotEqual(engine.status(text), 'submitted')
        self.candidate(state='vetted', extra='No application submitted. Submit was not clicked.')
        self.assertEqual(self.state()['counts']['submitted'], 0)

    def test_legacy_plain_and_bold_statuses(self):
        for style in ('bullet', 'plain', 'bold'):
            self.candidate(style, 'submitted', style=style)
        self.assertEqual(self.state()['counts']['submitted'], 3)

    def test_legacy_tracker_submission_outranks_record_and_outcome(self):
        key = self.candidate(state='vetted')
        (self.root / 'pipeline/tracker.md').write_text('| trip | summit | unknown | x | x | **submitted** | [record](opportunities/trip.md) |\n')
        self.write('ENGINE-OUTCOMES.json', {'records': {key: {'state':'verified'}}})
        self.assertEqual(self.state()['candidates'][0]['state'], 'submitted')
        with self.assertRaises(ValueError):
            self.outcome(key, 'needs-browser')

    def test_prior_ledger_match_requires_reconciliation_not_submit_replay(self):
        self.candidate()
        (self.root / 'pipeline/SUBMISSIONS.md').write_text('| 2026-09-09 | trip | x | y | z | https://example.org/trips/trip |\n')
        self.assertEqual(self.state()['counts']['reconcile'],1)
        self.assertEqual(self.state()['counts']['actionable'],0)

    def test_skip_survives_expired_deferral_and_reintake(self):
        key = self.candidate()
        self.write('USER-SKIPS.json', {'candidates':[{'keys':[key], 'reason':'User explicitly skipped'}]})
        self.write('APPLICATION-DEFERRALS.json', {'records':{key:{'reason':'no-progress','retryAt':'2000-01-01T00:00:00Z'}}})
        result=self.intake(sourceUrl='http://www.example.org/trips/trip/?utm_source=ig')
        self.assertFalse(result['added'])
        self.assertEqual(self.state()['counts']['skipped'],1)
        with self.assertRaises(ValueError):
            self.outcome(key,'needs-browser')

    def test_url_normalization_preserves_role_query_and_cycle(self):
        self.assertEqual(engine.canonical('http://www.Example.org/role/?b=2&utm_source=x&a=1#top|2026'),
                         'https://example.org/role?a=1&b=2|2026')
        self.assertNotEqual(engine.canonical('https://example.org/role|2026'),engine.canonical('https://example.org/role|2027'))
        self.assertNotEqual(engine.url_key('https://example.org/apply?job=1'),engine.url_key('https://example.org/apply?job=2'))

    def test_same_cycle_duplicate_does_not_add(self):
        self.assertTrue(self.intake()['added'])
        self.assertFalse(self.intake(sourceUrl='http://www.example.org/new-trip/?utm_medium=social')['added'])

    def test_malformed_json_policy_fails_closed_without_overwrite(self):
        file=self.root/'pipeline/USER-SKIPS.json'
        file.write_text('{broken')
        with self.assertRaises(ValueError):
            engine.prepare(self.root,self.omega,'opportunity')
        self.assertEqual(file.read_text(),'{broken')
        self.assertFalse((self.root/'pipeline/ENGINE-STATE.json').exists())

    def test_invalid_nested_category_policy_fails_closed(self):
        self.candidate()
        self.write('CATEGORIES.json',{'categories':{'summits':'invalid'}})
        with self.assertRaises(ValueError):
            self.state()

    def test_submission_requires_existing_image_and_confirmation(self):
        key=self.candidate()
        for values in ({}, {'evidence':'missing.png','confirmation':'Application received'}):
            with self.assertRaises(ValueError):
                self.outcome(key,'submitted',**values)
        evidence=self.root/'proof.txt'; evidence.write_text('Application received')
        with self.assertRaises(ValueError):
            self.outcome(key,'submitted',evidence=str(evidence),confirmation='Application received')
        image=self.root/'proof.png'; image.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        with self.assertRaises(ValueError):
            self.outcome(key,'submitted',evidence=str(image))
        result=self.outcome(key,'submitted',evidence=str(image),confirmation='Application received')
        self.assertEqual(result['counts']['submitted'],1)
        self.assertEqual(result['counts']['actionable'],0)

    def test_user_fact_deferral_does_not_expire(self):
        key=self.candidate()
        self.write('APPLICATION-DEFERRALS.json',{'records':{key:{'reason':'user-action','detail':'Missing emergency contact','retryAt':'2000-01-01T00:00:00Z'}}})
        self.assertEqual(self.state()['candidates'][0]['state'],'deferred')
        self.assertIsNone(self.state()['candidates'][0].get('retryAt'))

    def test_personal_wall_requires_user_request_and_evidence_to_release(self):
        key=self.candidate()
        self.write('APPLICATION-DEFERRALS.json',{'records':{key:{'reason':'user-action','detail':'Missing emergency contact'}}})
        self.outcome(key,'needs-browser',reason='Retry ordinary queue')
        self.assertEqual(self.state()['candidates'][0]['state'],'deferred')
        evidence=self.root/'new-answer.txt'
        evidence.write_text('Fixture user supplied the previously missing required answer.')
        self.outcome(key,'needs-browser',reason='Answer now supplied',evidence=str(evidence))
        self.assertEqual(self.state()['candidates'][0]['state'],'deferred')
        packet=self.outcome(key,'needs-browser',reason='Answer supplied explicitly',
                            user_request='User supplied the missing answer and asked to resume',evidence=str(evidence))
        self.assertEqual(packet['counts']['actionable'],1)
        self.assertEqual(self.state()['candidates'][0]['state'],'needs-browser')

    def test_followup_packet_limits_recent_submissions_and_omits_ledger_prose(self):
        for n in range(30):
            self.candidate(f'submitted-{n}',state='submitted')
        (self.root/'pipeline/SUBMISSIONS.md').write_text('UNRELATED FULL LEDGER NARRATION\n'*10000)
        packet=engine.prepare(self.root,self.omega,'opportunity-followup')
        self.assertEqual(packet['counts']['submitted'],30)
        self.assertGreater(len(packet['recentSubmitted']),0)
        self.assertLessEqual(len(packet['recentSubmitted']),12)
        self.assertNotIn('UNRELATED FULL LEDGER NARRATION',json.dumps(packet))
        self.assertLess(len(json.dumps(packet)),25000)

    def test_old_technical_override_cannot_reopen_personal_fact_wall(self):
        key=self.candidate()
        self.write('ENGINE-OUTCOMES.json',{'records':{key:{'state':'deferred','retryAt':'2000-01-01T00:00:00Z'}}})
        self.write('APPLICATION-DEFERRALS.json',{'records':{key:{'reason':'manual-heavy','detail':'Needs personal video'}}})
        self.assertEqual(self.state()['candidates'][0]['state'],'deferred')

    def test_technical_retry_becomes_due(self):
        key=self.candidate()
        self.write('ENGINE-OUTCOMES.json',{'records':{key:{'state':'deferred','reason':'Temporary browser outage','retryAt':'2000-01-01T00:00:00Z'}}})
        self.assertEqual(self.state()['candidates'][0]['state'],'needs-browser')

    def test_active_recovery_cooldown_outranks_expired_technical_override(self):
        key=self.candidate()
        self.write('ENGINE-OUTCOMES.json',{'records':{key:{'state':'deferred','reason':'Old outage','retryAt':'2000-01-01T00:00:00Z'}}})
        recovery=self.omega/'loops/state/opportunity.recovery.json'
        recovery.parent.mkdir(parents=True)
        recovery.write_text(json.dumps({'candidateCooldowns':{key:{'until':4102444800,'milestone':'form-page-2'}}}))
        self.assertEqual(self.state()['candidates'][0]['state'],'deferred')

    def test_submit_started_is_reconciliation_not_new_application(self):
        key=self.candidate()
        self.outcome(key,'unverified',reason='Submit clicked; confirmation response lost')
        packet=engine.prepare(self.root,self.omega,'opportunity')
        self.assertEqual(packet['counts']['reconcile'],0)
        self.assertEqual(packet['counts']['deferred'],1)
        self.assertEqual(packet['counts']['actionable'],0)
        self.assertEqual(packet['candidates'],[])
        self.assertEqual(self.state()['candidates'][0]['state'],'unverified')
        data=json.loads((self.root/'pipeline/ENGINE-OUTCOMES.json').read_text())
        data['records'][key]['retryAt']='2000-01-01T00:00:00Z'
        self.write('ENGINE-OUTCOMES.json',data)
        packet=engine.prepare(self.root,self.omega,'opportunity')
        self.assertEqual(packet['counts']['reconcile'],1)
        self.assertEqual(packet['counts']['actionable'],0)
        self.assertEqual(packet['candidates'][0]['state'],'unverified')

    def test_uncertain_submission_requires_proof_before_reopening(self):
        key=self.candidate()
        self.outcome(key,'unverified',reason='Submit clicked; confirmation response lost')
        with self.assertRaises(ValueError):
            self.outcome(key,'needs-browser',reason='Assume not sent')
        evidence=self.root/'portal.txt'; evidence.write_text('Portal shows draft, no submitted application.')
        with self.assertRaises(ValueError):
            self.outcome(key,'needs-browser',evidence=str(evidence))
        packet=self.outcome(key,'needs-browser',evidence=str(evidence),confirmation='Portal confirms draft only; submit did not complete')
        self.assertEqual(packet['counts']['actionable'],1)

    def test_intake_bounds_strings_and_evidence(self):
        for values in ({'name':'x'*2001},{'effort':'high'}, {'evidence':[{'url':'https://example.org','excerpt':'x'*1501}]}, {'evidence':[{'url':'https://example.org','excerpt':'short'}]*9}):
            with self.subTest(values=list(values)), self.assertRaises(ValueError):
                self.intake(**values)

    def test_personal_fact_outcome_cannot_set_technical_retry(self):
        key=self.candidate()
        with self.assertRaises(ValueError):
            self.outcome(key,'deferred',reason='Missing personal emergency contact',retry_minutes=60)

    def test_unknown_key_cannot_be_written_as_submission(self):
        with self.assertRaises(ValueError):
            self.outcome('https://example.org/unknown|2026','submitted')
        self.assertFalse((self.root/'pipeline/ENGINE-OUTCOMES.json').exists())

    def test_uncertain_submission_cannot_be_hidden_by_skip(self):
        key=self.candidate()
        self.outcome(key,'unverified',reason='Submission response lost')
        with self.assertRaises(ValueError):
            self.outcome(key,'skipped',user_request='Skip this candidate')
        self.assertEqual(self.state()['candidates'][0]['state'],'unverified')

    def test_durable_submission_uncertainty_outlives_cooldown_and_old_override(self):
        key=self.candidate()
        recovery=self.omega/'loops/state/opportunity.recovery.json'
        recovery.parent.mkdir(parents=True)
        recovery.write_text(json.dumps({'candidateCooldowns':{},'uncertainSubmissions':{key:{'at':100000,'reason':'Interrupted after submit','evidence':'pre-submit.png'}}}))
        self.write('ENGINE-OUTCOMES.json',{'records':{key:{'state':'verified','updatedAt':'1970-01-01T00:00:01Z','evidence':'old.txt','confirmation':'Earlier verification'}}})
        packet=engine.prepare(self.root,self.omega,'opportunity')
        self.assertEqual(packet['counts']['actionable'],0)
        self.assertEqual(packet['counts']['reconcile'],1)
        self.assertEqual(packet['candidates'][0]['state'],'unverified')
        evidence=self.root/'new-portal-check.txt'
        evidence.write_text('Current portal confirms application remains draft, not submitted.')
        packet=self.outcome(key,'needs-browser',evidence=str(evidence),confirmation='Current portal confirms no submitted application')
        self.assertEqual(packet['counts']['actionable'],1)
        self.assertEqual(packet['counts']['reconcile'],0)

    def test_empty_and_pending_answer_packet_counts(self):
        packet=engine.prepare(self.root,self.omega,'opportunity')
        self.assertEqual(packet['counts']['actionable'],0)
        self.assertEqual(packet['pendingAnswers'],0)
        answers=self.omega/'loops/answers/opportunity.jsonl'
        answers.parent.mkdir(parents=True)
        answers.write_text('{"answer":"Skip trip"}\n\n')
        self.assertEqual(engine.prepare(self.root,self.omega,'opportunity')['pendingAnswers'],1)

    def test_intake_rejects_missing_qualification_and_invalid_source(self):
        for values in ({'eligibility':''},{'evidence':[]},{'openStatus':'closed'},{'sourceUrl':'file:///tmp/application'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.intake(**values)
        self.assertEqual(self.state()['counts']['actionable'],0)

    def test_disabled_category_cannot_enter_action_queue(self):
        self.candidate()
        self.write('CATEGORIES.json',{'categories':{'summits':{'enabled':False,'keywords':['summit']}}})
        self.assertEqual(self.state()['counts']['outOfScope'],1)
        self.assertEqual(self.state()['counts']['actionable'],0)

    def test_packet_drops_historical_narration_and_limits_selected_records(self):
        for n in range(30):
            self.candidate(f'trip-{n}')
        (self.root/'pipeline/HUNT-INBOX.md').write_text('Historical unrelated audit.\n'*100000)
        packet=engine.prepare(self.root,self.omega,'opportunity')
        self.assertEqual(packet['counts']['actionable'],30)
        self.assertLessEqual(len(packet['candidates']),8)
        self.assertLess(len(json.dumps(packet)),20000)
        self.assertNotIn('Historical unrelated audit',json.dumps(packet))


if __name__=='__main__':
    unittest.main()
