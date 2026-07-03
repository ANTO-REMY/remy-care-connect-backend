#!/usr/bin/env python3
"""
Focused unit tests for auto ward-based mother-CHW assignment helpers.

These tests use lightweight stubs so they can run without a seeded database.
"""

import os
import sys
from contextlib import contextmanager
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import assignment_utils as mod


class _QueryListStub:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter_by(self, **kwargs):
        rows = [
            row for row in self._rows
            if all(getattr(row, key) == value for key, value in kwargs.items())
        ]
        return _QueryListStub(rows)

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _SessionStub:
    def __init__(self, counts=None):
        self._counts = list(counts or [])
        self.added = []
        self.flush_count = 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1

    def query(self, *_args, **_kwargs):
        return _AggregateQueryStub(self._counts)


class _AggregateQueryStub:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *_args, **_kwargs):
        return self

    def group_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)


class _CHWQueryStub:
    def __init__(self, chws):
        self._chws = list(chws)

    def filter_by(self, **kwargs):
        rows = [
            chw for chw in self._chws
            if all(getattr(chw, key) == value for key, value in kwargs.items())
        ]
        return _CHWOrderStub(rows)


class _CHWOrderStub:
    def __init__(self, chws):
        self._chws = list(chws)

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._chws)


class _AssignmentStub:
    query = _QueryListStub([])
    id = SimpleNamespace(desc=lambda: None)

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


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


def test_find_best_chw_for_ward_prefers_lowest_load_then_lowest_id():
    chws = [
        SimpleNamespace(id=9, ward_id=5),
        SimpleNamespace(id=3, ward_id=5),
        SimpleNamespace(id=7, ward_id=5),
    ]
    session = _SessionStub(counts=[(9, 2), (3, 1), (7, 1)])

    with _patched(
        CHW=SimpleNamespace(query=_CHWQueryStub(chws), id=SimpleNamespace(asc=lambda: None)),
        db=SimpleNamespace(session=session),
    ):
        chosen = mod.find_best_chw_for_ward(5)

    assert chosen.id == 3


def test_find_best_chw_for_ward_returns_none_when_all_full():
    chws = [
        SimpleNamespace(id=1, ward_id=4),
        SimpleNamespace(id=2, ward_id=4),
    ]
    session = _SessionStub(counts=[(1, mod.MAX_ACTIVE_MOTHERS_PER_CHW), (2, 27)])

    with _patched(
        CHW=SimpleNamespace(query=_CHWQueryStub(chws), id=SimpleNamespace(asc=lambda: None)),
        db=SimpleNamespace(session=session),
    ):
        chosen = mod.find_best_chw_for_ward(4)

    assert chosen is None


def test_assign_mother_to_specific_chw_refuses_second_active_assignment():
    chw = SimpleNamespace(id=10, chw_name='CHW One')
    mother = SimpleNamespace(id=20, mother_name='Mother One')
    current_active = SimpleNamespace(chw_id=99)

    with _patched(
        get_active_assignment_for_mother=lambda mother_id: current_active if mother_id == mother.id else None,
    ):
        try:
            mod.assign_mother_to_specific_chw(
                chw,
                mother,
                assignment_method=mod.ASSIGNMENT_METHOD_MANUAL,
                conflict_policy='refuse',
            )
            raise AssertionError('Expected AssignmentConflictError')
        except mod.AssignmentConflictError:
            pass


def test_assign_mother_if_possible_returns_none_without_eligible_chw():
    mother = SimpleNamespace(id=12, ward_id=8)

    with _patched(
        Mother=SimpleNamespace(query=SimpleNamespace(get=lambda mother_id: mother if mother_id == 12 else None)),
        get_active_assignment_for_mother=lambda _mother_id: None,
        find_best_chw_for_ward=lambda ward_id, exclude_chw_ids=None: None,
    ):
        assignment, changed = mod.assign_mother_if_possible(12)

    assert assignment is None
    assert changed is False


def test_assign_mother_to_specific_chw_creates_auto_assignment():
    chw = SimpleNamespace(id=4, chw_name='CHW Two')
    mother = SimpleNamespace(id=6, mother_name='Mother Two')
    session = _SessionStub()

    with _patched(
        get_active_assignment_for_mother=lambda _mother_id: None,
        count_active_assignments_for_chw=lambda _chw_id: 0,
        MotherCHWAssignment=_AssignmentStub,
        db=SimpleNamespace(session=session),
    ):
        assignment, changed, result_status = mod.assign_mother_to_specific_chw(
            chw,
            mother,
            assignment_method=mod.ASSIGNMENT_METHOD_AUTO_WARD_MATCH,
            conflict_policy='replace',
        )

    assert changed is True
    assert result_status == 'created'
    assert assignment.chw_id == 4
    assert assignment.mother_id == 6
    assert assignment.assignment_method == mod.ASSIGNMENT_METHOD_AUTO_WARD_MATCH
    assert session.added and session.added[0] is assignment


def run_all():
    tests = [
        test_find_best_chw_for_ward_prefers_lowest_load_then_lowest_id,
        test_find_best_chw_for_ward_returns_none_when_all_full,
        test_assign_mother_to_specific_chw_refuses_second_active_assignment,
        test_assign_mother_if_possible_returns_none_without_eligible_chw,
        test_assign_mother_to_specific_chw_creates_auto_assignment,
    ]

    passed = 0
    for test_fn in tests:
        test_fn()
        passed += 1
        print(f'PASS: {test_fn.__name__}')

    print(f'\\nAll assignment helper tests passed ({passed}/{len(tests)}).')


if __name__ == '__main__':
    run_all()
