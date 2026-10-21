"""Group management regressions; no SDR hardware or Qt required."""
import ast
import json
from pathlib import Path
import pytest
from sdr_studio.memory_groups import (
    ALL_GROUPS, DEFAULT_GROUP, create_group, delete_group, group_members,
    load_group_names, merge_groups, normalize_group, rename_group,
    save_group_names, shortcut_memory,
)
from sdr_studio.memories import load_memories, save_memories


@pytest.fixture
def saved_channels():
    return [
        {'name': 'Kanaal 1', 'frequency': 145525000, 'mode': 'NFM',
         'group': 'Beek', 'shortcut': 3, 'favorite': True, 'comment': 'test'},
        {'name': 'Kanaal 2', 'frequency': 123450000, 'mode': 'AM'},
        {'name': 'Kanaal 3', 'frequency': 145650000, 'mode': 'NFM', 'group': 'Beek'},
    ]


def test_create_empty_group_and_reload(tmp_path):
    path = tmp_path / 'groups.json'
    initial = load_group_names([], path)
    updated = create_group(initial, 'Beek')
    assert updated == ['Algemeen', 'Beek']
    save_group_names(updated, path)
    assert load_group_names([], path) == updated
    assert group_members([], 'Beek') == []


def test_existing_old_memories_are_discovered(tmp_path, saved_channels):
    assert load_group_names(saved_channels, tmp_path/'missing.json') == ['Algemeen', 'Beek']
    assert [x['name'] for x in group_members(saved_channels, 'Beek')] == ['Kanaal 1','Kanaal 3']
    assert len(group_members(saved_channels, ALL_GROUPS)) == 3
    assert [x['name'] for x in group_members(saved_channels, DEFAULT_GROUP)] == ['Kanaal 2']


def test_group_rename_keeps_frequencies_shortcut_favourite_comments(saved_channels):
    old = [dict(x) for x in saved_channels]
    names, moved = rename_group(['Algemeen','Beek'],saved_channels,'Beek','Maastricht')
    assert names == ['Algemeen','Maastricht']
    assert len(group_members(moved,'Maastricht')) == 2
    assert shortcut_memory(moved,3)['name'] == 'Kanaal 1'
    assert shortcut_memory(moved,3)['favorite'] is True
    assert shortcut_memory(moved,3)['comment'] == 'test'
    assert saved_channels == old


def test_deleting_group_keeps_frequencies_but_moves_to_general(saved_channels):
    names, moved = delete_group(['Algemeen','Beek'],saved_channels,'Beek')
    assert names == ['Algemeen']
    assert len(moved) == len(saved_channels)
    assert all(x.get('group','Algemeen') == 'Algemeen' for x in moved)


def test_case_insensitive_uniqueness_and_invalid_names():
    with pytest.raises(ValueError):create_group(['Algemeen','Beek'],'beek')
    with pytest.raises(ValueError):create_group(['Algemeen'],'Alle groepen')
    with pytest.raises(ValueError):create_group(['Algemeen'],' ')
    with pytest.raises(ValueError):delete_group(['Algemeen'],[],'Algemeen')
    with pytest.raises(ValueError):rename_group(['Algemeen'],[],'Algemeen','Beek')
    with pytest.raises(ValueError):rename_group(['Algemeen','Beek','Militair'],[],'Beek','MILITAIR')
    assert normalize_group('  Vlieg  veld  Beek  ') == 'Vlieg veld Beek'


def test_catalogue_corrupt_falls_back_to_memory_groups(tmp_path, saved_channels):
    path=tmp_path/'groups.json'
    path.write_text('{kapot json', encoding='utf8')
    assert load_group_names(saved_channels,path) == ['Algemeen','Beek']
    path.write_text('"geen lijst"',encoding='utf8')
    assert load_group_names(saved_channels,path) == ['Algemeen','Beek']


def test_persistent_groups_and_memories_remain_distinct(tmp_path, saved_channels):
    path=tmp_path/'groups.json'
    saved = save_group_names(['Algemeen','Beek','Reserve'],path)
    assert saved == ['Algemeen','Beek','Reserve']
    assert load_group_names(saved_channels,path) == saved
    assert json.loads(path.read_text()) == saved


def test_ui_has_group_crud_and_edit_dialog():
    source=(Path(__file__).resolve().parents[1]/'sdr_studio'/'app.py').read_text(encoding='utf8')
    ast.parse(source)
    for name in ('create_memory_group','rename_memory_group','delete_memory_group',
                 'edit_memory','memory_group_changed'):
        assert f'def {name}(' in source
    assert "self.mem_group.setCurrentText" in source
    assert 'MemoryEditDialog' in source
    assert 'Scan geheugenkanalen' in source
