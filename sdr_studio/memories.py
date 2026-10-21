"""Persistent named frequencies in user profile."""
import json
from pathlib import Path

ROOT = Path.home() / 'SDRStudio-RX'
FILE = ROOT / 'memories.json'


def load_memories():
    try:
        items = json.loads(FILE.read_text(encoding='utf-8'))
        return [x for x in items if isinstance(x, dict) and {'name', 'frequency', 'mode'} <= x.keys()]
    except (OSError, ValueError, TypeError):
        return []


def save_memories(memories):
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(memories, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(FILE)
