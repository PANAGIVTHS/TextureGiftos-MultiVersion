# TextureGiftos — 26.3 atlas repair (v3)

This is a drop-in update of the **existing repository build tools**. Only these files are replaced:

- `tools/build_pack.py`
- `tools/model_compat.py`
- `tests/test_model_compat.py` (tests, optional)

Do NOT delete `assets/`, `versions/`, `.git/`, `pack.png`, or your other scripts. The converter never writes to `assets/`.

## Apply in Windows Git Bash

Extract this archive into your repository root, preserving the `tools/` and `tests/` directories. Allow replacement of the files listed above.

Then run:

```bash
python tools/build_pack.py --version 26.3
python -m unittest discover -s tests -v
```

Generated file: `versions/26.3/TextureGiftos_26.3.zip`. Install that ZIP as a resource pack, with **only one TextureGiftos pack enabled**. Reload with `F3+T`.

## What's repaired automatically, inside the generated ZIP only

- **Minecraft 1.21.11+ texture atlas split.** Models cannot mix textures from the block and item atlases. Your Dragonslayer includes both vanilla `block/*` and custom `mcd:item/swords/*` textures. The converter copies the three custom textures into `assets/mcd/textures/block/texturegiftos_compat/item/swords/`, updates only the output model's texture references, and carries over the `handle_wraps.png.mcmeta` animation file. No source images are moved or overwritten. This is the most likely cause of the Dragonslayer model-baking failure.
- **Vanilla netherite sword fallback.** The generated selectors have a local `mcd:item/compat/vanilla_netherite_sword` fallback model with the standard handheld parent and the vanilla netherite sword sprite. This is a defensive change; we cannot verify that it resolves your missing default model without an in-game run.
- Preserves v2 fixes: removes duplicate name cases, removes demonstrably broken unbundled custom parents on self-contained models, skips undefined `#missing` faces (only in the ZIP), and converts removed `shade` properties when necessary.
- Performs the atlas compatibility transformation from Minecraft **1.21.11 onward**, not in older builds that do not need it.

Note: The old converter's undefined-face cleanup removes faces that had no resolvable texture; for the reference Dragonslayer model this is 39 such faces. Model elements, dimensions, position, rotation, and UV for surviving faces are retained. The atlas conversion itself does not alter geometry.

**Limitation:** The atlas fixer can copy only custom item PNG files actually packaged in the source. If a model mixes vanilla item sprites with block sprites, it reports an explicit error rather than pretending to fix it. Static ZIP checks do not equal a successful in-game model bake.

## Test in Minecraft 26.3

```mcfunction
/give @s minecraft:netherite_sword 1
/give @s minecraft:netherite_sword[minecraft:item_model="mcd:compat/vanilla_netherite_sword"] 1
/give @s minecraft:netherite_sword[minecraft:item_model="mcd:swords/dragonslayer"] 1
/give @s minecraft:netherite_sword[minecraft:custom_model_data={floats:[123004]}] 1
/give @s minecraft:netherite_sword[minecraft:custom_model_data={floats:[123002]}] 1
```

First test normal netherite. The explicit `mcd:compat/vanilla_netherite_sword` command bypasses the selector, distinguishing default-model problems from selector problems. Then test Dragonslayer direct model reference and CMD selection. Test with no other third-party resource pack above it.

If any fail, open `.minecraft/logs/latest.log` just after `F3+T` and find `Unable to bake item model`, `Multiple atlases`, `dragonslayer`, `netherite_sword`, `Couldn't load`, or `missing`. Share the surrounding lines for a precise diagnosis.

## What was actually verified

- 18 unit tests passed.
- All 23 configured versions built from the uploaded reference pack files with a lightweight validator stub.
- Generated 26.3 ZIP archive CRC/integrity passed.
- Dragonslayer's texture map uses only block-atlas sprites; all three new copied sprites and its animation metadata are present.
- All 209 Dragonslayer model elements were retained, with exact same non-face geometry properties.
- No Minecraft client was executed. In-game rendering remains unverified.
