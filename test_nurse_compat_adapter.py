#!/usr/bin/env python3
"""
Sprint 2 contract tests for nurse-compat facility adapter routes.

These tests use Flask's test client and lightweight monkeypatching of route-layer
query/helpers so they can run without a seeded database.
"""

import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

# Ensure local imports work when invoked directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from routes import routes_facility_staff_auth as mod


class _QueryStub:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = list(many or [])

    def get(self, _id):
        return self._one

    def filter_by(self, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._many)


class _SessionStub:
    def commit(self):
        return None


@contextmanager
def _patched(**patches):
    originals = {}
    try:
        for name, value in patches.items():
            originals[name] = getattr(mod, name)
            setattr(mod, name, value)
        yield
    finally:
        for name, original in originals.items():
            setattr(mod, name, original)


def _auth_header():
    return {'Authorization': 'Bearer fake-token'}


def _base_context(is_admin=False, role='nurse'):
    account = SimpleNamespace(id=99, name='Compat Nurse')

    def _scope(_account, facility_id):
        return int(facility_id), is_admin, None, role

    def _resolve_account_from_jwt():
        return account

    return account, _resolve_account_from_jwt, _scope


def test_context_contract():
    app = create_app()
    account, resolve_account_from_jwt, scope = _base_context(is_admin=False, role='nurse')

    facility = SimpleNamespace(id=7, city='Nairobi', address='CBD')

    with _patched(
        _resolve_facility_account_from_jwt=resolve_account_from_jwt,
        _ensure_nurse_compat_scope=scope,
        HealthFacility=SimpleNamespace(query=_QueryStub(one=facility)),
    ):
        with app.test_client() as client:
            res = client.get('/api/v1/facilities/7/nurse-compat/context', headers=_auth_header())
            assert res.status_code == 200, res.get_data(as_text=True)
            payload = res.get_json()
            assert payload['mode'] == 'facility_nurse_compat'
            assert payload['profile']['id'] == account.id
            assert payload['profile']['role'] == 'nurse'
            assert 'can_create_appointments' in payload['capabilities']


def test_escalation_list_contract_status_mapping():
    app = create_app()
    _account, resolve_account_from_jwt, scope = _base_context(is_admin=True, role='admin')

    escalation = SimpleNamespace(
        id=11,
        chw_id=22,
        chw=SimpleNamespace(name='CHW A'),
        assigned_staff_account_id=99,
        updated_by_account_id=99,
        assigned_staff=SimpleNamespace(name='Assigned Nurse'),
        mother_id=33,
        checkin_id=44,
        mother_name='Mother A',
        case_description='High blood pressure',
        issue_type='bp',
        notes='urgent',
        priority='high',
        status='checked_out',
        created_at=datetime.now(timezone.utc),
        checked_out_at=datetime.now(timezone.utc),
        facility_id=7,
    )

    with _patched(
        _resolve_facility_account_from_jwt=resolve_account_from_jwt,
        _ensure_nurse_compat_scope=scope,
        FacilityEscalation=SimpleNamespace(query=_QueryStub(many=[escalation]), created_at=SimpleNamespace(desc=lambda: None), status='status', priority='priority', assigned_staff_account_id='assigned_staff_account_id', facility_id='facility_id'),
    ):
        with app.test_client() as client:
            res = client.get('/api/v1/facilities/7/nurse-compat/escalations', headers=_auth_header())
            assert res.status_code == 200, res.get_data(as_text=True)
            payload = res.get_json()
            assert payload['total'] == 1
            assert payload['escalations'][0]['status'] == 'resolved'


def test_admin_only_escalation_status_update():
    app = create_app()
    _account, resolve_account_from_jwt, scope = _base_context(is_admin=False, role='nurse')

    with _patched(
        _resolve_facility_account_from_jwt=resolve_account_from_jwt,
        _ensure_nurse_compat_scope=scope,
    ):
        with app.test_client() as client:
            res = client.patch(
                '/api/v1/facilities/7/nurse-compat/escalations/1/status',
                json={'status': 'resolved'},
                headers=_auth_header(),
            )
            assert res.status_code == 403, res.get_data(as_text=True)


