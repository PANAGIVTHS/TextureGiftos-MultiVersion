# TextureGiftos — one source, 23 Minecraft Java versions

A **single-branch resource-pack repository** for Java **1.20.1 through 26.3**.
The Minecraft versions are **folders**, not Git branches. All assets and model
geometry are maintained in one shared source; Python builds a different
installable pack for each Minecraft release.

## Repository layout

```text
assets/mcd/models/item/         Editable source models (swords, bows, misc)
assets/mcd/textures/            Editable PNGs and animation metadata
assets/mcd/items/               Direct item-model definitions for modern Minecraft
assets/minecraft/items/         Modern preview definitions (build script regenerates selectors)
tools/build_pack.py             Generate packs for one or all versions
tools/validate_pack.py          Check references and metadata
tools/test_builds.py            Rebuild every release and run static tests
versions/<MC_VERSION>/          Generated installable resource-pack ZIPs
.github/workflows/             CI checks for consistency on every push
```

**Edit under `assets/`, never inside `versions/`.** The generated ZIPs are
checked into Git intentionally so each version can be downloaded from the
repository without running Python. They contain only the installable pack,
not any source-only files or `.git` metadata.

# Temporary modded weapon builds

`build_weapon_pack.py` creates a **complete, standalone resource-pack ZIP** with extra item definitions. It does **not** edit `assets/`, `versions/`, or the original build scripts. Outputs under `custom_builds/` are ignored by Git.

```sh
python tools/build_weapon_pack.py --version 1.20.1 --weapon soulsweapons:guts_sword=guts
python tools/build_weapon_pack.py --version 26.3 --weapon soulsweapons:guts_sword=guts --weapon othermod:greatblade=dragonslayer
python tools/build_weapon_pack.py --all --weapons-file weapons.txt --prune-missing-faces
```

`weapons.txt` example:

```text
# item registry ID = existing sword model
soulsweapons:guts_sword=guts
othermod:greatblade=dragonslayer
```

The output is `custom_builds/<version>/TextureGiftos_Custom_<version>.zip`. Install **only this ZIP** instead of the ordinary version ZIP; it already contains the full pack.

For Minecraft 1.20.1–1.21.3, modded-item support is generated as OptiFine-style **CIT rules** and requires a compatible CIT client mod. Numeric `CustomModelData` is matched by the CIT rule. Vanilla alone cannot universally override arbitrary modded item models.

For 1.21.4 and later, `assets/<mod_namespace>/items/<item>.json` item definitions are added to the generated ZIP. Numeric `CustomModelData` selects the target model; 1.21.5+ additionally includes a name-based selector. This may not work for mod items using custom renderers or special item-definition systems, and the fallback assumes the mod has a conventional `assets/<namespace>/models/item/<item>.json` model.

Only the four existing sword models are supported. For any modded item with a different base ID than its intended model, specify `namespace:item=guts` etc. The script refuses unknown names rather than silently choosing a wrong model.


## Quick start

Requirements: Python 3.9+; no third-party dependencies.

```bash
python tools/build_pack.py --list
python tools/build_pack.py --version 1.20.1
python tools/build_pack.py --all
python tools/test_builds.py
```

Example output: `versions/1.20.1/TextureGiftos_1.20.1.zip`. Place the ZIP
**without extracting it** in `.minecraft/resourcepacks/`. Disable older
TextureGiftos packs when testing, and use `F3+T` to reload.

## Supported models

| Vanilla base item | Model name | Numeric `CustomModelData` |
|---|---|---:|
| Netherite sword | Tenryū’s Shriek | `123001` |
| Netherite sword | Aatrox | `123002` |
| Netherite sword | Guts' Sword | `123003` |
| Netherite sword | Dragonslayer / Dragon Slayer | `123004` |
| Diamond sword | Tenryū’s Shriek | `123001` |
| Carrot on a stick | Scanner | `123401` |
| Eye of Ender | Ender's Wrath | `123301` |

Varus bow has name-based support in CIT-enabled legacy versions and in
supported modern versions.

Dragonslayer uses corrected vanilla block texture references,
`under_fix.png`, and the three-frame `handle_wraps.png` ribbon animation with
its `.png.mcmeta` file.

### Version compatibility

| Java versions | Item model format | Renaming to change textures |
|---|---|---|
| 1.20.1–1.21.3 | Legacy JSON overrides | Requires OptiFine/CIT-capable client for item-name rules; numeric `CustomModelData` works in vanilla |
| 1.21.4 | Modern item definitions | Use numeric `CustomModelData` or direct `item_model`; name selector unavailable in vanilla |
| 1.21.5–26.3 | Modern item definitions | Vanilla exact-name selector; numeric and direct selection also available |

Minecraft changed item rendering in 1.21.4 and added the `minecraft:component`
item-model selection property in 1.21.5. That is why **one ZIP is not used for
all releases**.

### Testing commands

Minecraft **1.20.1**:

```mcfunction
/give @s minecraft:netherite_sword{CustomModelData:123004} 1
```

Minecraft **1.20.5–1.21.3**:

```mcfunction
/give @s minecraft:netherite_sword[minecraft:custom_model_data=123004] 1
```

Minecraft **1.21.4+**:

```mcfunction
/give @s minecraft:netherite_sword[minecraft:custom_model_data={floats:[123004]}] 1
/give @s minecraft:netherite_sword[minecraft:item_model="mcd:swords/dragonslayer"] 1
```

The CIT rules also target `soulsweapons:guts_sword` when renamed in compatible
older CIT clients. Custom mod renderers can bypass CIT entirely.

## Validation and limitations

```bash
python tools/validate_pack.py
python tools/test_builds.py
```

Automated tests verify JSON, archive structure, local model and texture
references, PNG animation metadata, and the expected selectors. They **do not**
replace actual rendering tests in Minecraft, or guarantee compatibility with
third-party modded item renderers.

The original **Elite Power Bow** feature referenced four missing models, so
its incomplete override is intentionally excluded; Varus remains. The old
**CustomTrims** branch was not merged: armor trims require separate work.

## A fresh Git repository (one `main` branch)

This ZIP intentionally contains **no `.git/` directory** and **does not need
any patch**. Extract it into a new folder and initialize Git once:

```bash
git init -b main
python tools/test_builds.py
git add -A
git commit -m "Initial clean multi-version TextureGiftos repository"
```

Then create an **empty** GitHub repository (do not select auto-generated README,
`.gitignore`, or license); copy its HTTPS URL and run:

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_NEW_REPOSITORY.git
git push -u origin main
```

**Do not push this onto the existing historical repository with `--force`.**
Either give the new GitHub repository a new name, or rename the old GitHub
repository to an archive name before creating a fresh one under its old name.

## Build automation

The included GitHub Actions workflow validates all 23 packs, checks that
committed `versions/` ZIPs agree with the shared sources, and uploads all
installable packs as a workflow artifact. Every Minecraft version is built
from the same models and textures; **no per-version branches are necessary**.
