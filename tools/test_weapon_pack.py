#!/usr/bin/env python3
"""Quick regression test for generated modded weapon name/model rules."""
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile

from build_weapon_pack import add_weapons, parse_weapons, sword_name_rules
from build_pack import collect

TEST_ID = 'soulsweapons:guts_sword'
assert TEST_ID in parse_weapons([TEST_ID])
assert TEST_ID in parse_weapons([TEST_ID + '=guts'])
assert ('Dragonslayer', 'swords/dragonslayer') in sword_name_rules()

for version in ('1.20.1', '1.21.3', '1.21.4', '1.21.5', '26.3'):
    baseline = collect(version)
    original = dict(baseline)
    add_weapons(baseline, version, {TEST_ID: None})
    assert all(baseline[key] == value for key, value in original.items()), version
    if version in ('1.20.1', '1.21.3'):
        extras = [baseline[k].decode('utf8') for k in baseline
                  if 'extra_soulsweapons_guts_sword' in k]
        assert any('nbt.display.Name=ipattern:*Dragonslayer*' in prop and
                   'model=item/custom/swords/dragonslayer' in prop for prop in extras), version
        assert any('nbt.CustomModelData=123004' in prop and
                   'model=item/custom/swords/dragonslayer' in prop for prop in extras), version
    else:
        definition = json.loads(baseline['assets/soulsweapons/items/guts_sword.json'])
        model = definition['model']
        assert model['type'] == 'minecraft:range_dispatch'
        assert any(e['threshold'] == 123004 and
                   e['model']['model'] == 'mcd:item/swords/dragonslayer'
                   for e in model['entries']), version
        if version != '1.21.4':
            selector = model['fallback']
            assert selector['component'] == 'minecraft:custom_name'
            assert any(e['when'] == 'Dragonslayer' and
                       e['model']['model'] == 'mcd:item/swords/dragonslayer'
                       for e in selector['cases']), version
print('PASS: modded weapon name/CMD rules verified in 5 representative Minecraft versions.')
