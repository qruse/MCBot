"""Explicit held conversion preserves the native book and isolates closed-market exits."""
from copy import deepcopy

import pytest
from test_paper import NOW, command
from test_paper import service as service
from test_portfolio import activate, fill
from test_stock_theme import INVERSES, STOCKS, proposal, snapshot

from app.paper.contracts import Command
from app.paper.market import demo_snapshot
from app.paper.service import Conflict


def closed_native(service):
    activate(service)
    fill(service)
    command(service, 'pause', now=NOW+70000)
    closed = demo_snapshot('KR', NOW+80000)
    closed.update(marketOpen=False, marketClose=NOW+70000, id='closed-held-fixture',
                  observedAt=NOW+80000)
    # A recorded, dated positive mark is valuation only; executable quotes are unavailable.
    closed['displayQuotes'] = deepcopy(closed['quotes'])
    for q in closed['quotes'].values():
        q['price'] = None
    from app.paper.storage import encode
    with service.store.transaction() as db:
        db.execute('INSERT INTO observations VALUES(?,?)', (closed['id'], encode(closed)))
        bundle = service.store.current()
        bundle['session']['latest'] = closed
        bundle['session']['lastOpenClose'] = NOW+70000
        service.store.save(bundle)
    return deepcopy(service.store.current())


def test_held_conversion_then_us_orders_preserve_native_account_and_reference(service):
    before = closed_native(service)
    receipt = command(service, 'enable_global_preserving', now=NOW+90000)
    after = service.store.current()
    for field in ('id', 'cash', 'baseline', 'positions', 'fills', 'policy', 'policyVersion'):
        assert after['session'][field] == before['session'][field]
    assert after['benchmark'] == before['benchmark']
    assert after['session']['marketEntryBlocks'] == {'KR': 'closing_exit_incomplete'}
    assert (after['session']['portfolioRuntime']['last_slot']
            == before['session']['portfolioRuntime']['last_slot'])
    assert service.view()['session']['config']['market'] == 'GLOBAL'
    repeat = Command(command_id=f'enable_global_preserving-{NOW+90000}',
                     session_id=before['session']['id'],
                     expected_version=before['session']['version'],
                     action='enable_global_preserving')
    assert service.command(repeat, NOW+90000) == receipt
    command(service, 'resume', now=NOW+100000)
    now = NOW+3700000  # A new hour; conversion did not erase ordinary turnover history.
    value = proposal(service, now=now, existing=True, kr=False)
    held = {f'KR:{p["symbol"]}' for p in before['session']['positions']}
    retired = held-set(STOCKS)-set(INVERSES)
    value['portfolio']['target_weights'] = {
        **{k: '0.17' for k in STOCKS}, **{k: '0.025' for k in INVERSES},
        **{k: '0' for k in retired}, 'CASH': '0.10'}
    value['portfolio']['retirements'] = [dict(market='KR', symbol=k[3:], name=k,
        rationale='Explicit legacy fixture retirement.', evidence_ids=['stocks']) for k in retired]
    assert service.submit(value, 'seven-plan', now)['status'] == 'accepted'
    for offset in (30000, 60000):
        service.tick(now+offset, snapshot(now+offset, kr=False))
    final = service.store.current()['session']
    assert final['strategyError'] is None
    assert final['condition'] == 'ready' and final['lifecycle'] == 'running'
    added = final['fills'][len(before['session']['fills']):]
    assert added and all(f['market'] == 'US' and f['side'] == 'buy' for f in added)
    assert [p for p in final['positions'] if 'market' not in p] == before['session']['positions']
    assert final['baseline'] == before['session']['baseline']
    assert service.store.current()['benchmark']['fills'] == before['benchmark']['fills']
    # A fresh KR open completes the failed closing exits; old lots retain attribution.
    service.tick(now+90000, snapshot(now+90000))
    kr_sells = service.store.current()['session']['fills'][len(final['fills']):]
    assert kr_sells and all(f['market'] == 'KR' and f['reason'] == 'closing_exit' for f in kr_sells)
    assert ({f['entryId'] for f in kr_sells}
            == {p['entryId'] for p in before['session']['positions']})


@pytest.mark.parametrize('failure', ['sidecar', 'open_market', 'missing_mark'])
def test_held_conversion_refuses_unsafe_state(service, failure):
    closed_native(service)
    with service.store.transaction() as db:
        bundle = service.store.current()
        if failure == 'sidecar':
            bundle['session']['sidecarPending'] = True
        else:
            observation = demo_snapshot('KR', NOW+81000)
            observation.update(id=f'migration-{failure}', marketOpen=failure == 'open_market',
                               observedAt=NOW+81000)
            if failure == 'missing_mark':
                observation['quotes'] = {'005930': {'price': None}}
            from app.paper.storage import encode
            db.execute('INSERT INTO observations VALUES(?,?)',
                       (observation['id'], encode(observation)))
        service.store.save(bundle)
    before = deepcopy(service.store.current())
    with pytest.raises(Conflict):
        command(service, 'enable_global_preserving', now=NOW+90000)
    assert service.store.current() == before
