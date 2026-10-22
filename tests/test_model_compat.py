"""Regression tests for source-preserving model migrations. Run with unittest."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from model_compat import convert


def encode(value):
    return json.dumps(value).encode('utf-8')


class ModelConversionTests(unittest.TestCase):
    def test_shade_false_is_migrated_without_geometry_changes(self):
        name = 'assets/mcd/models/item/swords/old_sword.json'
        model = {'textures': {'0': 'minecraft:block/stone'},
                 'elements': [{'from': [0, 1, 2], 'to': [3, 4, 5],
                               'shade': False, 'faces': {'up': {'texture': '#0'}}}]}
        raw = encode(model)
        output, log = convert({name: raw}, '26.3')
        self.assertEqual(raw, encode(model))
        updated = json.loads(output[name])
        self.assertEqual(updated['elements'][0]['from'], model['elements'][0]['from'])
        self.assertEqual(updated['elements'][0]['to'], model['elements'][0]['to'])
        self.assertEqual(updated['elements'][0]['faces'], model['elements'][0]['faces'])
        self.assertNotIn('shade', updated['elements'][0])
        self.assertEqual(updated['elements'][0]['shade_direction_override'], 'up')
        self.assertIn('assets/mcd/items/swords/old_sword.json', output)
        self.assertGreater(len(log), 0)

    def test_shade_true_removed(self):
        name = 'assets/mcd/models/item/example.json'
        files = {name: encode({'elements': [{'shade': True, 'from': [1, 2, 3]}]})}
        out, _ = convert(files, '26.3')
        self.assertNotIn('shade', json.loads(out[name])['elements'][0])

    def test_native_modern_item_definitions_are_preserved(self):
        name = 'assets/mcd/models/item/swords/aatrox.json'
        item = 'assets/mcd/items/swords/aatrox.json'
        files = {name: encode({'elements': []}), item: encode({'model': {'type':'minecraft:empty'}})}
        out, actions = convert(files, '26.3')
        self.assertEqual(out, files)
        self.assertEqual(actions, [])

    def test_old_overrides_are_promoted_and_preserve_base(self):
        name = 'assets/minecraft/models/item/example.json'
        legacy = {'parent': 'minecraft:item/generated',
                  'textures': {'layer0': 'minecraft:item/stick'},
                  'overrides': [
                      {'predicate': {'custom_model_data': 12},
                       'model': 'mcd:item/swords/guts'},
                      {'predicate': {'custom_model_data': 14},
                       'model': 'mcd:item/swords/aatrox'}]}
        out, _ = convert({name: encode(legacy)}, '26.3')
        base = json.loads(out[name])
        self.assertEqual(base['parent'], legacy['parent'])
        self.assertEqual(base['textures'], legacy['textures'])
        self.assertNotIn('overrides', base)
        model = json.loads(out['assets/minecraft/items/example.json'])['model']
        self.assertEqual([x['threshold'] for x in model['entries']], [12, 14, 15])
        self.assertEqual(model['fallback']['model'], 'minecraft:item/example')

    def test_unsupported_predicate_is_not_silently_dropped(self):
        name = 'assets/minecraft/models/item/example.json'
        files = {name: encode({'overrides': [
            {'predicate': {'pulling': 1}, 'model': 'minecraft:item/bow_pulling_1'}]})}
        with self.assertRaisesRegex(ValueError, 'manual conversion'):
            convert(files, '26.3')

    def test_old_versions_get_inline_texture_strings(self):
        name = 'assets/mcd/models/item/swords/demo.json'
        raw = encode({'textures': {'layer0': {'sprite': 'mcd:item/swords/demo'}}})
        out, _ = convert({name: raw}, '1.21.11')
        self.assertEqual(json.loads(out[name])['textures']['layer0'], 'mcd:item/swords/demo')
        self.assertEqual(json.loads(raw)['textures']['layer0']['sprite'], 'mcd:item/swords/demo')

    def test_future_only_render_features_fail_on_old_versions(self):
        name = 'assets/mcd/models/item/swords/demo.json'
        raw = encode({'textures': {'layer0': {
            'sprite': 'mcd:item/swords/demo', 'force_translucent': True}}})
        with self.assertRaisesRegex(ValueError, 'force'):
            convert({name: raw}, '1.21.11')

    def test_raw_files_remain_unmodified(self):
        name = 'assets/mcd/models/item/swords/demo.json'
        original = {name: encode({'elements': [{'shade': False}]})}
        saved = original.copy()
        convert(original, '26.3')
        self.assertEqual(saved, original)


class BrokenPackRepairTests(unittest.TestCase):
    def test_missing_parent_with_local_elements_is_removed_from_copy(self):
        name = 'assets/mcd/models/item/swords/aatrox.json'
        raw = encode({'parent': 'aatrox:custom/aatrox_sword',
                      'textures': {'particle': 'minecraft:block/obsidian'},
                      'elements': [{'from': [0,0,0], 'to': [16,16,16],
                                    'faces': {'up': {'texture': '#particle'}}}]})
        files = {name: raw}
        out, log = convert(files, '26.3')
        self.assertNotIn('parent', json.loads(out[name]))
        self.assertEqual(files[name], raw)
        self.assertTrue(any('nonexistent parent' in msg for msg in log))

    def test_existing_custom_parent_is_not_removed(self):
        name = 'assets/mcd/models/item/swords/a.json'
        parent = 'assets/mcd/models/item/swords/parent.json'
        files = {name: encode({'parent': 'mcd:item/swords/parent',
                               'elements': [{'faces': {'up': {'texture': '#x'}}}]}),
                 parent: encode({'textures': {'x': 'minecraft:block/stone'}})}
        out, log = convert(files, '26.3')
        self.assertEqual(json.loads(out[name])['parent'], 'mcd:item/swords/parent')
        self.assertEqual(len(json.loads(out[name])['elements'][0]['faces']), 1)

    def test_undefined_face_is_omitted_without_deleting_element(self):
        name = 'assets/mcd/models/item/swords/dragonslayer.json'
        original = {'textures': {'valid': 'minecraft:block/stone'},
                    'elements': [{'from':[1,2,3], 'to':[4,5,6],
                                  'faces': {'up': {'texture': '#missing'},
                                            'down': {'texture': '#valid'}}}]}
        files = {name: encode(original)}
        out, log = convert(files, '26.3')
        result = json.loads(out[name])
        self.assertEqual(result['elements'][0]['faces'], {'down': {'texture': '#valid'}})
        self.assertEqual(result['elements'][0]['from'], [1,2,3])
        self.assertEqual(json.loads(files[name]), original)
        self.assertTrue(any('omitted 1 faces' in msg for msg in log))

    def test_duplicate_select_cases_removed_in_nested_fallback(self):
        name = 'assets/minecraft/items/netherite_sword.json'
        aatrox = {'type':'minecraft:model', 'model':'mcd:item/swords/aatrox'}
        selector = {'model': {'type': 'minecraft:range_dispatch',
            'property': 'minecraft:custom_model_data', 'entries': [],
            'fallback': {'type': 'minecraft:select', 'property': 'minecraft:component',
                         'component': 'minecraft:custom_name',
                         'cases': [{'when': "Guts' Sword", 'model': aatrox},
                                   {'when': "Guts' Sword", 'model': aatrox}],
                         'fallback': aatrox}}}
        out, log = convert({name: encode(selector)}, '26.3')
        cases = json.loads(out[name])['model']['fallback']['cases']
        self.assertEqual(len(cases), 1)
        self.assertTrue(any('duplicate' in msg for msg in log))

    def test_conflicting_duplicate_select_cases_fails(self):
        name = 'assets/minecraft/items/netherite_sword.json'
        data = {'model': {'type': 'minecraft:select',
            'cases': [{'when': 'Aatrox', 'model': {'type': 'minecraft:empty'}},
                      {'when': 'Aatrox', 'model': {'type': 'minecraft:model', 'model':'mcd:item/swords/aatrox'}}]}}
        with self.assertRaisesRegex(ValueError, 'conflicting select cases'):
            convert({name: encode(data)}, '26.3')


class AtlasCompatibilityTests(unittest.TestCase):
    def test_dragonslayer_mixed_atlases_move_only_generated_item_sprites(self):
        model = 'assets/mcd/models/item/swords/dragonslayer.json'
        image = 'assets/mcd/textures/item/swords/handle_wraps.png'
        anim = image + '.mcmeta'
        source = {'textures': {
            '0': 'minecraft:block/stone',
            '1': 'mcd:item/swords/handle_wraps',
            'particle': 'minecraft:block/stone',
        }, 'elements': [{'from': [0, 0, 0], 'to': [8, 8, 8],
                         'faces': {'north': {'texture': '#1', 'uv': [0,0,16,16]}}}]}
        files = {model: encode(source), image: b'fake-png', anim: b'{"animation":{"frametime":3}}'}
        output, actions = convert(files, '26.3')
        new_image = 'assets/mcd/textures/block/texturegiftos_compat/item/swords/handle_wraps.png'
        self.assertEqual(output[new_image], files[image])
        self.assertEqual(output[new_image+'.mcmeta'], files[anim])
        self.assertEqual(output[image], files[image])
        self.assertEqual(output[model] != files[model], True)
        updated = json.loads(output[model])
        self.assertEqual(updated['textures']['1'],
                         'mcd:block/texturegiftos_compat/item/swords/handle_wraps')
        self.assertEqual(updated['elements'], source['elements'])
        self.assertEqual(updated['textures']['0'], 'minecraft:block/stone')
        self.assertTrue(any('block atlas' in x for x in actions))

    def test_dragonslayer_original_texture_ids_remain_in_old_pack(self):
        model = 'assets/mcd/models/item/swords/dragonslayer.json'
        img = 'assets/mcd/textures/item/swords/a.png'
        raw = encode({'textures': {'0':'block/stone','1':'mcd:item/swords/a'}})
        output, _ = convert({model:raw, img:b'png'}, '1.21.10')
        self.assertEqual(output[model], raw)
        self.assertNotIn('assets/mcd/textures/block/texturegiftos_compat/item/swords/a.png',output)

    def test_reject_mixed_atlas_with_unavailable_item_texture(self):
        model = 'assets/mcd/models/item/swords/dragonslayer.json'
        raw = encode({'textures': {'0':'minecraft:block/anvil','1':'minecraft:item/diamond'}})
        with self.assertRaisesRegex(ValueError,'not packaged'):
            convert({model:raw}, '26.3')

    def test_does_not_rewrite_single_atlas_models(self):
        model = 'assets/mcd/models/item/swords/aatrox.json'
        raw = encode({'textures': {'0':'minecraft:block/anvil','1':'minecraft:block/stone'}})
        out, actions = convert({model:raw}, '26.3')
        self.assertEqual(out[model],raw)
        self.assertFalse(any('block atlas' in x for x in actions))

    def test_modern_object_texture_preserved_while_switching_atlas(self):
        model = 'assets/mcd/models/item/dragon.json'
        img = 'assets/mcd/textures/item/swords/handle_wraps.png'
        raw = encode({'textures': {'0':{'sprite':'minecraft:block/stone'},
                                   '1':{'sprite':'mcd:item/swords/handle_wraps','force_translucent':True}}})
        output, _ = convert({model:raw,img:b'png'}, '26.3')
        texture = json.loads(output[model])['textures']['1']
        self.assertEqual(texture['sprite'], 'mcd:block/texturegiftos_compat/item/swords/handle_wraps')
        self.assertEqual(texture['force_translucent'],True)


if __name__ == '__main__':
    unittest.main()
