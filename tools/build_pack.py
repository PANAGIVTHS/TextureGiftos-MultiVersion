#!/usr/bin/env python3
"""Build Minecraft Java TextureGiftos packs without modifying source assets.

All version-specific conversions are performed in memory on the archive map.
Python 3.9+ and the standard library only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from model_textures import prune_broken_faces
from model_compat import convert

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'
PACK_FORMATS = {
    '1.20.1': 15, '1.20.2': 18, '1.20.3': 22, '1.20.4': 22,
    '1.20.5': 32, '1.20.6': 32, '1.21': 34, '1.21.1': 34,
    '1.21.2': 42, '1.21.3': 42, '1.21.4': 46, '1.21.5': 55,
    '1.21.6': 63, '1.21.7': 64, '1.21.8': 64,
    '1.21.9': 69, '1.21.10': 69, '1.21.11': 75,
    '26.1': 84, '26.1.1': 84, '26.1.2': 84, '26.2': 88, '26.3': (97, 1),
}
CUSTOM_SWORDS = [
    ('agsheath', 123001), ('aatrox', 123002), ('guts', 123003),
    ('dragonslayer', 123004),
]
NAME_RULES = [
    ('netherite_sword', "Guts' Sword", 'swords/guts'),
    ('netherite_sword', "Gut’s Sword", 'swords/guts'),
    ('netherite_sword', 'Aatrox', 'swords/aatrox'),
    ('netherite_sword', 'Tenryū’s Shriek', 'swords/agsheath'),
    ('diamond_sword', 'Tenryū’s Shriek', 'swords/agsheath'),
    ('netherite_sword', 'Dragonslayer', 'swords/dragonslayer'),
    ('netherite_sword', 'Dragon Slayer', 'swords/dragonslayer'),
    ('bow', 'Varus', 'bows/varus'),
    ('carrot_on_a_stick', 'Scanner', 'misc/scanner_detector'),
    ('ender_eye', "Ender's Wrath", 'misc/enders_wrath'),
]


def pretty_json(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def metadata(version):
    fmt = PACK_FORMATS[version]
    title = f'TextureGiftos · Minecraft Java {version}'
    if isinstance(fmt, tuple):
        return {'pack': {'description': title, 'min_format': list(fmt), 'max_format': list(fmt)}}
    if fmt >= 69:
        return {'pack': {'description': title, 'min_format': [fmt, 0], 'max_format': fmt}}
    return {'pack': {'description': title, 'pack_format': fmt}}


def nested_model(path):
    return {'type': 'minecraft:model', 'model': f'mcd:item/{path}'}


def default_item_model(item):
    if item == 'netherite_sword':
        # Self-contained conventional vanilla handheld model: protects the
        # unmodified sword from an absent or overridden raw Minecraft model.
        return {'type': 'minecraft:model', 'model': 'mcd:item/compat/vanilla_netherite_sword'}
    return {'type': 'minecraft:model', 'model': f'minecraft:item/{item}'}


def named_switch(item_name, mapping):
    """Create a name selector. A duplicate name can invalidate the *entire* item.

    Identical duplicates are deduplicated, but contradictory names are errors.
    """
    cases, seen = [], {}
    for name, path in mapping:
        if name in seen:
            if seen[name] != path:
                raise ValueError(f'Conflicting model for item {item_name} name {name!r}')
            continue
        seen[name] = path
        cases.append({'when': name, 'model': nested_model(path)})
    return {'model': {
        'type': 'minecraft:select', 'property': 'minecraft:component',
        'component': 'minecraft:custom_name',
        'cases': cases,
        'fallback': default_item_model(item_name),
    }}


def numeric_model_selector(named, entries):
    """Use CMD floats and restore the fallback after the last known ID."""
    if not entries:
        return named
    entries = sorted(entries)
    if len(set(code for code, _ in entries)) != len(entries):
        raise ValueError('Duplicate CustomModelData ID')
    return {
        'type': 'minecraft:range_dispatch',
        'property': 'minecraft:custom_model_data',
        'entries': [
            {'threshold': code, 'model': nested_model(path)} for code, path in entries
        ] + [{'threshold': entries[-1][0] + 1, 'model': named}],
        'fallback': named,
    }


def modern_definitions(name_switch_supported=True):
    defs = {
        key: named_switch(key, [(n, p) for item, n, p in NAME_RULES if item == key])
        for key in ('netherite_sword', 'diamond_sword', 'carrot_on_a_stick', 'ender_eye')
    }
    if not name_switch_supported:
        for key in defs:
            defs[key] = {'model': default_item_model(key)}
    for item, entries in (
        ('netherite_sword', [(code, f'swords/{name}') for name, code in CUSTOM_SWORDS]),
        ('diamond_sword', [(123001, 'swords/agsheath')]),
        ('carrot_on_a_stick', [(123401, 'misc/scanner_detector')]),
        ('ender_eye', [(123301, 'misc/enders_wrath')]),
    ):
        defs[item]['model'] = numeric_model_selector(defs[item]['model'], entries)
    # Bow retains vanilla pull stages rather than blindly replacing them.
    def bow_state(stage):
        return {
            'type': 'minecraft:select', 'property': 'minecraft:component',
            'component': 'minecraft:custom_name',
            'cases': [{'when': 'Varus', 'model': nested_model('bows/varus')}],
            'fallback': default_item_model('bow' if stage is None else f'bow_pulling_{stage}'),
        }
    defs['bow'] = {'model': {
        'type': 'minecraft:condition', 'property': 'minecraft:using_item',
        'on_false': bow_state(None),
        'on_true': {
            'type': 'minecraft:range_dispatch', 'property': 'minecraft:use_duration',
            'scale': 0.05,
            'entries': [
                {'threshold': .65, 'model': bow_state(1)},
                {'threshold': .9, 'model': bow_state(2)},
            ], 'fallback': bow_state(0),
        },
    }}
    if not name_switch_supported:
        defs['bow'] = {'model': default_item_model('bow')}
    return {f'assets/minecraft/items/{key}.json': pretty_json(value) for key, value in defs.items()}


def legacy_definition(item, layer, parent, overrides):
    return pretty_json({
        'parent': parent, 'textures': {'layer0': f'minecraft:item/{layer}'},
        'overrides': [
            {'predicate': {'custom_model_data': code}, 'model': f'minecraft:item/custom/{path}'}
            for code, path in overrides
        ],
    })


def legacy_definitions():
    out = {}
    for source in sorted((ASSETS / 'mcd/models/item').rglob('*.json')):
        rel = source.relative_to(ASSETS / 'mcd/models/item').with_suffix('')
        item_ref = rel.as_posix()
        out[f'assets/minecraft/models/item/custom/{item_ref}.json'] = pretty_json(
            {'parent': f'mcd:item/{item_ref}'})
    swords = [(code, f'swords/{name}') for name, code in CUSTOM_SWORDS]
    out['assets/minecraft/models/item/netherite_sword.json'] = legacy_definition(
        'netherite_sword', 'netherite_sword', 'minecraft:item/handheld', swords)
    out['assets/minecraft/models/item/diamond_sword.json'] = legacy_definition(
        'diamond_sword', 'diamond_sword', 'minecraft:item/handheld', [(123001, 'swords/agsheath')])
    out['assets/minecraft/models/item/carrot_on_a_stick.json'] = legacy_definition(
        'carrot_on_a_stick', 'carrot_on_a_stick', 'minecraft:item/handheld_rod',
        [(123401, 'misc/scanner_detector')])
    out['assets/minecraft/models/item/ender_eye.json'] = legacy_definition(
        'ender_eye', 'ender_eye', 'minecraft:item/generated', [(123301, 'misc/enders_wrath')])
    for i, (item, name, target) in enumerate(NAME_RULES):
        out[f'assets/minecraft/optifine/cit/texturegiftos/{i:02d}_{target.replace("/", "_")}.properties'] = (
            'type=item\n'
            f'items=minecraft:{item}\n'
            f'model=item/custom/{target}\n'
            f'nbt.display.Name=ipattern:*{name}*\n'
        ).encode('utf-8')
    out['assets/minecraft/optifine/cit/texturegiftos/99_soulsweapons_guts.properties'] = (
        'type=item\nitems=soulsweapons:guts_sword\n'
        'model=item/custom/swords/guts\n'
        "nbt.display.Name=ipattern:*Guts' Sword*\n"
    ).encode('utf-8')
    return out


def collect(version, *, prune_missing_faces=False):
    if version not in PACK_FORMATS:
        raise ValueError(f'Unsupported Minecraft release: {version}')
    fmt = PACK_FORMATS[version]
    legacy = isinstance(fmt, int) and fmt < 46
    files = {'pack.mcmeta': pretty_json(metadata(version)),
             'pack.png': (ROOT / 'pack.png').read_bytes()}
    # Source paths: copy arbitrary assets as well as mcd models/textures.
    # Generated modern selectors below take precedence over preview sources.
    for file in sorted(ASSETS.rglob('*')):
        if file.is_file():
            rel = file.relative_to(ROOT).as_posix()
            if legacy and '/items/' in rel:
                continue
            files[rel] = file.read_bytes()
    if legacy:
        files.update(legacy_definitions())
    else:
        files.update(modern_definitions(name_switch_supported=(version != '1.21.4')))
        # Provide a local vanilla fallback model without replacing any
        # original Minecraft model file or image. This uses Mojang's own
        # netherite sword sprite with the vanilla handheld transform.
        files['assets/mcd/models/item/compat/vanilla_netherite_sword.json'] = pretty_json({
            'parent': 'minecraft:item/handheld',
            'textures': {'layer0': 'minecraft:item/netherite_sword'},
        })
        # Keep the verified legacy CIT path as an *additional* option for
        # CIT-capable modded clients; modern vanilla selectors still take priority.
        # These wrappers also avoid duplicating any model geometry.
        files.update({path: data for path, data in legacy_definitions().items()
                      if '/custom/' in path or '/optifine/cit/' in path})
    files, actions = convert(files, version)
    if actions:
        print(f'{version}: automatically adapted {len(actions)} model/definition entries for this version')
    if prune_missing_faces:
        files, removed = prune_broken_faces(files)
        if removed:
            print(f'WARNING {version}: --prune-missing-faces removed {len(removed)} geometry/texture entries from output ZIP only')
            for action in removed:
                print('  ' + action)
    # Building is also a validation gate: never produce a misleading "success"
    # ZIP when a model points at a nonexistent custom PNG or item definition.
    # This uses the repository's existing validator; no external dependencies.
    from validate_pack import inspect
    errors = inspect(files, version)
    if errors:
        raise ValueError('Cannot build an invalid resource pack:\n' + '\n'.join(errors[:30]))
    return files


def build(version, output, *, prune_missing_faces=False):
    files = collect(version, prune_missing_faces=prune_missing_faces)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, data, compress_type=ZIP_DEFLATED, compresslevel=9)
    return len(files)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--version', choices=PACK_FORMATS)
    group.add_argument('--all', action='store_true')
    group.add_argument('--list', action='store_true')
    p.add_argument('--output-dir', type=Path, default=ROOT / 'versions')
    p.add_argument('--prune-missing-faces', action='store_true',
                   help='Optional potentially destructive model repair; only generated ZIP is affected')
    a = p.parse_args()
    if a.list:
        for name, fmt in PACK_FORMATS.items():
            print(f'{name}: {fmt}')
        return 0
    for version in PACK_FORMATS if a.all else (a.version,):
        target = a.output_dir / version / f'TextureGiftos_{version}.zip'
        count = build(version, target, prune_missing_faces=a.prune_missing_faces)
        print(f'{version}: {target} ({count} files)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
