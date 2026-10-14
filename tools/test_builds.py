#!/usr/bin/env python3
"""Automated archive and semantic smoke tests for all supported Java releases."""
import json
from pathlib import Path
from zipfile import ZipFile

from build_pack import PACK_FORMATS, ROOT, build
from validate_pack import inspect


def main():
    dist = ROOT / 'versions'
    for version in PACK_FORMATS:
        target = dist / version / f'TextureGiftos_{version}.zip'
        build(version, target)
        with ZipFile(target) as z:
            files = {name: z.read(name) for name in z.namelist()}
        errors = inspect(files, version)
        assert not errors, '\n'.join(errors)
        assert 'assets/mcd/models/item/swords/dragonslayer.json' in files
        assert 'assets/mcd/textures/item/swords/handle_wraps.png' in files
        assert 'assets/mcd/textures/item/swords/under_fix.png' in files
        assert 'assets/mcd/textures/item/swords/handle_wraps.png.mcmeta' in files
        assert all(not x.startswith(('TextureGiftos/', '.git/', 'tools/', 'dist/')) for x in files)
        if version in ('1.20.1', '1.21.3'):
            model = json.loads(files['assets/minecraft/models/item/netherite_sword.json'])
            assert [x['predicate']['custom_model_data'] for x in model['overrides']] == [123001, 123002, 123003, 123004]
            assert 'assets/minecraft/optifine/cit/texturegiftos/99_soulsweapons_guts.properties' in files
        if version in ('1.21.4', '26.3'):
            model = json.loads(files['assets/minecraft/items/netherite_sword.json'])
            assert [x['threshold'] for x in model['model']['entries']] == [123001, 123002, 123003, 123004, 123005]
            if version == '26.3':
                assert any(x['when'] == 'Dragonslayer' for x in model['model']['fallback']['cases'])
            else:
                assert model['model']['fallback'] == {'type': 'minecraft:model', 'model': 'minecraft:item/netherite_sword'}
                assert 'minecraft:component' not in json.dumps(model)
                assert 'minecraft:component' not in files['assets/minecraft/items/bow.json'].decode('utf8')
            assert 'assets/minecraft/models/item/netherite_sword.json' not in files
        print(f'PASS Minecraft Java {version}: {len(files)} files, {target.stat().st_size:,} bytes')
    print(f'PASS: {len(PACK_FORMATS)} version-specific resource packs generated and validated.')


if __name__ == '__main__':
    main()
