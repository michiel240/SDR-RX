"""Targeted v0.8.2 tests: selection, legacy migration and scan isolation."""
import ast
from pathlib import Path
import pytest
from sdr_studio.memory_groups import (
    ALL_GROUPS, DEFAULT_GROUP, group_members, scan_candidates, scan_counts,
    rename_group, delete_group,
)
from sdr_studio.scan import ScanConfig, ScanEngine


def channels():
    return [{'name': f'Beek {n:02d}', 'frequency': 118_000_000 + n * 25_000,
             'mode': 'AM', 'group': 'Beek'} for n in range(20)]


def test_legacy_channels_all_selected_by_default():
    memories = channels()
    assert scan_counts(memories, 'Beek') == (20, 20)
    assert scan_candidates(memories, 'Beek') == memories


def test_scan_only_ten_of_twenty_without_deleting_anything():
    memories = channels()
    for index, mem in enumerate(memories):
        mem['scan_enabled'] = index < 10
    assert scan_counts(memories, 'Beek') == (10, 20)
    subset = scan_candidates(memories, 'Beek')
    assert len(subset) == 10
    assert [x['frequency'] for x in subset] == [m['frequency'] for m in memories[:10]]
    assert len(group_members(memories, 'Beek')) == 20


def test_any_ten_can_be_selected_not_only_first_ten():
    memories = channels()
    for index, mem in enumerate(memories):
        mem['scan_enabled'] = index % 2 == 0
    result = scan_candidates(memories, 'Beek')
    assert [int(x['name'][-2:]) for x in result] == list(range(0, 20, 2))


def test_unselected_frequencies_still_work_as_memories():
    memories = channels()
    memories[4]['scan_enabled'] = False
    assert len(group_members(memories, 'Beek')) == 20
    assert len(scan_candidates(memories, 'Beek')) == 19
    assert memories[4]['frequency'] == 118_100_000


def test_group_filter_does_not_include_other_group():
    memories = channels() + [{'name': 'Marine', 'frequency': 156_800_000,
                              'mode': 'NFM', 'group': 'Marine'}]
    assert len(scan_candidates(memories, 'Beek')) == 20
    assert len(scan_candidates(memories, 'Marine')) == 1
    assert len(scan_candidates(memories, ALL_GROUPS)) == 21


def test_zero_selection_rejected_by_scan_engine():
    memories = channels()
    for m in memories:
        m['scan_enabled'] = False
    assert scan_counts(memories, 'Beek') == (0, 20)
    with pytest.raises(ValueError):
        ScanConfig(tuple(scan_candidates(memories, 'Beek')))


def test_scan_engine_scans_only_checked_channels():
    memories = channels()
    for index, m in enumerate(memories):
        m['scan_enabled'] = index in (0, 3, 6, 12, 15, 18)
    scan = ScanEngine(ScanConfig(tuple(scan_candidates(memories, 'Beek')), dwell_ms=300, hold_ms=0))
    seen = []
    for index in range(13):
        tune = scan.update(index * .4, False)
        if tune:
            seen.append(tune['name'])
    assert len(set(seen)) == 6
    assert all(int(name[-2:]) in (0, 3, 6, 12, 15, 18) for name in seen)


def test_selection_flags_survive_rename_and_group_delete():
    memories = channels()
    memories[1]['scan_enabled'] = False
    names, renamed = rename_group(['Algemeen', 'Beek'], memories, 'Beek', 'EHBK')
    assert scan_counts(renamed, 'EHBK') == (19, 20)
    names, relocated = delete_group(names, renamed, 'EHBK')
    assert scan_counts(relocated, DEFAULT_GROUP) == (19, 20)
    assert relocated[1]['scan_enabled'] is False


def test_ui_wiring_includes_selector_dialog_and_persistence():
    source = (Path(__file__).resolve().parents[1] / 'sdr_studio' / 'app.py').read_text(encoding='utf-8')
    ast.parse(source)
    for symbol in ('class ScanSelectionDialog(', 'def choose_scan_channels(',
                   'def scan_group_changed(', 'def scan_configuration('):
        assert symbol in source
    assert "scan_candidates(self.memories, self.scan_group.currentText())" in source
    assert 'save_memories(updated)' in source
    assert 'Meenemen in groepsscan' in source
    assert 'Kies eerste N' in source
