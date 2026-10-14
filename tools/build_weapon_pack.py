#!/usr/bin/env python3
"""Generate an extra resource-pack ZIP with support for selected modded item IDs.

Examples:
  python tools/build_weapon_pack.py --version 1.20.1 --weapon soulsweapons:guts_sword=guts
  python tools/build_weapon_pack.py --version 26.3 --weapon soulsweapons:guts_sword=guts --weapon mymod:big_blade=dragonslayer
  python tools/build_weapon_pack.py --all --weapons-file weapons.txt --prune-missing-faces

Input syntax: namespace:item=model_key (guts, aatrox, dragonslayer, agsheath),
or simply namespace:item. Every registered modded item receives ALL the
existing sword name and CustomModelData rules (not just one model). The
optional =model_key is accepted for compatibility with older commands.
No source files are written.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
from build_pack import PACK_FORMATS, CUSTOM_SWORDS, NAME_RULES, collect, pretty_json, nested_model, numeric_model_selector

ROOT = Path(__file__).resolve().parent.parent
KEYS = {name: (f'swords/{name}', code) for name, code in CUSTOM_SWORDS}
KEYS['guts_sword'] = KEYS['guts']
KEYS['dragon_slayer'] = KEYS['dragonslayer']
IDENT = re.compile(r'^[a-z0-9_.-]+:[a-z0-9_./-]+$')


def parse_weapons(raw):
    """Parse registered item IDs; old =model_key syntax is optional.

    Earlier versions applied one model to one item. All requested IDs now
    receive the same name and numeric selections as a Netherite Sword.
    """
    result = {}
    for value in raw:
        item, sep, key = value.partition('=')
        item = item.strip()
        if not IDENT.fullmatch(item):
            raise ValueError(f'Invalid item ID {item!r}; expected namespace:item')
        key = key.strip().removeprefix('mcd:item/').removeprefix('swords/') if sep else None
        if sep and key not in KEYS:
            raise ValueError(f'Unknown legacy model hint {key!r} for {item}. '
                             'Use item ID alone or item=guts|aatrox|agsheath|dragonslayer')
        if item in result and key and result[item] and result[item] != key:
            raise ValueError(f'Conflicting model hints for {item}')
        result[item] = key or result.get(item)
    if not result:
        raise ValueError('Provide at least one --weapon or --weapons-file entry')
    return result


def sword_name_rules():
    """Reuse the exact existing Netherite Sword CIT / name rules."""
    return list(dict.fromkeys((name, path) for item, name, path in NAME_RULES
                              if item == 'netherite_sword'))


def modern_definition(item, version):
    namespace, item_name = item.split(':', 1)
    fallback = {'type': 'minecraft:model', 'model': f'{namespace}:item/{item_name}'}
    if version != '1.21.4':
        fallback = {
            'type': 'minecraft:select',
            'property': 'minecraft:component',
            'component': 'minecraft:custom_name',
            'cases': [{'when': name, 'model': nested_model(path)}
                      for name, path in sword_name_rules()],
            'fallback': fallback,
        }
    numeric = numeric_model_selector(fallback, [
        (code, f'swords/{key}') for key, code in CUSTOM_SWORDS
    ])
    return {'model': numeric}


def add_weapons(files, version, weapons):
    legacy = isinstance(PACK_FORMATS[version], int) and PACK_FORMATS[version] < 46
    for item in weapons:
        namespace, item_name = item.split(':', 1)
        if legacy:
            base = (f'assets/minecraft/optifine/cit/texturegiftos/'
                    f'extra_{namespace}_{item_name.replace("/", "_")}')
            # Unlike the old implementation, every item has all the same
            # name rules that a Netherite Sword has, regardless of its ID.
            for idx, (name, path) in enumerate(sword_name_rules()):
                model_ref = f'item/custom/{path}'
                files[f'{base}_name_{idx:02d}.properties'] = (
                    'type=item\n'
                    f'items={item}\n'
                    f'model={model_ref}\n'
                    f'nbt.display.Name=ipattern:*{name}*\n'
                ).encode('utf-8')
            # Preserve numeric CustomModelData support for all models too.
            for key, code in CUSTOM_SWORDS:
                files[f'{base}_cmd_{code}.properties'] = (
                    'type=item\n'
                    f'items={item}\n'
                    f'model=item/custom/swords/{key}\n'
                    f'nbt.CustomModelData={code}\n'
                ).encode('utf-8')
        else:
            key = f'assets/{namespace}/items/{item_name}.json'
            if key in files:
                raise ValueError(f'Generated item definition would overwrite existing {key}')
            files[key] = pretty_json(modern_definition(item, version))
    return files


def write_zip(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, 'w', compression=ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o644 << 16
            z.writestr(entry, data, compress_type=ZIP_DEFLATED, compresslevel=9)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--version', choices=PACK_FORMATS)
    g.add_argument('--all', action='store_true')
    p.add_argument('--weapon', action='append', default=[], help='namespace:item (optional legacy =model); repeat as needed')
    p.add_argument('--weapons-file', type=Path, help='One item=model per line; # comments allowed')
    p.add_argument('--output-dir', type=Path, default=ROOT / 'custom_builds')
    p.add_argument('--prune-missing-faces', action='store_true')
    args = p.parse_args()
    values = list(args.weapon)
    if args.weapons_file:
        values += [line.strip() for line in args.weapons_file.read_text(encoding='utf-8').splitlines()
                   if line.strip() and not line.lstrip().startswith('#')]
    try:
        weapons = parse_weapons(values)
    except ValueError as exc:
        p.error(str(exc))
    for version in PACK_FORMATS if args.all else [args.version]:
        files = collect(version, prune_missing_faces=args.prune_missing_faces)
        add_weapons(files, version, weapons)
        target = args.output_dir / version / f'TextureGiftos_Custom_{version}.zip'
        write_zip(target, files)
        print(f'{version}: {target} ({len(weapons)} extra items)')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
