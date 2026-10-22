# TextureGiftos build-time compatibility layer

## Installation

Copy the `tools/` and `tests/` folders from this update into the **root of your existing** `TextureGiftos-MultiVersion` repository, replacing only `tools/build_pack.py` and adding `tools/model_compat.py` and `tests/test_model_compat.py`. Keep all original `assets/`, `pack.png`, `pack.mcmeta`, and the other `tools/` scripts. Do not extract this update into `assets/` or into a Minecraft resource-pack ZIP.

## One command builds the pack

```bash
python tools/build_pack.py --version 26.3
```

Creates `versions/26.3/TextureGiftos_26.3.zip`.

All 23 versions: `python tools/build_pack.py --all`.
Temporary modded item build (still supported):
`python tools/build_weapon_pack.py --version 26.3 --weapon soulsweapons:guts_sword`.

For an extra regression test, run `python -m unittest discover -s tests -v` and the repository's existing `python tools/test_builds.py`.

## What happens under the hood

- Reads your authoritative sources from `assets/` **without writing them**.
- Uses old-style item overrides for 1.20.1 through 1.21.3 and modern `assets/<namespace>/items/` definitions for 1.21.4+.
- Generates missing direct item definitions for new `assets/mcd/models/item/` models automatically, preserving manually authored definitions.
- Converts model element `shade: false` into `shade_direction_override: "up"` in 26.3, removes `shade: true`, and reverses the supported case for old targets. Shape, UV mapping, element ordering and face definitions are preserved.
- Converts 26.1+ object-form model texture references back into old string references only when the target Minecraft version needs it. Object textures with `force_translucent:true` cannot be faithfully downgraded and cause a clear build error.
- Converts simple legacy numeric `custom_model_data` overrides to modern `minecraft:range_dispatch` selectors. Unsupported multi-predicate overrides produce errors instead of silent data loss.
- Adds legacy model wrappers and OptiFine/CIT `.properties` rules in modern ZIPs as a supplementary path for compatible modded clients; vanilla modern item definitions remain the primary path.
- Invokes your existing `validate_pack.py` before producing a ZIP; missing references and other validation errors stop the build.
- Optional `--prune-missing-faces` remains available, **but removes geometry faces from the generated ZIP** and is therefore *not* used automatically.

## Important limitations

**Static build verification is not an in-game rendering test.** The uploaded repository ZIP already has the correct `assets/minecraft/items/` style and no obsolete `shade` values. Its failure cannot be conclusively attributed to these format issues from the ZIPs alone. The legacy `Fixed` pack has a fundamentally different model-selection system; it should not replace modern item definitions in a 26.3 resource pack.

Minecraft's format changes are not always reversible. No converter can guarantee that arbitrary Blockbench models or third-party renderers work without modification; unsupported semantics are rejected, not guessed. The modded-item renderer may bypass either CIT or vanilla item-model definitions. A resource pack cannot make legacy NBT `/give` syntax work in a newer Minecraft version.

## Isolation checks on 26.3

Test with only your newly generated ZIP enabled, using the correct *new* data-component syntax:

```mcfunction
/give @s minecraft:netherite_sword[minecraft:item_model="mcd:swords/aatrox"] 1
/give @s minecraft:netherite_sword[minecraft:custom_model_data={floats:[123002]}] 1
/give @s minecraft:netherite_sword[minecraft:custom_name={text:'Aatrox'}] 1
```

The first tests the direct model; the second tests the numeric selector; the third tests the name selector. If only one fails, the cause is likely in that selection route rather than the model geometry. When these fail, inspect `.minecraft/logs/latest.log` for `Unable to load model`, `Failed to parse`, and `Missing texture` warnings; these runtime errors are needed for a confirmed diagnosis.
