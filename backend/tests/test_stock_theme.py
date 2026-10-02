"""Fixed selection, classified instruments and preserved cross-market execution gates."""

import json
from copy import deepcopy
from decimal import Decimal as D

import pytest
from test_global import SOURCE, data
from test_paper import NOW, command
from test_paper import service as service
from test_strategies import register

from app.paper import domain
from app.paper.contracts import Proposal, Settings
from app.paper.global_account import combine
from app.paper.investment_universe import INDEX_INVERSES
from app.paper.strategies.contracts import Draft

STOCKS = ['KR:005930', 'KR:000660', 'US:NVDA', 'US:AVGO', 'US:AMD']
INVERSES = ['US:SH', 'US:PSQ']


def snapshot(now, kr=True, us=True):
    value = data(now, kr, us)
    for key in INDEX_INVERSES:
        market, raw = key.split(':')
        native = value['markets'][market]
        source = '114800' if market == 'KR' else 'SH'
        for field in ('quotes', 'minute', 'daily', 'securities'):
            native[field][raw] = deepcopy(native[field][source])
        native['securities'][raw].update(symbol=raw, securityType='ETF', leverageFactor='-1')
    return combine(value['markets'], now, value['fx'])


def proposal(service, now=NOW, existing=False, kr=True):
    if not existing:
        command(service, 'new', settings=Settings(market='GLOBAL', capital='10000000',
                                                 source='demo', mode='adaptive'))
        command(service, 'start')
    service.tick(now, snapshot(now, kr=kr))
    register(service, Draft(strategy_id='test-seven', version=1, protocol_version=5,
                           parent_ref='cash-v1@1', name='Seven slots', source=SOURCE,
                           hypothesis='Five stocks and two index inverse slots.',
                           failure_criterion='Wrong class, cash or execution gates.'))
    state = service.store.current()['session']
    service.claim('seven-run', now, *('Fixture migrated-account review', state['id'],
                                    state['policyVersion']) if existing else ())
    manifest = json.loads((service.exchange / 'latest.json').read_text())

    def candidate(key, evidence):
        market, symbol = key.split(':')
        return dict(market=market, symbol=symbol, name=symbol, rationale='Synthetic fixture.',
                    evidence_ids=[evidence])

    value = dict(schema_version=8, proposal_id='seven-plan', run_id='seven-run',
                 session_id=state['id'], snapshot_id=manifest['snapshot_id'], market='GLOBAL',
                 base_policy_version=state['policyVersion'], as_of=now, valid_from=now,
                 expires_at=now+3600000,
                 playbook_id='test-seven', strategy_version=1, allowed_symbols=STOCKS,
                 candidate_groups=[dict(group_id=m, name='Individual stocks',
                    candidates=[candidate(k, 'stocks') for k in STOCKS if k.startswith(m)])
                    for m in ('KR', 'US')],
                 inverse_groups=[dict(group_id='themes', name='Index inverses',
                    candidates=[candidate(k, k.replace(':', '-')) for k in INVERSES])],
                 hypothesis='Seven slots, flexible targets.', counterevidence='No return evidence.',
                 rationale='Synthetic test only.', evidence=[dict(evidence_id=e, source_url=url,
                    publisher='Fixture', published_at=now-1000, retrieved_at=now,
                    claim='Fixture only.', excerpt='', uncertainty='Not market evidence.')
                    for e, url in [('stocks', 'https://example.com/stocks'),
                        *[(k.replace(':', '-'), INDEX_INVERSES[k]['source_url'])
                          for k in INVERSES]]],
                 portfolio=dict(mode='adaptive', target_weights={
                    **{k:'0.08' for k in STOCKS}, **{k:'0.05' for k in INVERSES}, 'CASH':'0.5'},
                    retirements=[]))
    return value


def test_fixed_seven_and_fee_cash_conservation(service):
    value = proposal(service)
    assert service.submit(value, 'seven-plan', NOW)['status'] == 'accepted'
    service.export(NOW+1000)
    manifest = json.loads((service.exchange/'latest.json').read_text())
    exported = json.loads((service.exchange/'exports'/manifest['snapshot_id']/
                           'context.json').read_text())
    selection = exported['instructions']['candidate_selection']
    assert selection['required_symbols'] == 5
    assert selection['required_index_inverses'] == 2
    assert 'theme/sector inverses' in selection['standing_rules']
    for offset in (30000, 60000):
        service.tick(NOW+offset, snapshot(NOW+offset))
    state = service.store.current()['session']
    assert set(domain.candidate_symbols(state)) == set(STOCKS+INVERSES)
    assert set(domain.standing_symbols(state)) == set(INVERSES)
    assert len(state['positions']) == 7 and len(state['fills']) == 7
    assert all(D(x) >= 0 for x in state['cashBalances'].values())
    assert D(state['cash']) + sum(D(p['entryCost']) for p in state['positions']) == D(
        state['baseline'])
    before = deepcopy(state['fills'])
    service.tick(NOW+90000, snapshot(NOW+90000))
    assert service.store.current()['session']['fills'] == before


