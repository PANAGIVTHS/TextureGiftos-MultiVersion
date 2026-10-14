#!/usr/bin/env python3
"""Generate an extra resource-pack ZIP with support for selected modded item IDs.

Examples:
  python tools/build_weapon_pack.py --version 1.20.1 --weapon soulsweapons:guts_sword=guts
  python tools/build_weapon_pack.py --version 26.3 --weapon soulsweapons:guts_sword=guts --weapon mymod:big_blade=dragonslayer
  python tools/build_weapon_pack.py --all --weapons-file weapons.txt --prune-missing-faces

Input syntax: namespace:item=model_key (guts, aatrox, dragonslayer, agsheath),
or namespace:item=mcd:item/swords/model_key. Plain IDs are inferred only if
there is an unambiguous model-key match. No source files are written.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
from build_pack import PACK_FORMATS, CUSTOM_SWORDS, collect, pretty_json, nested_model

ROOT = Path(__file__).resolve().parent.parent
KEYS = {name: (f'swords/{name}', code) for name, code in CUSTOM_SWORDS}
KEYS['guts_sword'] = KEYS['guts']
KEYS['dragon_slayer'] = KEYS['dragonslayer']
IDENT = re.compile(r'^[a-z0-9_.-]+:[a-z0-9_./-]+$')


def parse_weapons(raw):
    result = {}
    for value in raw:
        item, sep, key = value.partition('=')
        item = item.strip()
        if not IDENT.fullmatch(item):
            raise ValueError(f'Invalid item ID {item!r}; expected namespace:item')
        if not sep:
            key = item.split(':', 1)[1].rsplit('/', 1)[-1]
        key = key.strip().removeprefix('mcd:item/').removeprefix('swords/')
        if key not in KEYS:
            raise ValueError(f'Unknown model {key!r} for {item}. Use item=guts|aatrox|agsheath|dragonslayer')
        if item in result and result[item] != KEYS[key]:
            raise ValueError(f'Conflicting models for {item}')
        result[item] = KEYS[key]
    if not result:
        raise ValueError('Provide at least one --weapon or --weapons-file entry')
    return result


def modern_definition(item, path, code, version):
    # 1.21.4 lacks the custom_name selector. CustomModelData works on all
    # modern versions. On 1.21.5+ a matching custom name also selects it.
    namespace, item_name = item.split(':', 1)
    fallback = {'type': 'minecraft:model', 'model': f'{namespace}:item/{item_name}'}
    if version != '1.21.4':
        names = [item.split(':', 1)[1], item.split(':', 1)[1].replace('_', ' ').title()]
        # Preserve fallback for other names and other numeric IDs.
        fallback = {'type': 'minecraft:select', 'property': 'minecraft:component',
                    'component': 'minecraft:custom_name',
                    'cases': [{'when': n, 'model': nested_model(path)} for n in dict.fromkeys(names)],
                    'fallback': fallback}
    return {'model': {'type': 'minecraft:range_dispatch',
                      'property': 'minecraft:custom_model_data',
                      'entries': [{'threshold': code, 'model': nested_model(path)},
                                  {'threshold': code + 1, 'model': fallback}],
                      'fallback': fallback}}


def add_weapons(files, version, weapons):
    legacy = version in PACK_FORMATS and isinstance(PACK_FORMATS[version], int) and PACK_FORMATS[version] < 46
    for item, (path, code) in weapons.items():
        namespace, item_name = item.split(':', 1)
        if legacy:
            # CIT (OptiFine / CIT Resewn / Forge CIT) is required for arbitrary
            # modded items. Vanilla 1.20.x has no global CMD model hook.
            model_ref = f'minecraft:item/custom/{path}'
            base = f'assets/minecraft/optifine/cit/texturegiftos/extra_{namespace}_{item_name.replace("/", "_")}'
            files[base + '_cmd.properties'] = (f'type=item\nitems={item}\nmodel={model_ref}\nnbt.CustomModelData={code}\n').encode()
            files[base + '_name.properties'] = (f'type=item\nitems={item}\nmodel={model_ref}\nnbt.display.Name=ipattern:*{item_name.replace("_", " ")}*\n').encode()
        else:
            key = f'assets/{namespace}/items/{item_name}.json'
            if key in files:
                raise ValueError(f'Generated item definition would overwrite existing {key}')
            files[key] = pretty_json(modern_definition(item, path, code, version))
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
    p.add_argument('--weapon', action='append', default=[], help='namespace:item=model; repeat as needed')
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
