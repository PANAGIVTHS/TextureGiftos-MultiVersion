#!/usr/bin/env python3
"""Version-specific, source-preserving Minecraft model compatibility conversion.

Operate on an in-memory ``{archive_path: bytes}`` mapping.  The originals in
assets/ are never written or renamed.  Never delete model elements/faces to
make a build pass: an unconvertible case must be reported, not silently hidden.
"""
from __future__ import annotations

import copy
import json


def _json(doc):
    return (json.dumps(doc, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def _modern(version):
    return version == '26.3' or version.startswith('26.') or (
        version.startswith('1.21.') and int(version.split('.')[-1]) >= 4
    )


def _at_least(version, release):
    """Compare supported release numbers; 26.x is later than all 1.x versions."""
    return tuple(int(part) for part in version.split('.')) >= tuple(int(part) for part in release.split('.'))



def _migrate_old_overrides(path, doc):
    """Translate simple legacy CustomModelData predicates to >=1.21.4.

    Complex predicates (damage, pulling, etc.) cannot be faithfully expressed
    as a numeric-only selector, so fail explicitly instead of discarding them.
    """
    entries = []
    for index, override in enumerate(doc.get('overrides', [])):
        predicate = override.get('predicate') if isinstance(override, dict) else None
        if not isinstance(predicate, dict) or set(predicate) != {'custom_model_data'}:
            raise ValueError(f'{path}: override {index} has predicates requiring manual conversion: {predicate}')
        code, target = predicate['custom_model_data'], override.get('model')
        if isinstance(code, bool) or not isinstance(code, (int, float)) or not isinstance(target, str):
            raise ValueError(f'{path}: invalid CustomModelData override {index}')
        entries.append((code, target))
    if not entries:
        return None
    if len({code for code, _ in entries}) != len(entries):
        raise ValueError(f'{path}: repeated CustomModelData thresholds need explicit handling')
    entries.sort(key=lambda entry: entry[0])
    # Preserve the model's original base geometry, parent, and texture refs.
    # It remains under models/item, but will no longer carry obsolete overrides.
    namespace = path.split('/')[1]
    rel = path.split('/models/', 1)[1].removesuffix('.json')
    fallback = {'type': 'minecraft:model', 'model': f'{namespace}:{rel}'}
    result = {
        'type': 'minecraft:range_dispatch',
        'property': 'minecraft:custom_model_data',
        'entries': [
            {'threshold': code, 'model': {'type': 'minecraft:model', 'model': target}}
            for code, target in entries
        ] + [{'threshold': entries[-1][0] + 1, 'model': fallback}],
        'fallback': fallback,
    }
    return {'model': result}


def _fix_duplicate_cases(node, path, changes):
    """Deduplicate any nested `minecraft:select` case, not just generated names.

    Minecraft can reject a whole item definition if two cases have the same
    `when` value. Never discard conflicting cases silently.
    """
    if isinstance(node, list):
        for child in node:
            _fix_duplicate_cases(child, path, changes)
        return
    if not isinstance(node, dict):
        return
    if node.get('type') in ('minecraft:select', 'select') and isinstance(node.get('cases'), list):
        unique, seen, removed = [], {}, 0
        for case in node['cases']:
            if not isinstance(case, dict) or 'when' not in case:
                unique.append(case)
                continue
            when = case['when']
            values = when if isinstance(when, list) else [when]
            kept = []
            for value in values:
                key = json.dumps(value, sort_keys=True, ensure_ascii=False)
                if key in seen:
                    if seen[key] != case.get('model'):
                        raise ValueError(f'{path}: conflicting select cases for {value!r}')
                    removed += 1
                else:
                    seen[key] = case.get('model')
                    kept.append(value)
            if kept:
                clean_case = dict(case)
                clean_case['when'] = kept if isinstance(when, list) else kept[0]
                unique.append(clean_case)
        if removed:
            node['cases'] = unique
            changes.append(f'{path}: removed {removed} duplicate item-selector cases')
    for child in node.values():
        _fix_duplicate_cases(child, path, changes)


def _repair_model_refs(out, changes):
    """Fix demonstrably invalid source references in generated model copies.

    - A non-vanilla parent that isn't in the archive is removed only when the
      child explicitly has its own elements. It may lose unknown inherited
      transforms but keeps all locally specified geometry.
    - Face texture variables absent from both local and *packaged* parent
      textures are removed. Missing faces cannot be reconstructed automatically;
      removing them prevents missing-texture squares while retaining elements.
    """
    for path, raw in sorted(list(out.items())):
        if not (path.startswith('assets/') and '/models/' in path and path.endswith('.json')):
            continue
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            continue
        original = copy.deepcopy(doc)
        parent = doc.get('parent')
        if isinstance(parent, str):
            ns, sep, rel = parent.partition(':')
            if not sep:
                ns, rel = 'minecraft', ns
            parent_path = f'assets/{ns}/models/{rel}.json'
            if ns != 'minecraft' and parent_path not in out and doc.get('elements'):
                del doc['parent']
                changes.append(f'{path}: removed nonexistent parent {parent!r} (own elements preserved)')

        # Resolve texture variables through parents that are actually in the
        # pack. A vanilla parent may contribute unknown texture aliases, so
        # conservatively skip repair for such unresolved inheritance.
        aliases = dict(doc.get('textures', {}))
        cur = doc
        visited = {path}
        uncertain_vanilla_parent = False
        while isinstance(cur.get('parent'), str):
            ref = cur['parent']
            ns, sep, rel = ref.partition(':')
            if not sep:
                ns, rel = 'minecraft', ns
            parent_path = f'assets/{ns}/models/{rel}.json'
            if parent_path in visited:
                break
            visited.add(parent_path)
            if parent_path not in out:
                uncertain_vanilla_parent = (ns == 'minecraft')
                break
            cur = json.loads(out[parent_path])
            for name, texture in cur.get('textures', {}).items():
                aliases.setdefault(name, texture)

        def has_texture(key):
            seen = set()
            while key in aliases:
                if key in seen:
                    return False
                seen.add(key)
                value = aliases[key]
                if not isinstance(value, str):
                    # Modern object-format textures are resolved by the game.
                    return True
                if not value.startswith('#'):
                    return True
                key = value[1:]
            return uncertain_vanilla_parent

        removed = 0
        for element in doc.get('elements', []):
            if not isinstance(element, dict):
                continue
            faces = element.get('faces')
            if not isinstance(faces, dict):
                continue
            for direction, face in list(faces.items()):
                ref = face.get('texture') if isinstance(face, dict) else None
                if isinstance(ref, str) and ref.startswith('#') and not has_texture(ref[1:]):
                    del faces[direction]
                    removed += 1
        if removed:
            changes.append(f'{path}: omitted {removed} faces with unresolved #texture variables (elements untouched)')
        if doc != original:
            out[path] = _json(doc)

def _fix_mixed_item_block_atlases(out, version, changes):
    """Minecraft 1.21.11+ forbids mixing blocks/items atlases in one model.

    For a mixed model built from vanilla block sprites and *packaged* custom
    item sprites, duplicate the custom PNGs into the block-texture directory
    and rewrite only the generated JSON texture IDs.  All geometry, UVs,
    animation frame indices, and original files remain unchanged.

    This is NOT a general strategy for relocating vanilla textures.  A missing
    custom PNG or non-packaged item sprite is refused, rather than producing a
    superficially valid, still-broken pack.
    """
    if not _at_least(version, '1.21.11'):
        return

    for path in sorted(list(out)):
        if not (path.startswith('assets/') and '/models/' in path and path.endswith('.json')):
            continue
        doc = json.loads(out[path])
        if not isinstance(doc, dict) or not isinstance(doc.get('textures'), dict):
            continue
        textures = doc['textures']
        block_entries, item_entries = [], []
        for key, value in textures.items():
            sprite = value.get('sprite') if isinstance(value, dict) else value
            if not isinstance(sprite, str) or sprite.startswith('#'):
                continue
            ns, sep, texture = sprite.partition(':')
            if not sep:
                ns, texture = 'minecraft', ns
            if texture.startswith('block/'):
                block_entries.append((key, ns, texture))
            elif texture.startswith('item/'):
                item_entries.append((key, ns, texture))

        if not (block_entries and item_entries):
            continue

        for key, namespace, texture in item_entries:
            source_file = f'assets/{namespace}/textures/{texture}.png'
            if source_file not in out:
                raise ValueError(
                    f'{path}: mixed block/item texture atlases; cannot move '
                    f'{namespace}:{texture}, because {source_file} is not packaged'
                )
            # Place a COPY of each item sprite into the standard block atlas.
            # Namespace and original path are encoded to avoid accidental
            # collisions with existing assets.
            block_texture = 'block/texturegiftos_compat/' + texture
            dst_file = f'assets/{namespace}/textures/{block_texture}.png'
            dst_meta = dst_file + '.mcmeta'
            src_meta = source_file + '.mcmeta'
            if dst_file in out and out[dst_file] != out[source_file]:
                raise ValueError(f'{path}: destination texture conflicts: {dst_file}')
            out[dst_file] = out[source_file]
            if src_meta in out:
                if dst_meta in out and out[dst_meta] != out[src_meta]:
                    raise ValueError(f'{path}: destination animation metadata conflicts: {dst_meta}')
                out[dst_meta] = out[src_meta]
            new_sprite = f'{namespace}:{block_texture}'
            old = textures[key]
            if isinstance(old, dict):
                textures[key] = {**old, 'sprite': new_sprite}
            else:
                textures[key] = new_sprite
            changes.append(
                f'{path}: moved {namespace}:{texture} into the block atlas '
                f'({dst_file}; original preserved)'
            )
        out[path] = _json(doc)


def convert(files, version):
    """Return (converted files, changes). Inputs, source and geometry unchanged.

    Converts legacy item override selectors; adapts pre-26.3 ``shade`` values;
    downgrades 26.1 object texture declarations for older targets; generates
    missing direct item definitions for mcd models on 1.21.4+.
    """
    out = dict(files)
    changes = []
    modern = _modern(version)
    for path, raw in sorted(files.items()):
        if not (path.startswith('assets/') and '/models/' in path and path.endswith('.json')):
            continue
        original = json.loads(raw)
        if not isinstance(original, dict):
            raise ValueError(f'{path}: model must be a JSON object')
        doc = copy.deepcopy(original)
        if modern and isinstance(doc.get('overrides'), list) and doc['overrides']:
            modern_name = path.replace('/models/item/', '/items/', 1)
            definition = _migrate_old_overrides(path, doc)
            if modern_name in out:
                # Collision detection prevents a generated selector from silently
                # replacing a user's more complex source definition.
                raise ValueError(f'{path}: cannot import legacy overrides: {modern_name} already exists')
            out[modern_name] = _json(definition)
            del doc['overrides']
            changes.append(f'{path}: migrated legacy CustomModelData overrides to {modern_name}')
        for idx, element in enumerate(doc.get('elements', [])):
            if not isinstance(element, dict):
                continue
            if _at_least(version, '26.3'):
                if 'shade' in element:
                    shade = element.pop('shade')
                    if not isinstance(shade, bool):
                        raise ValueError(f'{path}: element {idx} shade must be true/false')
                    if shade is False:
                        if element.get('shade_direction_override', 'up') != 'up':
                            raise ValueError(f'{path}: conflicting shade settings in element {idx}')
                        element['shade_direction_override'] = 'up'
                    changes.append(f'{path}: converted element {idx} legacy shade={shade}')
            elif 'shade_direction_override' in element:
                direction = element.pop('shade_direction_override')
                if direction == 'up':
                    element['shade'] = False
                    changes.append(f'{path}: converted element {idx} shade_direction_override=up')
                else:
                    raise ValueError(f'{path}: element {idx} shade_direction_override={direction!r} cannot be represented before 26.3')
        # Minecraft 26.1 added object-format texture definitions with
        # optional force_translucent; older clients need inline sprite strings.
        # Strings *remain valid* on 26.1+, so don't rewrite them unnecessarily.
        if not _at_least(version, '26.1'):
            for key, value in doc.get('textures', {}).items():
                if isinstance(value, dict):
                    sprite = value.get('sprite')
                    if not isinstance(sprite, str):
                        raise ValueError(f'{path}: texture {key} has no sprite ID')
                    if value.get('force_translucent'):
                        raise ValueError(f'{path}: texture {key} forces translucency not available in {version}')
                    doc['textures'][key] = sprite
                    changes.append(f'{path}: converted texture {key} to old string form')
        if doc != original:
            out[path] = _json(doc)
    # Item definitions can include nested selectors, e.g. numeric CMD whose
    # fallback is a name selector. Check all levels for ambiguous duplicate keys.
    for path, raw in list(out.items()):
        if not (path.startswith('assets/') and '/items/' in path and path.endswith('.json')):
            continue
        doc = json.loads(raw)
        before = copy.deepcopy(doc)
        _fix_duplicate_cases(doc, path, changes)
        if doc != before:
            out[path] = _json(doc)
    _repair_model_refs(out, changes)
    _fix_mixed_item_block_atlases(out, version, changes)
    if modern:
        for path in sorted(out):
            if not path.startswith('assets/mcd/models/item/') or not path.endswith('.json'):
                continue
            dest = path.replace('/models/item/', '/items/', 1)
            if dest not in out:
                ref = 'mcd:' + path[len('assets/mcd/models/'):-5]
                out[dest] = _json({'model': {'type': 'minecraft:model', 'model': ref}})
                changes.append(f'{dest}: generated direct item-model definition')
    return out, changes