def test_non_admin_cannot_restore_appointment():
    app = create_app()
    account, resolve_account_from_jwt, scope = _base_context(is_admin=False, role='nurse')

    appointment = SimpleNamespace(
        id=21,
        facility_id=7,
        status='canceled',
        assigned_staff_account_id=account.id,
        created_by_account_id=account.id,
        mother_id=1,
        mother_name='Mother A',
        assigned_staff=None,
        creator_account=None,
        appointment_type='checkup',
        scheduled_time=datetime.now(timezone.utc),
        notes=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    with _patched(
        _resolve_facility_account_from_jwt=resolve_account_from_jwt,
        _ensure_nurse_compat_scope=scope,
        FacilityAppointment=SimpleNamespace(query=_QueryStub(one=appointment)),
        db=SimpleNamespace(session=_SessionStub()),
    ):
        with app.test_client() as client:
            res = client.post(
                '/api/v1/facilities/7/nurse-compat/appointments/21/restore',
                headers=_auth_header(),
            )
            assert res.status_code == 403, res.get_data(as_text=True)


def test_delete_appointment_sets_canceled_status():
    app = create_app()
    account, resolve_account_from_jwt, scope = _base_context(is_admin=False, role='nurse')

    appointment = SimpleNamespace(
        id=42,
        facility_id=7,
        status='scheduled',
        assigned_staff_account_id=account.id,
        created_by_account_id=88,
        mother_id=1,
        mother_name='Mother A',
        assigned_staff=None,
        creator_account=None,
        appointment_type='checkup',
        scheduled_time=datetime.now(timezone.utc),
        notes='x',
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    with _patched(
        _resolve_facility_account_from_jwt=resolve_account_from_jwt,
        _ensure_nurse_compat_scope=scope,
        FacilityAppointment=SimpleNamespace(query=_QueryStub(one=appointment)),
        db=SimpleNamespace(session=_SessionStub()),
        _emit_facility_appointment=lambda *_args, **_kwargs: None,
        _notify_mother_facility_appointment=lambda *_args, **_kwargs: None,
        _notify_assigned_facility_staff_for_appointment=lambda *_args, **_kwargs: None,
    ):
        with app.test_client() as client:
            res = client.delete(
                '/api/v1/facilities/7/nurse-compat/appointments/42',
                headers=_auth_header(),
            )
            assert res.status_code == 200, res.get_data(as_text=True)
            payload = res.get_json()
            assert payload['appointment']['status'] == 'canceled'


def test_update_appointment_details_contract():
    app = create_app()
    account, resolve_account_from_jwt, scope = _base_context(is_admin=True, role='admin')

    appointment = SimpleNamespace(
        id=52,
        facility_id=7,
        status='scheduled',
        assigned_staff_account_id=account.id,
        created_by_account_id=account.id,
        mother_id=1,
        mother_name='Mother A',
        assigned_staff=None,
        creator_account=None,
        appointment_type='checkup',
        scheduled_time=datetime.now(timezone.utc),
        notes='before',
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    with _patched(
        _resolve_facility_account_from_jwt=resolve_account_from_jwt,
        _ensure_nurse_compat_scope=scope,
        FacilityAppointment=SimpleNamespace(query=_QueryStub(one=appointment)),
        db=SimpleNamespace(session=_SessionStub()),
        _emit_facility_appointment=lambda *_args, **_kwargs: None,
        _notify_mother_facility_appointment=lambda *_args, **_kwargs: None,
        _notify_assigned_facility_staff_for_appointment=lambda *_args, **_kwargs: None,
    ):
        with app.test_client() as client:
            res = client.patch(
                '/api/v1/facilities/7/nurse-compat/appointments/52',
                json={'notes': 'after', 'appointment_type': 'follow_up'},
                headers=_auth_header(),
            )
            assert res.status_code == 200, res.get_data(as_text=True)
            payload = res.get_json()
            assert payload['appointment']['notes'] == 'after'


def test_resources_contract_in_compat_mode():
    app = create_app()
    _account, resolve_account_from_jwt, scope = _base_context(is_admin=False, role='nurse')

    row = SimpleNamespace(
        id=9,
        title='Danger Signs',
        description='Reference',
        category='maternal',
        target_role='nurse',
        content_type='article',
        url='https://example.com',
        thumbnail='doc',
        created_at=datetime.now(timezone.utc),
    )

    with _patched(
        _resolve_facility_account_from_jwt=resolve_account_from_jwt,
        _ensure_nurse_compat_scope=scope,
        Resource=SimpleNamespace(query=_QueryStub(many=[row]), created_at=SimpleNamespace(desc=lambda: None)),
    ):
        with app.test_client() as client:
            res = client.get('/api/v1/facilities/7/nurse-compat/resources?role=nurse', headers=_auth_header())
            assert res.status_code == 200, res.get_data(as_text=True)
            payload = res.get_json()
            assert payload['count'] == 1
            assert payload['data'][0]['target_role'] == 'nurse'


def run_all():
    tests = [
        test_context_contract,
        test_escalation_list_contract_status_mapping,
        test_admin_only_escalation_status_update,
        test_non_admin_cannot_restore_appointment,
        test_delete_appointment_sets_canceled_status,
        test_update_appointment_details_contract,
        test_resources_contract_in_compat_mode,
    ]

    passed = 0
    for test_fn in tests:
        test_fn()
        passed += 1
        print(f'PASS: {test_fn.__name__}')

    print(f'\nAll nurse-compat adapter tests passed ({passed}/{len(tests)}).')


if __name__ == '__main__':
    run_all()
