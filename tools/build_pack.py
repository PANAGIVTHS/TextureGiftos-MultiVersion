#!/usr/bin/env python3
"""Build installable Minecraft Java resource packs from shared TextureGiftos assets.

For Java 1.20.1-1.21.3, generate pre-1.21.4 item overrides and OptiFine/CIT
rules; for 1.21.4 onward, use data-driven item definitions. Model/texture
sources are shared. No Python dependencies outside the standard library.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'

# Release numbers are Minecraft: Java Edition (not Bedrock) versions.
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
    ('netherite_sword', "Gut's Sword", 'swords/guts'),  # old legacy typo
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


def default_item_model(id_):
    return {'type': 'minecraft:model', 'model': f'minecraft:item/{id_}'}


def named_switch(item_name, mapping):
    return {
        'model': {
            'type': 'minecraft:select', 'property': 'minecraft:component',
            'component': 'minecraft:custom_name',
            'cases': [{'when': name, 'model': nested_model(path)} for name, path in mapping],
            'fallback': default_item_model(item_name),
        }
    }


def numeric_model_selector(named, entries):
    """Keep old numeric IDs usable on 1.21.4+ using CMD's floats list.

    An explicit ending threshold restores the fallback for unrelated IDs,
    avoiding Minecraft's open-ended >= last-threshold behavior.
    """
    if not entries:
        return named
    return {
        'type': 'minecraft:range_dispatch',
        'property': 'minecraft:custom_model_data',
        'entries': [
            {'threshold': code, 'model': nested_model(path)} for code, path in entries
        ] + [{'threshold': entries[-1][0] + 1, 'model': named}],
        'fallback': named,
    }


def modern_definitions(name_switch_supported=True):
    sword_names = [(name, path) for item, name, path in NAME_RULES if item == 'netherite_sword']
    diamond_names = [(name, path) for item, name, path in NAME_RULES if item == 'diamond_sword']
    defs = {
        'netherite_sword': named_switch('netherite_sword', sword_names),
        'diamond_sword': named_switch('diamond_sword', diamond_names),
        'carrot_on_a_stick': named_switch('carrot_on_a_stick',
                [(name, path) for item, name, path in NAME_RULES if item == 'carrot_on_a_stick']),
        'ender_eye': named_switch('ender_eye',
                [(name, path) for item, name, path in NAME_RULES if item == 'ender_eye']),
    }
    if not name_switch_supported:
        # Minecraft 1.21.4 has data-driven item models but lacks the
        # minecraft:component select property (first available in 1.21.5).
        for item in defs:
            defs[item] = {'model': default_item_model(item)}
    for item, entries in (
        ('netherite_sword', [(code, f'swords/{name}') for name, code in CUSTOM_SWORDS]),
        ('diamond_sword', [(123001, 'swords/agsheath')]),
        ('carrot_on_a_stick', [(123401, 'misc/scanner_detector')]),
        ('ender_eye', [(123301, 'misc/enders_wrath')]),
    ):
        defs[item]['model'] = numeric_model_selector(defs[item]['model'], entries)
    # The original Elite Power Bow references non-existent model files. Do not
    # emit unresolved models; offer Varus instead and preserve vanilla bow states.
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
        'on_true': {'type': 'minecraft:range_dispatch', 'property': 'minecraft:use_duration',
                    'scale': 0.05,
                    'entries': [
                        {'threshold': .65, 'model': bow_state(1)},
                        {'threshold': .9, 'model': bow_state(2)},
                    ], 'fallback': bow_state(0)}
    }}
    if not name_switch_supported:
        # Name-switched Varus isn't possible with vanilla pack JSON in 1.21.4.
        defs['bow'] = {'model': default_item_model('bow')}
    return {f'assets/minecraft/items/{key}.json': pretty_json(value) for key, value in defs.items()}


def legacy_definition(item, layer, parent, overrides):
    return pretty_json({
        'parent': parent,
        'textures': {'layer0': f'minecraft:item/{layer}'},
        'overrides': [{'predicate': {'custom_model_data': code},
                       'model': f'minecraft:item/custom/{path}'} for code, path in overrides],
    })


def legacy_definitions():
    out = {}
    for source in sorted((ASSETS / 'mcd/models/item').rglob('*.json')):
        rel = source.relative_to(ASSETS / 'mcd/models/item').with_suffix('')
        item_ref = rel.as_posix()
        # Wrapper parents inherit the geometry, transforms and textures from
        # the modern model, avoiding duplicate divergent editable assets.
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
    # Older clients don't support vanilla item-name predicates. CIT files are
    # optional: they only activate with OptiFine or a compatible CIT mod.
    for i, (item, name, target) in enumerate(NAME_RULES):
        out[f'assets/minecraft/optifine/cit/texturegiftos/{i:02d}_{target.replace("/", "_")}.properties'] = (
            'type=item\n'
            f'items=minecraft:{item}\n'
            f'model=item/custom/{target}\n'
            f'nbt.display.Name=ipattern:*{name}*\n'
        ).encode('utf-8')
    # Optional compatibility for the modded Guts Sword on CIT-capable clients.
    out['assets/minecraft/optifine/cit/texturegiftos/99_soulsweapons_guts.properties'] = (
        'type=item\nitems=soulsweapons:guts_sword\n'
        'model=item/custom/swords/guts\n'
        "nbt.display.Name=ipattern:*Guts' Sword*\n"
    ).encode('utf-8')
    return out


def collect(version):
    if version not in PACK_FORMATS:
        raise ValueError(f'Unsupported Minecraft release: {version}')
    legacy = PACK_FORMATS[version] < 46 if isinstance(PACK_FORMATS[version], int) else False
    files = {'pack.mcmeta': pretty_json(metadata(version)),
             'pack.png': (ROOT / 'pack.png').read_bytes()}
    # Retain a single authoritative model/texture source across all formats.
    for file in sorted((ASSETS / 'mcd').rglob('*')):
        if file.is_file():
            # Modern 'items/' declarations do not exist on older clients.
            if legacy and '/items/' in file.as_posix():
                continue
            files[file.relative_to(ROOT).as_posix()] = file.read_bytes()
    files.update(legacy_definitions() if legacy else modern_definitions(name_switch_supported=(version != '1.21.4')))
    return files


def build(version, output):
    files = collect(version)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            # Stable timestamp and permissions prevent every version ZIP from
            # changing on each build even when the source is unchanged.
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, data, compress_type=ZIP_DEFLATED, compresslevel=9)
    return len(files)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--version', choices=PACK_FORMATS)
    group.add_argument('--all', action='store_true', help='Build one ZIP into each version folder')
    group.add_argument('--list', action='store_true', help='List supported releases')
    p.add_argument('--output-dir', type=Path, default=ROOT / 'versions')
    a = p.parse_args()
    if a.list:
        for k, v in PACK_FORMATS.items():
            print(f'{k}: {v}')
        return 0
    for version in PACK_FORMATS if a.all else (a.version,):
        target = a.output_dir / version / f'TextureGiftos_{version}.zip'
        n = build(version, target)
        print(f'{version}: {target} ({n} files)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
