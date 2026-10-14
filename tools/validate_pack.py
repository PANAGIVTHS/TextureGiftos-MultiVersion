#!/usr/bin/env python3
"""Validate generated pack structure/references for one or every Java release.

This is a structural check, not a substitute for loading the pack in-game.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from zipfile import ZipFile

from build_pack import PACK_FORMATS, collect
from model_textures import model_issues


def target(ref, kind):
    ns, sep, rel = ref.partition(':')
    if not sep:
        ns, rel = 'minecraft', ns
    return f'assets/{ns}/{kind}/{rel}.json' if kind == 'models' else f'assets/{ns}/{kind}/{rel}.png'


def inspect(files, version, warnings=None):
    errors = []
    def err(msg):
        errors.append(f'{version}: {msg}')
    if 'pack.mcmeta' not in files or 'pack.png' not in files:
        err('Missing pack.mcmeta or pack.png at the ZIP root')
        return errors
    try:
        meta = json.loads(files['pack.mcmeta'])['pack']
        fmt = PACK_FORMATS[version]
        if isinstance(fmt, tuple):
            if meta.get('min_format') != list(fmt) or meta.get('max_format') != list(fmt):
                err(f'Wrong major/minor resource-pack format {fmt}')
        elif fmt >= 69:
            if meta.get('min_format') != [fmt, 0] or meta.get('max_format') != fmt:
                err(f'Wrong resource-pack range format {fmt}')
        elif meta.get('pack_format') != fmt:
            err(f'Wrong resource-pack format {fmt}')
    except (ValueError, KeyError, TypeError) as e:
        err(f'Bad pack.mcmeta: {e}')
    modern = isinstance(fmt, tuple) or fmt >= 46
    models = {}
    for file, data in files.items():
        if not file.startswith('assets/'):
            if file not in ('pack.mcmeta', 'pack.png'):
                err(f'Unexpected root file {file}')
            continue
        if file.endswith('.json'):
            try:
                doc = json.loads(data)
            except (ValueError, UnicodeDecodeError) as e:
                err(f'Invalid JSON {file}: {e}')
                continue
            if '/models/' in file:
                models[file] = doc
                parent = doc.get('parent')
                if parent and target(parent, 'models') not in files and not target(parent, 'models').startswith('assets/minecraft/'):
                    err(f'{file}: nonexistent custom parent {parent}')
                for node in doc.get('overrides', []):
                    ref = node.get('model')
                    if ref and target(ref, 'models') not in files and not target(ref, 'models').startswith('assets/minecraft/'):
                        err(f'{file}: absent override model {ref}')
            if '/items/' in file:
                if not modern:
                    err(f'Old Minecraft version must not contain item definitions: {file}')
                def walk(v):
                    if isinstance(v, dict):
                        if v.get('type') == 'minecraft:model':
                            ref = v.get('model')
                            if not isinstance(ref, str):
                                err(f'{file}: missing model reference')
                            elif target(ref, 'models') not in files and not target(ref, 'models').startswith('assets/minecraft/'):
                                err(f'{file}: missing referenced model {ref}')
                        for sub in v.values():
                            walk(sub)
                    elif isinstance(v, list):
                        for sub in v:
                            walk(sub)
                walk(doc)
        if file.endswith('.png'):
            if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
                err(f'Invalid PNG header: {file}')
                continue
            w, h = struct.unpack('>II', data[16:24])
            if w <= 0 or h <= 0:
                err(f'Invalid PNG dimensions: {file}')
            meta_file = file + '.mcmeta'
            if meta_file in files:
                try:
                    anim = json.loads(files[meta_file])['animation']
                    fw, fh = anim.get('width', w), anim.get('height', w)
                    if not (isinstance(fw, int) and isinstance(fh, int) and fw > 0 and fh > 0 and w % fw == 0 and h % fh == 0):
                        err(f'Invalid animation frame size: {file} ({w}x{h})')
                    else:
                        count = w // fw * h // fh
                        for frame in anim.get('frames', []):
                            n = frame.get('index', -1) if isinstance(frame, dict) else frame
                            if not isinstance(n, int) or not (0 <= n < count):
                                err(f'Animation frame out of range: {file} = {n}')
                except (ValueError, KeyError, TypeError) as e:
                    err(f'Malformed animation {meta_file}: {e}')
        if file.endswith('.properties'):
            raw = data.decode('utf8')
            lines = dict(kv.split('=', 1) for line in raw.splitlines() if '=' in line for kv in [line])
            model = lines.get('model')
            if model and target(model, 'models') not in files:
                err(f'{file}: referenced CIT model does not exist: {model}')
    for level, name, detail in model_issues(files):
        if level == 'ERROR':
            err(f'{name}: {detail}')
        elif warnings is not None:
            warnings.append(f'{version}: {name}: {detail}')
    if 'assets/mcd/textures/item/swords/under_fix.png' not in files:
        err('Dragonslayer patch is absent')
    if 'assets/mcd/textures/item/swords/handle_wraps.png.mcmeta' not in files:
        err('Dragonslayer ribbon animation missing metadata')
    if modern and 'assets/minecraft/items/netherite_sword.json' not in files:
        err('No modern Netherite Sword selector')
    if not modern and 'assets/minecraft/models/item/netherite_sword.json' not in files:
        err('No legacy Netherite Sword overrides')
    return errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', choices=PACK_FORMATS, help='Validate one supported Java release')
    p.add_argument('--zip', type=Path, help='Validate a built pack ZIP (requires --version)')
    a = p.parse_args()
    if a.zip and not a.version:
        p.error('--zip requires --version')
    errors = []
    all_warnings = []
    for version in (a.version,) if a.version else PACK_FORMATS:
        if a.zip:
            with ZipFile(a.zip) as z:
                files = {name: z.read(name) for name in z.namelist() if not name.endswith('/')}
        else:
            files = collect(version)
        warnings = []
        e = inspect(files, version, warnings)
        errors.extend(e)
        all_warnings.extend(warnings)
        print(f'{version:8s} {"FAIL" if e else "OK"}  ({len(files)} pack files, {len(e)} errors, {len(warnings)} warnings)')
    for e in errors:
        print('ERROR:', e)
    # De-duplicate warnings across the 23 generated versions.
    for warning in all_warnings:
        print('WARN:', warning)
    print(f'{len(errors)} total errors; {len(all_warnings)} warnings.')
    return int(bool(errors))


if __name__ == '__main__':
    sys.exit(main())