@pytest.mark.parametrize('mutation', ['four_stocks', 'one_inverse', 'theme_inverse', 'duplicate'])
def test_wrong_counts_or_theme_inverse_rejected(service, mutation):
    value = proposal(service)
    if mutation == 'four_stocks':
        value['candidate_groups'][0]['candidates'].pop()
    elif mutation == 'one_inverse':
        value['inverse_groups'][0]['candidates'].pop()
    elif mutation == 'theme_inverse':
        value['inverse_groups'][0]['candidates'][0]['symbol'] = 'SEF'
    else:
        value['inverse_groups'][0]['candidates'][1] = deepcopy(
            value['inverse_groups'][0]['candidates'][0])
    with pytest.raises(ValueError):
        Proposal.model_validate(value)


@pytest.mark.parametrize('failure', ['gold_stock', 'wrong_factor', 'missing_issuer'])
def test_instrument_and_source_admission(service, failure):
    value = proposal(service)
    if failure != 'missing_issuer':
        with service.store.transaction():
            bundle = service.store.current()
            securities = bundle['session']['latest']['securities']
            if failure == 'gold_stock':
                securities['KR:005930']['securityType'] = 'ETF'
            else:
                securities['US:SH']['leverageFactor'] = '-2'
            service.store.save(bundle)
    else:
        value['evidence'][1]['source_url'] = 'https://example.com/unverified'
    assert service.submit(value, 'seven-plan', NOW)['status'] == 'rejected'


def test_closed_us_index_inverses_do_not_fill(service):
    value = proposal(service)
    assert service.submit(value, 'seven-plan', NOW)['status'] == 'accepted'
    for offset in (30000, 60000):
        service.tick(NOW+offset, snapshot(NOW+offset, us=False))
    state = service.store.current()['session']
    assert state['fills'] and all(f['market'] == 'KR' for f in state['fills'])
    assert set(domain.standing_symbols(state)) == set(INVERSES)
    assert state['candidateChecks']['US:SH'] == 'market_closed'


def test_changed_inverse_factor_blocks_execution(service):
    value = proposal(service)
    assert service.submit(value, 'seven-plan', NOW)['status'] == 'accepted'
    for offset in (30000, 60000):
        broken = snapshot(NOW+offset)
        broken['securities']['US:SH']['leverageFactor'] = '-3'
        service.tick(NOW+offset, broken)
    state = service.store.current()['session']
    assert not state['fills']
    assert state['candidateChecks']['US:SH'] == 'index_inverse_ineligible'


def test_inverse_replacement_requires_explicit_retirement_and_preserves_lots(service):
    value = proposal(service)
    assert service.submit(value, 'seven-plan', NOW)['status'] == 'accepted'
    for offset in (30000, 60000):
        service.tick(NOW+offset, snapshot(NOW+offset))
    state = service.store.current()['session']
    before = deepcopy(state)
    now = NOW+120000
    service.claim('rotation-run', now, 'Owner-requested fixture rotation', state['id'],
                  state['policyVersion'])
    manifest = json.loads((service.exchange/'latest.json').read_text())
    value.update(proposal_id='rotation-plan', run_id='rotation-run',
                 snapshot_id=manifest['snapshot_id'],
                 base_policy_version=state['policyVersion'], as_of=now, valid_from=now)
    replacement = dict(market='KR', symbol='114800', name='KODEX Inverse',
                       rationale='Fixture rotation.', evidence_ids=['kodex'])
    value['inverse_groups'] = [dict(group_id='kr-inverse', name='KR index',
                                   candidates=[replacement]),
                               dict(group_id='us-inverse', name='US index', candidates=[
                                   value['inverse_groups'][0]['candidates'][1]])]
    value['evidence'].append(dict(evidence_id='kodex',
        source_url=INDEX_INVERSES['KR:114800']['source_url'], publisher='Fixture',
        published_at=NOW-1000, retrieved_at=now, claim='Fixture only.', excerpt='',
        uncertainty='No market evidence.'))
    value['portfolio']['target_weights'].update({'US:SH':'0', 'KR:114800':'0.05'})
    assert service.validate_proposal(Proposal.model_validate(value), now, state,
                                     service.store.db) == 'invalid_retirements'
    value['portfolio']['retirements'] = [dict(market='US', symbol='SH', name='SH',
        rationale='Explicit inverse replacement.', evidence_ids=['US-SH'])]
    assert service.submit(value, 'rotation-plan', now)['status'] == 'accepted'
    after = service.store.current()['session']
    for field in ('cashBalances', 'positions', 'fills', 'baseline', 'portfolioRuntime'):
        assert after[field] == before[field]
    assert set(domain.standing_symbols(after)) == {'KR:114800', 'US:PSQ'}
