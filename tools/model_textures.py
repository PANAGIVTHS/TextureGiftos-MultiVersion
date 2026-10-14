#!/usr/bin/env python3
"""Resolve model texture aliases; safely audit and optionally prune broken faces.

Does not assume that missing `minecraft:` textures are errors: vanilla resources
may supply them. Non-Minecraft namespaces must be bundled in this pack.
"""
from __future__ import annotations

import json
from pathlib import Path


def asset_path(ref, kind='textures'):
    ns, separator, path = ref.partition(':')
    if not separator:
        ns, path = 'minecraft', ns
    return f'assets/{ns}/{kind}/{path}.png'


def model_path(ref):
    ns, separator, path = ref.partition(':')
    if not separator:
        ns, path = 'minecraft', ns
    return f'assets/{ns}/models/{path}.json'


def loaded_models(files):
    result = {}
    for name, data in files.items():
        if name.startswith('assets/') and '/models/' in name and name.endswith('.json'):
            try:
                doc = json.loads(data)
                if isinstance(doc, dict):
                    result[name] = doc
            except (ValueError, UnicodeDecodeError):
                pass  # JSON errors are reported by validate_pack.py.
    return result


def inherited_textures(name, models, visited=frozenset()):
    if name in visited or name not in models:
        return {}
    doc = models[name]
    parent = doc.get('parent')
    bindings = inherited_textures(model_path(parent), models, visited | {name}) if isinstance(parent, str) else {}
    if isinstance(doc.get('textures'), dict):
        bindings.update(doc['textures'])
    return bindings


def rendered_elements(name, models, visited=frozenset()):
    if name in visited or name not in models:
        return []
    doc = models[name]
    if 'elements' in doc:
        return doc['elements'] if isinstance(doc['elements'], list) else []
    parent = doc.get('parent')
    return rendered_elements(model_path(parent), models, visited | {name}) if isinstance(parent, str) else []


def resolve_texture(ref, bindings, files):
    """Return a human-readable error for a face / particle reference, or None."""
    visited = set()
    while isinstance(ref, str) and ref.startswith('#'):
        key = ref[1:]
        if key in visited:
            return f'cyclic texture alias {ref}'
        visited.add(key)
        if key not in bindings:
            return f'undefined texture variable {ref}'
        ref = bindings[key]
    if not isinstance(ref, str) or not ref:
        return f'invalid texture reference {ref!r}'
    path = asset_path(ref)
    if not path.startswith('assets/minecraft/') and path not in files:
        return f'missing custom PNG {ref} ({path})'
    return None


def used_bindings(elements, bindings):
    """Follow alias chains used by visible faces, plus particle textures."""
    used = set()
    pending = []
    for element in elements:
        if isinstance(element, dict):
            for face in element.get('faces', {}).values():
                if isinstance(face, dict):
                    pending.append(face.get('texture'))
    if 'particle' in bindings:
        pending.append('#particle')
    while pending:
        ref = pending.pop()
        if isinstance(ref, str) and ref.startswith('#'):
            key = ref[1:]
            if key not in used:
                used.add(key)
                if key in bindings:
                    pending.append(bindings[key])
    return used


def model_issues(files, *, include_unused=True):
    """(level, path, message) entries. Errors are never fixed silently."""
    models = loaded_models(files)
    issues = []
    for name, doc in sorted(models.items()):
        # Pure parent wrappers have no independent texture choices or geometry.
        if not any(k in doc for k in ('elements', 'textures')):
            continue
        bindings = inherited_textures(name, models)
        elements = rendered_elements(name, models)
        for idx, element in enumerate(elements):
            if not isinstance(element, dict):
                continue
            for face_name, face in element.get('faces', {}).items():
                if not isinstance(face, dict):
                    continue
                ref = face.get('texture')
                problem = resolve_texture(ref, bindings, files)
                if problem:
                    issues.append(('ERROR', name, f'element {idx} face {face_name}: {problem}'))
        if 'particle' in bindings:
            problem = resolve_texture('#particle', bindings, files)
            if problem:
                issues.append(('ERROR', name, f'particle: {problem}'))
        # Generated / handheld item models often define no elements because
        # their vanilla parent supplies the geometry. Their layerN bindings
        # are still used and must be present; don't treat them as unused.
        if not elements and isinstance(doc.get('textures'), dict):
            for key in doc['textures']:
                if key == 'particle':
                    continue
                problem = resolve_texture('#' + key, bindings, files)
                if problem:
                    issues.append(('ERROR', name, f'inherited texture {key}: {problem}'))
        # Absence of local elements or presence of a parent can mean the
        # parent expects a seemingly unused variable. Don't guess.
        if include_unused and 'elements' in doc and not doc.get('parent') and isinstance(doc.get('textures'), dict):
            used = used_bindings(elements, bindings)
            for key, ref in doc['textures'].items():
                if key not in used and isinstance(ref, str) and not ref.startswith('#'):
                    path = asset_path(ref)
                    if not path.startswith('assets/minecraft/') and path not in files:
                        issues.append(('WARN', name, f'unused declaration {key} refers to missing custom PNG {ref}'))
    return issues


def prune_broken_faces(files):
    """Return new pack-file dict and actions; never mutate original bytes.

    Only removes *individual* geometry faces whose texture cannot resolve.
    An element with zero remaining faces is removed as it cannot render.
    Also drops provably unused, missing custom texture declarations on
    standalone element models (not parent-based models).
    """
    models = loaded_models(files)
    result = dict(files)
    actions = []
    for name, original in sorted(models.items()):
        if 'elements' not in original or not isinstance(original['elements'], list):
            continue
        doc = json.loads(json.dumps(original))
        bindings = inherited_textures(name, models)
        elements = []
        for idx, element in enumerate(doc['elements']):
            if not isinstance(element, dict) or not isinstance(element.get('faces'), dict):
                elements.append(element)
                continue
            for face_name, face in list(element['faces'].items()):
                if not isinstance(face, dict):
                    continue
                problem = resolve_texture(face.get('texture'), bindings, files)
                if problem:
                    del element['faces'][face_name]
                    actions.append(f'{name}: removed element {idx} face {face_name} ({problem})')
            if element['faces']:
                elements.append(element)
            else:
                actions.append(f'{name}: removed now-invisible element {idx}')
        doc['elements'] = elements
        if not doc.get('parent') and isinstance(doc.get('textures'), dict):
            used = used_bindings(elements, bindings)
            for key, ref in list(doc['textures'].items()):
                if key in used or not isinstance(ref, str) or ref.startswith('#'):
                    continue
                path = asset_path(ref)
                if not path.startswith('assets/minecraft/') and path not in files:
                    del doc['textures'][key]
                    actions.append(f'{name}: removed unused missing texture declaration {key}={ref}')
        if doc != original:
            result[name] = (json.dumps(doc, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    return result, actions
