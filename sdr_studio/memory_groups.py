"""Persistent channel-group catalogue, compatible with older memory records.

Groups exist independently of channels, so an empty group survives a restart.
Existing memories.json remains the source of truth for channel data.
"""
from __future__ import annotations

import json
from pathlib import Path
from .memories import ROOT

ALL_GROUPS = 'Alle groepen'
DEFAULT_GROUP = 'Algemeen'
GROUPS_FILE = ROOT / 'groups.json'


def normalize_group(name):
    name = ' '.join(str(name or '').split()).strip()
    if not name or len(name) > 64 or name.casefold() == ALL_GROUPS.casefold():
        raise ValueError('Geef een groepsnaam van 1–64 tekens (niet "Alle groepen").')
    return name


def memory_group(memory):
    try:
        return normalize_group(memory.get('group', DEFAULT_GROUP))
    except ValueError:
        return DEFAULT_GROUP


def groups(memories):
    """Legacy function: groups that contain at least one memory."""
    return sorted({memory_group(m) for m in memories}, key=str.casefold)


def group_members(memories, group):
    if group == ALL_GROUPS:
        return list(memories)
    return [m for m in memories if memory_group(m).casefold() == str(group).casefold()]


def scan_candidates(memories, group=ALL_GROUPS):
    """Return only selected channels, preserving the original group order.

    Legacy memory records without ``scan_enabled`` remain scanable by default.
    The list is never truncated or altered; choices live with each memory.
    """
    return [m for m in group_members(memories, group)
            if m.get('scan_enabled', True) is not False]


def scan_counts(memories, group=ALL_GROUPS):
    """Return (selected, total) for the requested group."""
    total = group_members(memories, group)
    return sum(m.get('scan_enabled', True) is not False for m in total), len(total)


def merge_groups(saved, memories=()):
    seen = set()
    result = []
    for name in [DEFAULT_GROUP, *(saved or ()), *groups(memories)]:
        try:
            cleaned = normalize_group(name)
        except ValueError:
            continue
        folded = cleaned.casefold()
        if folded not in seen:
            result.append(cleaned)
            seen.add(folded)
    return [DEFAULT_GROUP] + sorted((n for n in result if n.casefold() != DEFAULT_GROUP.casefold()), key=str.casefold)


def load_group_names(memories, path=None):
    path = Path(path) if path is not None else GROUPS_FILE
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(saved, list):
            saved = []
    except (OSError, ValueError, TypeError):
        saved = []
    return merge_groups(saved, memories)


def save_group_names(names, path=None):
    path = Path(path) if path is not None else GROUPS_FILE
    clean = merge_groups(names)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)
    return clean


def create_group(existing, name):
    name = normalize_group(name)
    if any(item.casefold() == name.casefold() for item in existing):
        raise ValueError(f'De groep "{name}" bestaat al.')
    return merge_groups([*existing, name])


def rename_group(existing, memories, old, new):
    """Return (groups, updated_memories); do not mutate callers on failure."""
    new = normalize_group(new)
    if old.casefold() == DEFAULT_GROUP.casefold():
        raise ValueError('De groep Algemeen kan niet hernoemd worden.')
    if not any(x.casefold() == old.casefold() for x in existing):
        raise ValueError('De oorspronkelijke groep bestaat niet.')
    if any(x.casefold() == new.casefold() for x in existing if x.casefold() != old.casefold()):
        raise ValueError(f'De groep "{new}" bestaat al.')
    renamed = [new if x.casefold() == old.casefold() else x for x in existing]
    updated = [dict(m, group=new) if memory_group(m).casefold() == old.casefold() else dict(m) for m in memories]
    return merge_groups(renamed), updated


def delete_group(existing, memories, target):
    """Move old channels to Algemeen; caller must confirm deletion in the UI."""
    if target.casefold() == DEFAULT_GROUP.casefold():
        raise ValueError('De groep Algemeen kan niet verwijderd worden.')
    if not any(x.casefold() == target.casefold() for x in existing):
        raise ValueError('De groep bestaat niet.')
    remaining = [g for g in existing if g.casefold() != target.casefold()]
    updated = [dict(m, group=DEFAULT_GROUP) if memory_group(m).casefold() == target.casefold() else dict(m) for m in memories]
    return merge_groups(remaining), updated


def shortcut_memory(memories, number):
    for item in memories:
        try:
            if int(item.get('shortcut', 0)) == int(number):
                return item
        except (ValueError, TypeError):
            continue
    return None
