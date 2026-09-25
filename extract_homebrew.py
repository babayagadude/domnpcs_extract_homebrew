#!/usr/bin/env python3
"""
Extract non-SRD content from D&D 5e supplements.
Outputs JSON matching the app's import structure.

Usage:
  python3 extract_homebrew.py <source data directory>

The argument is the `data` folder of the source dataset (its parent folder
works too). Output goes to homebrew.json in the current directory.
"""

import argparse
import os
import glob
import re
import json
import string
import time

# The source data directory, set from the command line in main().
DATA = None


def data_path(*parts):
    """Path to a file inside the source data directory."""
    return os.path.join(DATA, *parts)


# Supplements we import, highest precedence first. When the same subclass or
# species is printed in more than one book the earlier source wins, because the
# 2024-era books (XPHB, AU, EFA, RHW) restate the older XGE/TCE/MPMM versions.
SOURCE_PRECEDENCE = ["XPHB", "AU", "EFA", "RHW", "FRHoF", "TCE", "XGE", "MPMM"]
SOURCE_PRIORITY = {src: i for i, src in enumerate(SOURCE_PRECEDENCE)}

SOURCE_NAMES = {
    "XPHB": "2024 Player's Handbook",
    "AU": "Arcana Unleashed",
    "EFA": "Eberron: Forge of the Artificer",
    "RHW": "Ravenloft: The Horrors Within",
    "FRHoF": "Forgotten Realms: Heroes of Faerun",
    "TCE": "Tasha's Cauldron of Everything",
    "XGE": "Xanathar's Guide to Everything",
    "MPMM": "Monsters of the Multiverse",
}

# Books we pull each kind of content from. XPHB is always filtered further,
# since only part of the 2024 PHB falls outside the SRD.
SUBCLASS_SOURCES = ["XPHB", "AU", "EFA", "RHW", "FRHoF", "TCE", "XGE"]

# TCE's feats and backgrounds are omitted: the ones still in print were
# reprinted in the 2024 PHB, and XGE has neither.
FEAT_SOURCES = ["XPHB", "AU", "EFA", "RHW", "FRHoF"]
BACKGROUND_SOURCES = ["XPHB", "AU", "EFA", "RHW", "FRHoF"]
EQUIPMENT_SOURCES = ["XPHB", "AU", "EFA", "RHW", "FRHoF", "TCE", "XGE"]

# Books that publish playable non-SRD species. Arcana Unleashed has none.
SPECIES_SOURCES = ["EFA", "RHW", "MPMM"]


def extract_supplement_species():
    """Extract non-SRD species from the supplement books in SPECIES_SOURCES."""
    # Load species descriptions from fluff-races.json
    with open(data_path('fluff-races.json'), 'r') as f:
        fluff_data = json.load(f)

    # Keyed by (name, source) so the RHW/EFA reprints keep their own blurb.
    species_descriptions = {}
    for race_fluff in fluff_data.get('raceFluff', []):
        if race_fluff.get('source') in SPECIES_SOURCES:
            name = race_fluff.get('name', '')
            entries = race_fluff.get('entries', [])
            if entries:
                desc = entries_to_text(entries)
                species_descriptions[(name, race_fluff['source'])] = desc

    # Load species data from races.json
    with open(data_path('races.json'), 'r') as f:
        races_data = json.load(f)

    # SRD species to exclude: Goliath, Human, Elf, Dwarf, Halfling, Orc (2024 SRD species)
    SRD_SPECIES = {'Goliath', 'Human', 'Elf', 'Dwarf', 'Halfling', 'Orc'}

    # Species to skip (these are heritages, not base species in the app)
    SKIP_SPECIES = {'Deep Gnome', 'Sea Elf', 'Drow', 'Eladrin'}

    # name -> species entry, keeping only the highest-precedence printing
    # (e.g. EFA's 2024 Changeling wins over the MPMM one).
    by_name = {}
    reprints = {}

    for race in races_data.get('race', []):
        source = race.get('source')
        if source not in SPECIES_SOURCES:
            continue

        name = race.get('name')
        if name in SRD_SPECIES or name in SKIP_SPECIES:
            continue

        # Get size
        size_list = race.get('size', ['M'])
        size_map = {'T': 'Tiny', 'S': 'Small', 'M': 'Medium', 'L': 'Large'}
        size = size_map.get(size_list[0] if isinstance(size_list, list) else size_list, 'Medium')
        
        # Get speed
        speed_obj = race.get('speed', {})
        if isinstance(speed_obj, dict):
            speed = speed_obj.get('walk', 30)
        else:
            speed = 30
            
        # Get description from fluff
        description = species_descriptions.get(
            (name, source), f"A {name} from {SOURCE_NAMES.get(source, source)}")

        # Extract abilities from entries
        abilities = []
        for entry in race.get('entries', []):
            if isinstance(entry, dict) and entry.get('type') == 'entries':
                ability_name = entry.get('name', '')
                ability_entries = entry.get('entries', [])
                
                # Extract description
                ability_desc = entries_to_text(ability_entries)
                
                # Create ability structure
                ability = {
                    'name': ability_name,
                    'levelRequired': 1,
                    'description': ability_desc,
                    'heritage': None,
                    'isChoice': False,
                    'choiceGroup': None,
                    'grantsSpells': False,
                    'spellsGranted': None,
                    'spellUsageType': None,
                    'spellNotes': None,
                    'grantsProficiencies': False,
                    'proficienciesGranted': None,
                    'grantsResistances': False,
                    'resistancesGranted': None,
                    'grantsImmunities': False,
                    'immunitiesGranted': None,
                    'grantsConditionImmunities': False,
                    'conditionImmunitiesGranted': None,
                    'grantsSenses': False,
                    'sensesGranted': None,
                    'grantsMovement': False,
                    'movementGranted': None,
                    'grantsAbilityScoreIncrease': False,
                    'abilityScoreIncrease': None
                }
                
                abilities.append(ability)
        
        species_entry = {
            "id": 0,
            "name": name,
            "description": description,
            "size": size,
            "speed": speed,
            "languages": [],
            "abilities": abilities,
            "_source": source
        }

        existing = by_name.get(name)
        if existing is None:
            by_name[name] = species_entry
            continue

        reprints.setdefault(name, [existing['_source']]).append(source)
        if SOURCE_PRIORITY[source] < SOURCE_PRIORITY[existing['_source']]:
            by_name[name] = species_entry

    if reprints:
        print("\nSpecies printed in multiple books (keeping the newest):")
        for name, sources in sorted(reprints.items()):
            print(f"  {name}: {sources} → chose {by_name[name]['_source']}")

    species = sorted(by_name.values(), key=lambda x: x['name'])

    counts = {}
    for entry in species:
        counts[entry['_source']] = counts.get(entry['_source'], 0) + 1
        entry.pop('_source')

    for source in SPECIES_SOURCES:
        if counts.get(source):
            print(f"Loaded {counts[source]} non-SRD species from {SOURCE_NAMES[source]}")
    return species


def entries_to_text(entries, max_length=None):
    """Convert a source entries array to plain text description.

    Pass max_length=None to disable truncation.
    """
    import re

    if not entries:
        return ""

    def clean_source_tags(text):
        """Remove the source's formatting tags like {@spell fireball|phb} -> fireball"""
        if not isinstance(text, str):
            return text

        # Pattern matches {@tagname content|source} or {@tagname content}
        # Examples: {@spell Fireball|PHB}, {@variantrule Bonus Action|XPHB}, {@item Longsword}
        pattern = r'\{@[a-zA-Z]+\s+([^}|]+)(?:\|[^}]*)?\}'
        text = re.sub(pattern, r'\1', text)

        # Also handle {@dice 1d6} -> 1d6
        text = re.sub(r'\{@dice\s+([^}]+)\}', r'\1', text)

        # Handle {@damage 2d8} -> 2d8
        text = re.sub(r'\{@damage\s+([^}]+)\}', r'\1', text)

        return text

    def process_entry(entry):
        if isinstance(entry, str):
            return clean_source_tags(entry)
        elif isinstance(entry, dict):
            if entry.get('type') == 'list' and 'items' in entry:
                items = [process_entry(item) for item in entry['items']]
                return ' '.join(items)
            elif entry.get('type') == 'item':
                # Handle list items with name and entries (e.g., "Elemental Immunity: ...")
                parts = []
                if 'name' in entry:
                    parts.append(entry['name'] + ':')
                if 'entries' in entry:
                    parts.append(' '.join([process_entry(e) for e in entry['entries']]))
                elif 'entry' in entry:
                    parts.append(process_entry(entry['entry']))
                return ' '.join(parts)
            elif 'entries' in entry:
                # Handle nested entries with optional name prefix
                parts = []
                if 'name' in entry:
                    parts.append(entry['name'] + ':')
                parts.append(' '.join([process_entry(e) for e in entry['entries']]))
                return ' '.join(parts)
            elif 'entry' in entry:
                return process_entry(entry['entry'])
        return ""

    text_parts = [process_entry(e) for e in entries]
    full_text = ' '.join(text_parts)
    full_text = ' '.join(full_text.split())  # Clean up multiple spaces

    # Truncate if too long (only when a limit is specified)
    if max_length is not None and len(full_text) > max_length:
        full_text = full_text[:max_length].rsplit(' ', 1)[0] + '...'

    return full_text

def convert_source_spell(spell_data):
    """Convert a source spell to app format."""
    # Map school abbreviations
    school_map = {
        "A": "Abjuration", "C": "Conjuration", "D": "Divination",
        "E": "Enchantment", "V": "Evocation", "I": "Illusion",
        "N": "Necromancy", "T": "Transmutation"
    }

    # Extract casting time
    casting_time = "1 action"
    if "time" in spell_data and spell_data["time"]:
        time_obj = spell_data["time"][0]
        unit = time_obj.get("unit", "action")
        number = time_obj.get("number", 1)
        if unit == "bonus":
            casting_time = "1 bonus action"
        elif unit == "reaction":
            casting_time = "1 reaction"
        elif unit == "minute":
            casting_time = f"{number} minute{'s' if number > 1 else ''}"
        elif unit == "hour":
            casting_time = f"{number} hour{'s' if number > 1 else ''}"
        else:
            casting_time = f"{number} {unit}{'s' if number > 1 else ''}"

    # Extract components - MUST BE A LIST
    components = []
    if spell_data.get("components", {}).get("v"):
        components.append("V")
    if spell_data.get("components", {}).get("s"):
        components.append("S")
    if spell_data.get("components", {}).get("m"):
        material = spell_data["components"]["m"]
        if isinstance(material, str):
            components.append(f"M ({material})")
        elif isinstance(material, dict):
            # Handle complex material format
            mat_text = material.get("text", "")
            components.append(f"M ({mat_text})" if mat_text else "M")
        else:
            components.append("M")

    description = ""
    higher_levels = ""
    if "entries" in spell_data:
        # Separate "At Higher Levels" from main description
        main_entries = []
        for entry in spell_data["entries"]:
            if isinstance(entry, dict) and entry.get("type") == "entries" and entry.get("name", "").startswith("At Higher Levels"):
                # Extract higher levels section
                if "entries" in entry:
                    higher_levels_parts = []
                    for he in entry["entries"]:
                        if isinstance(he, str):
                            higher_levels_parts.append(he)
                    higher_levels = " ".join(higher_levels_parts)
            else:
                main_entries.append(entry)

        # Use entries_to_text for the main description
        description = entries_to_text(main_entries)

    # Clean up description (remove the source's tags like {@damage}, {@spell}, {@dice})
    description = re.sub(r'\{@damage ([^}]+)\}', r'\1', description)
    description = re.sub(r'\{@dice ([^}]+)\}', r'\1', description)
    description = re.sub(r'\{@spell ([^}|]+)(\|[^}]+)?\}', r'\1', description)
    description = re.sub(r'\{@\w+\s+([^}]+)\}', r'\1', description)

    higher_levels = re.sub(r'\{@damage ([^}]+)\}', r'\1', higher_levels)
    higher_levels = re.sub(r'\{@dice ([^}]+)\}', r'\1', higher_levels)
    higher_levels = re.sub(r'\{@spell ([^}|]+)(\|[^}]+)?\}', r'\1', higher_levels)
    higher_levels = re.sub(r'\{@\w+\s+([^}]+)\}', r'\1', higher_levels)

    # Extract range
    range_text = extract_range(spell_data.get("range", {}))

    # Extract duration
    duration_text = extract_duration(spell_data.get("duration", []))

    # Extract classes - MUST BE A STRING
    classes = extract_spell_classes(spell_data)
    classes_string = ", ".join(classes) if classes else ""

    # Determine if it's a concentration spell
    concentration = False
    if "duration" in spell_data and spell_data["duration"]:
        concentration = spell_data["duration"][0].get("concentration", False)

    # Determine if it's a ritual
    ritual = spell_data.get("meta", {}).get("ritual", False)

    # Determine if it's an attack spell
    is_attack = "spellAttack" in spell_data and len(spell_data.get("spellAttack", [])) > 0

    return {
        "id": 0,
        "name": spell_data["name"],
        "level": spell_data["level"],
        "school": school_map.get(spell_data["school"], "Evocation"),
        "castingTime": casting_time,
        "range": range_text,
        "components": components,  # LIST not string
        "duration": duration_text,
        "description": description.strip(),
        "higherLevels": higher_levels.strip(),
        "ritual": ritual,
        "concentration": concentration,
        "classes": classes_string,  # STRING not list
        "isAttack": is_attack
    }

def extract_range(range_obj):
    """Extract range from the source format."""
    if isinstance(range_obj, dict):
        range_type = range_obj.get("type")
        if range_type == "point":
            dist = range_obj.get("distance", {})
            amount = dist.get("amount", 0)
            dist_type = dist.get("type", "feet")
            return f"{amount} {dist_type}"
        elif range_type == "self":
            # Check for area
            if "distance" in range_obj:
                dist = range_obj["distance"]
                amount = dist.get("amount", 0)
                dist_type = dist.get("type", "feet")
                return f"Self ({amount}-foot radius)"
            return "Self"
        elif range_type == "touch":
            return "Touch"
        elif range_type == "sight":
            return "Sight"
        elif range_type == "unlimited":
            return "Unlimited"
    return "Touch"

def extract_duration(duration_list):
    """Extract duration from the source format."""
    if not duration_list:
        return "Instantaneous"
    dur = duration_list[0]
    dur_type = dur.get("type")

    if dur_type == "instant":
        return "Instantaneous"
    elif dur_type == "timed":
        conc = "Concentration, " if dur.get("concentration") else ""
        duration_obj = dur.get("duration", {})
        amount = duration_obj.get("amount", 1)
        unit = duration_obj.get("type", "minute")

        # Pluralize if needed
        if amount > 1 and not unit.endswith("s"):
            unit = unit + "s"

        return f"{conc}up to {amount} {unit}"
    elif dur_type == "permanent":
        ends = dur.get("ends", [])
        if ends:
            return f"Until {', '.join(ends)}"
        return "Permanent"
    elif dur_type == "special":
        return "Special"

    return "Instantaneous"

def extract_spell_classes(spell_data):
    """Extract classes that can cast this spell."""
    classes = []

    # Check classes field
    if "classes" in spell_data and "fromClassList" in spell_data["classes"]:
        for cls in spell_data["classes"]["fromClassList"]:
            classes.append(cls["name"])

    # Check subclasses field (some spells are granted by subclasses)
    if "classes" in spell_data and "fromSubclass" in spell_data["classes"]:
        for subcls in spell_data["classes"]["fromSubclass"]:
            class_name = subcls.get("class", {}).get("name")
            if class_name and class_name not in classes:
                classes.append(class_name)


    return classes

def build_spell_class_mapping():
    """Build a mapping of spell names to classes using sources.json."""
    spell_to_classes = {}

    # Read the sources.json file which maps spells to classes
    sources_file = data_path("spells", "sources.json")
    try:
        with open(sources_file, "r", encoding="utf-8") as f:
            sources_data = json.load(f)

        # Iterate through all sources and collect spell-to-class mappings
        for source_name, spells in sources_data.items():
            if isinstance(spells, dict):
                for spell_name, spell_info in spells.items():
                    class_names = []

                    # Check for "class" field (standard format)
                    if "class" in spell_info and isinstance(spell_info["class"], list):
                        class_names = [cls["name"] for cls in spell_info["class"]]

                    # Check for "classVariant" field (variant format for TCE and other supplements)
                    if "classVariant" in spell_info and isinstance(spell_info["classVariant"], list):
                        class_names = [cls["name"] for cls in spell_info["classVariant"]]

                    # If we found classes, add/merge them
                    if class_names:
                        # Deduplicate class names
                        class_names = list(set(class_names))
                        # If this spell already exists, merge the classes
                        if spell_name in spell_to_classes:
                            existing_classes = set(spell_to_classes[spell_name].split(", "))
                            existing_classes.update(class_names)
                            spell_to_classes[spell_name] = ", ".join(sorted(existing_classes))
                        else:
                            spell_to_classes[spell_name] = ", ".join(sorted(class_names))

        print(f"Loaded {len(spell_to_classes)} spell-class mappings from sources.json")

    except FileNotFoundError:
        print(f"Warning: Could not find {sources_file}")

    return spell_to_classes

# Per-book spell files. Ravenloft: The Horrors Within has no spell file
# upstream — it introduces no new spells.
SPELL_FILES = [
    ("spells-xphb.json", "XPHB"),
    ("spells-au.json", "AU"),
    ("spells-efa.json", "EFA"),
    ("spells-frhof.json", "FRHoF"),
    ("spells-tce.json", "TCE"),
    ("spells-xge.json", "XGE"),
]


def load_and_convert_spells():
    """Load spells from JSON files and convert to app format."""
    all_spells = []

    # Build spell-to-class mapping from SRD data
    spell_class_mapping = build_spell_class_mapping()

    for filename, source in SPELL_FILES:
        try:
            with open(data_path("spells", filename), "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Warning: {filename} not found")
            continue

        count = 0
        for spell in data.get("spell", []):
            if spell.get("source") != source:
                continue
            # The 2024 PHB is only partly non-SRD; the rest of these books are
            # non-SRD in their entirety.
            if source == "XPHB" and spell.get("srd52"):
                continue

            converted_spell = convert_source_spell(spell)
            # If spell has no classes, try to find it in SRD mapping
            if not converted_spell["classes"] and spell["name"] in spell_class_mapping:
                converted_spell["classes"] = spell_class_mapping[spell["name"]]
            all_spells.append(converted_spell)
            count += 1

        print(f"Loaded {count} non-SRD spells from {SOURCE_NAMES[source]}")

    return all_spells


def extract_all_spells():
    """Extract all non-SRD spells from supplement files."""
    return load_and_convert_spells()

def extract_phb_feats():
    """Extract non-SRD feats from the books in FEAT_SOURCES."""
    try:
        with open(data_path("feats.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
            phb_feats = []

            # D&D 5e 2024 SRD feats to exclude
            srd_feats = {
                # Origin Feats (SRD 5.2.1)
                'Alert', 'Magic Initiate', 'Savage Attacker', 'Skilled',
                # General Feats (SRD 5.2.1)
                'Ability Score Improvement', 'Grappler',
                # Fighting Style Feats (SRD 5.2.1)
                'Archery', 'Defense', 'Great Weapon Fighting', 'Two-Weapon Fighting',
                # Epic Boon Feats (SRD 5.2.1)
                'Boon of Combat Prowess', 'Boon of Dimensional Travel', 'Boon of Fate',
                'Boon of Irresistible Offense', 'Boon of Spell Recall',
                'Boon of the Night Spirit', 'Boon of Truesight'
            }

            counts = {}
            seen = set()

            for feat in data.get('feat', []):
                feat_source = feat.get('source')

                if feat_source not in FEAT_SOURCES:
                    continue
                # Only the 2024 PHB needs the SRD filter; the supplements are
                # non-SRD in their entirety.
                if feat_source == 'XPHB' and feat['name'] in srd_feats:
                    continue
                if feat['name'] in seen:
                    continue
                seen.add(feat['name'])

                # Convert entries to description
                desc = entries_to_text(feat.get('entries', []))

                # Extract prerequisites if any
                prereqs = feat.get('prerequisite', [])
                prereq_text = ""
                if prereqs:
                    for prereq in prereqs:
                        if 'ability' in prereq:
                            for ability in prereq['ability']:
                                for stat, value in ability.items():
                                    prereq_text += f"{stat.upper()} {value}+ "
                        if 'proficiency' in prereq:
                            for prof in prereq['proficiency']:
                                prereq_text += f"{prof.get('armor', prof.get('weapon', ''))} proficiency "

                entry = {
                    "id": 0,
                    "name": feat['name'],
                    "description": desc,
                    "benefits": desc,
                    "prerequisites": prereq_text.strip() if prereq_text else ""
                }
                grant = feat_spell_grant(feat.get('additionalSpells'))
                if grant:
                    entry["grantsSpells"] = grant
                phb_feats.append(entry)

                counts[feat_source] = counts.get(feat_source, 0) + 1

            for source in FEAT_SOURCES:
                if counts.get(source):
                    print(f"Loaded {counts[source]} non-SRD feats from {SOURCE_NAMES[source]}")
            return phb_feats
    except FileNotFoundError:
        print("Warning: feats.json not found")
        return []

def extract_phb_backgrounds():
    """Extract non-SRD backgrounds from the books in BACKGROUND_SOURCES."""
    try:
        # Load main background data
        with open(data_path("backgrounds.json"), "r", encoding="utf-8") as f:
            data = json.load(f)

        # Load fluff descriptions, keyed by (name, source) so reprints keep
        # their own blurb
        fluff_data = {}
        try:
            with open(data_path("fluff-backgrounds.json"), "r", encoding="utf-8") as f:
                fluff = json.load(f)
                for bg_fluff in fluff.get('backgroundFluff', []):
                    if bg_fluff.get('source') in BACKGROUND_SOURCES:
                        fluff_data[(bg_fluff['name'], bg_fluff['source'])] = bg_fluff
        except FileNotFoundError:
            print("Warning: fluff-backgrounds.json not found, using basic descriptions")

        phb_backgrounds = []

        # 2024 SRD includes only 4 backgrounds: Acolyte, Criminal, Sage, Soldier
        # Extract the remaining 12 from XPHB as non-SRD content, plus every
        # background from the supplements
        srd_backgrounds = {'Acolyte', 'Criminal', 'Sage', 'Soldier'}

        counts = {}
        seen = set()

        for bg in data.get('background', []):
            bg_source = bg.get('source')

            if bg_source not in BACKGROUND_SOURCES:
                continue
            # Only the 2024 PHB needs the SRD filter; the supplements are
            # non-SRD in their entirety.
            if bg_source == 'XPHB' and bg['name'] in srd_backgrounds:
                continue
            if bg['name'] in seen:
                continue
            seen.add(bg['name'])

            # Get description from fluff if available, otherwise from main data
            bg_fluff = fluff_data.get((bg['name'], bg_source))
            if bg_fluff and 'entries' in bg_fluff:
                desc = entries_to_text(bg_fluff['entries'])
            else:
                desc = entries_to_text(bg.get('entries', []))

            # Extract skill proficiencies (2024 format)
            skills = []
            if 'skillProficiencies' in bg:
                for skill_set in bg['skillProficiencies']:
                    if isinstance(skill_set, dict):
                        for skill_name, has_skill in skill_set.items():
                            if has_skill and skill_name != 'choose':
                                skills.append(skill_name.title())

            # Extract tool proficiencies
            tools = []
            if 'toolProficiencies' in bg:
                for tool_set in bg['toolProficiencies']:
                    if isinstance(tool_set, dict):
                        for tool_name, has_tool in tool_set.items():
                            if has_tool and tool_name != 'choose':
                                tools.append(tool_name.title())

            # Extract origin feat (2024 backgrounds grant a feat)
            origin_feat = None
            if 'feats' in bg and bg['feats']:
                # Parse feat name from the dict key
                feat_entry = bg['feats'][0] if bg['feats'] else {}
                if isinstance(feat_entry, dict):
                    feat_key = list(feat_entry.keys())[0] if feat_entry else ""
                    # Format: "magic initiate; cleric|xphb"
                    origin_feat = feat_key.split(';')[0].split('|')[0].strip().title()

            # Extract ability score pattern (2024 format)
            asi_json = None
            if 'ability' in bg:
                # 2024 backgrounds give +2/+1 or +1/+1/+1 from a list
                asi_json = json.dumps({"pattern": "2+1", "from": bg['ability']})

            phb_backgrounds.append({
                "id": 0,
                "name": bg['name'],
                "description": desc,
                "skillProficiencies": ','.join(skills) if skills else "",
                "toolProficiencies": ','.join(tools) if tools else None,
                "languages": None,
                "equipment": "",
                "feature": bg['name'] + " Background",
                "featureDescription": desc,
                "originFeat": origin_feat,
                "abilityScoreIncrease": asi_json
            })

            counts[bg_source] = counts.get(bg_source, 0) + 1

        for source in BACKGROUND_SOURCES:
            if counts.get(source):
                print(f"Loaded {counts[source]} non-SRD backgrounds from {SOURCE_NAMES[source]}")
        return phb_backgrounds
    except FileNotFoundError:
        print("Warning: backgrounds.json not found")
        return []
    except Exception as e:
        print(f"Error extracting backgrounds: {e}")
        import traceback
        traceback.print_exc()
        return []

# Source damage codes -> the damage types the app's equipment editor offers.
DAMAGE_TYPES = {
    'A': 'Acid', 'B': 'Bludgeoning', 'C': 'Cold', 'F': 'Fire', 'O': 'Force',
    'L': 'Lightning', 'N': 'Necrotic', 'P': 'Piercing', 'I': 'Poison',
    'Y': 'Psychic', 'R': 'Radiant', 'S': 'Slashing', 'T': 'Thunder'
}

# Source item type codes -> the app's four equipment types. Anything not
# listed here (wands, rings, potions, wondrous items) falls through to "Other".
ARMOR_TYPES = {'LA', 'MA', 'HA', 'S'}
WEAPON_TYPES = {'M', 'R'}
TOOL_TYPES = {'T', 'AT', 'INS', 'GS'}

# Proficiency each armor type requires, keyed by the same codes.
ARMOR_PROFICIENCY = {
    'LA': 'Light Armor', 'MA': 'Medium Armor', 'HA': 'Heavy Armor', 'S': 'Shields'
}


def type_code(item):
    """Bare source type abbreviation, with the |SOURCE suffix stripped."""
    return item.get('type', '').split('|')[0]


def format_cost(value):
    """Turn a source copper-piece value into a cost string."""
    if not value:
        return ""
    if value % 100 == 0:
        return f"{value // 100} gp"
    if value % 10 == 0:
        return f"{value // 10} sp"
    return f"{value} cp"


def load_item_vocabulary():
    """Build the abbreviation -> display name maps the source stores in items-base.json.

    Both properties and types are defined once per edition; the 2024 (XPHB)
    wording wins where a code was reprinted.
    """
    property_names = {}
    type_names = {}

    try:
        with open(data_path('items-base.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Warning: items-base.json not found, item properties will be unnamed")
        return property_names, type_names

    for prop in data.get('itemProperty', []):
        abbreviation = prop.get('abbreviation')
        if not abbreviation:
            continue
        # The name lives either on a named sub-entry or on the property itself.
        name = prop.get('name')
        for entry in prop.get('entries', []):
            if isinstance(entry, dict) and entry.get('name'):
                name = entry['name']
                break
        if name and (abbreviation not in property_names or prop.get('source') == 'XPHB'):
            property_names[abbreviation] = name.title() if name.islower() else name

    for item_type in data.get('itemType', []):
        abbreviation = item_type.get('abbreviation')
        name = item_type.get('name')
        if abbreviation and name and (abbreviation not in type_names or item_type.get('source') == 'XPHB'):
            type_names[abbreviation] = name

    return property_names, type_names


def convert_source_item(item, property_names, type_names):
    """Convert a source item to the app's homebrew equipment format."""
    code = type_code(item)

    if item.get('weapon') or code in WEAPON_TYPES:
        app_type = "Weapon"
    elif item.get('armor') or code in ARMOR_TYPES:
        app_type = "Armor"
    elif code in TOOL_TYPES:
        app_type = "Tool"
    else:
        app_type = "Other"

    # Damage, versatile damage folded in the way the books print it
    damage = item.get('dmg1')
    if damage and item.get('dmg2'):
        damage = f"{damage} ({item['dmg2']} versatile)"

    # Weapon properties, then the magic-item qualities worth surfacing
    properties = []
    for prop in item.get('property', []):
        abbreviation = prop.split('|')[0] if isinstance(prop, str) else prop.get('uid', '').split('|')[0]
        properties.append(property_names.get(abbreviation, abbreviation))

    rarity = item.get('rarity')
    if rarity and rarity not in ('none', 'unknown', 'varies', 'unknown (magic)'):
        properties.append(rarity.title())

    attunement = item.get('reqAttune')
    if attunement is True:
        properties.append("Requires Attunement")
    elif isinstance(attunement, str):
        properties.append(f"Requires Attunement {attunement}")

    # Proficiency needed to use it
    required_proficiency = None
    if app_type == "Weapon" and item.get('weaponCategory'):
        required_proficiency = f"{item['weaponCategory'].title()} Weapons"
    elif app_type == "Armor":
        required_proficiency = ARMOR_PROFICIENCY.get(code)

    # Fall back to the type's own name for items that carry no prose
    description = entries_to_text(item.get('entries', []))
    if not description:
        description = type_names.get(code, "")

    weapon_category = None
    if app_type == "Weapon" and item.get('weaponCategory'):
        weapon_category = item['weaponCategory'].title()

    return {
        "id": 0,
        "name": item['name'],
        "type": app_type,
        "weaponCategory": weapon_category,
        "description": description,
        "properties": properties,
        "cost": format_cost(item.get('value')),
        "weight": float(item.get('weight', 0) or 0),
        "damage": damage if app_type == "Weapon" else None,
        "damageType": DAMAGE_TYPES.get(item.get('dmgType')) if app_type == "Weapon" else None,
        "armorClass": item.get('ac') if app_type == "Armor" else None,
        "requiredProficiency": required_proficiency
    }


def extract_all_equipment():
    """Extract non-SRD equipment from the books in EQUIPMENT_SOURCES.

    Covers the mundane gear in items-base.json and the magic items in
    items.json. The generated variants in magicvariants.json (+1 Longsword and
    friends) are deliberately left out — they multiply out to thousands of
    entries the app has no way to present.
    """
    property_names, type_names = load_item_vocabulary()

    # name -> item, keeping only the highest-precedence printing
    by_name = {}
    reprints = {}
    counts = {}

    for filename, key in [('items-base.json', 'baseitem'), ('items.json', 'item')]:
        try:
            with open(data_path(filename), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Warning: {filename} not found")
            continue

        for item in data.get(key, []):
            source = item.get('source')
            if source not in EQUIPMENT_SOURCES:
                continue
            # Only the 2024 PHB needs the SRD filter; the supplements are
            # non-SRD in their entirety.
            if source == 'XPHB' and item.get('srd52'):
                continue
            # A _copy record is a stub the source resolves against another book at
            # load time; it carries no prose of its own, so let the printing it
            # points at supply the item instead.
            if '_copy' in item:
                continue

            name = item['name']
            existing = by_name.get(name)
            if existing is None:
                by_name[name] = convert_source_item(item, property_names, type_names)
                counts[source] = counts.get(source, 0) + 1
                by_name[name]['_source'] = source
                continue

            reprints.setdefault(name, [existing['_source']]).append(source)
            if SOURCE_PRIORITY[source] < SOURCE_PRIORITY[existing['_source']]:
                counts[existing['_source']] -= 1
                counts[source] = counts.get(source, 0) + 1
                by_name[name] = convert_source_item(item, property_names, type_names)
                by_name[name]['_source'] = source

    if reprints:
        print("\nEquipment printed in multiple books (keeping the newest):")
        for name, sources in sorted(reprints.items()):
            print(f"  {name}: {sources} → chose {by_name[name]['_source']}")

    equipment = sorted(by_name.values(), key=lambda x: x['name'])
    for item in equipment:
        item.pop('_source')

    for source in EQUIPMENT_SOURCES:
        if counts.get(source):
            print(f"Loaded {counts[source]} non-SRD equipment items from {SOURCE_NAMES[source]}")

    print(f"Extracted {len(equipment)} non-SRD equipment items")
    return equipment

def extract_class_features(class_file, class_name, non_srd_subclass_names=None):
    """Extract class features and subclass features from a source class JSON file.

    Args:
        class_file: Path to the class JSON file
        class_name: Name of the class
        non_srd_subclass_names: Optional set of non-SRD subclass short names to filter for

    Returns a (class_features, subclass_features_map) pair, where the map is
    keyed by (shortName, source). A subclass reprinted in a newer book — EFA's
    Alchemist, RHW's Grave Domain — keeps its printings apart so their features
    don't get merged into one list.
    """
    try:
        with open(class_file, 'r') as f:
            data = json.load(f)

        # Build mapping of (shortName, source) to full name for header feature filtering
        subclass_name_map = {}
        for sc in data.get('subclass', []):
            short_name = sc.get('shortName', sc.get('name'))
            full_name = sc.get('name')
            if short_name and full_name:
                subclass_name_map[(short_name, sc.get('source'))] = full_name

        # Extract class features, keyed by source so callers can pick a printing
        class_features_by_source = {}
        if 'classFeature' in data:
            for feature in data['classFeature']:
                if feature.get('className') != class_name:
                    continue
                # Skip optional rules
                if 'Optional Rule' in feature.get('name', ''):
                    continue

                class_features_by_source.setdefault(feature.get('source'), []).append({
                    "name": feature['name'],
                    "level": feature['level'],
                    "description": entries_to_text(feature.get('entries', []))
                })

        # Extract subclass features
        subclass_features_map = {}
        if 'subclassFeature' in data:
            for feature in data['subclassFeature']:
                subclass_name = feature.get('subclassShortName', '')
                if not subclass_name:
                    continue

                # Only extract features from the books we import, skipping the
                # 2014 PHB and anything else upstream carries
                feature_source = feature.get('source', '')
                if feature_source not in SUBCLASS_SOURCES:
                    continue

                # Filter to only non-SRD subclasses if filter provided
                if non_srd_subclass_names is not None and subclass_name not in non_srd_subclass_names:
                    continue

                key = (subclass_name, feature_source)
                if key not in subclass_features_map:
                    subclass_features_map[key] = []

                # Skip the subclass header feature (matches full subclass name at level 1-3)
                feature_name = feature.get('name', '')
                feature_level = feature.get('level', 0)
                full_subclass_name = subclass_name_map.get(key, subclass_name)

                # Common subclass start levels
                subclass_start_levels = [1, 2, 3]

                if feature_level in subclass_start_levels and feature_name == full_subclass_name:
                    continue

                subclass_features_map[key].append({
                    "name": feature_name,
                    "level": feature_level,
                    "description": entries_to_text(feature.get('entries', []))
                })

        if class_features_by_source or subclass_features_map:
            feature_count = sum(len(v) for v in class_features_by_source.values())
            print(f"  {class_name}: {feature_count} class features, {len(subclass_features_map)} subclass printings")

        return class_features_by_source, subclass_features_map

    except Exception as e:
        print(f"  Error extracting {class_name} features: {e}")
        return {}, {}

def extract_all_subclass_features(non_srd_subclass_names):
    """Extract subclass features from all class JSON files, filtered to only non-SRD subclasses.

    Args:
        non_srd_subclass_names: Set of non-SRD subclass short names to extract features for
    """
    all_subclass_features = {}

    # Map of class files to class names
    class_names = ["Artificer", "Barbarian", "Bard", "Cleric", "Druid", "Fighter",
                   "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard"]
    class_files = {
        data_path("class", f"class-{name.lower()}.json"): name for name in class_names
    }

    print("Extracting subclass features for non-SRD subclasses only...")

    artificer_class_features = []
    for class_file, class_name in class_files.items():
        class_features_by_source, subclass_features = extract_class_features(
            class_file, class_name, non_srd_subclass_names)

        # Save Artificer class features, preferring the newest printing (EFA's
        # 2024 Artificer over Tasha's).
        if class_name == "Artificer" and class_features_by_source:
            chosen = min(class_features_by_source,
                         key=lambda s: SOURCE_PRIORITY.get(s, 999))
            artificer_class_features = class_features_by_source[chosen]
            print(f"  Artificer class features: using the {SOURCE_NAMES.get(chosen, chosen)} printing "
                  f"({len(artificer_class_features)} features)")

        # Merge all subclass features
        all_subclass_features.update(subclass_features)

    return artificer_class_features, all_subclass_features


# ── Spell grants ────────────────────────────────────────────────────────────
# A feat, class or subclass lists the spells it grants under "additionalSpells".
# The app takes fixed grants: a class or subclass feature carries
# "spellsGranted" ("Bless, 5:Aid", where a prefix is the character level the
# spell arrives at) and one "spellUsageType"; a feat carries a JSON string with
# "fixedSpells", one "usageType", and optionally a class list and per-level
# counts to draw from. Whatever the app cannot state - a spell chosen by school,
# a grant that waits on a spell-slot level, casting that spends a resource or
# only works as a ritual, a choice between named options - is left out rather
# than approximated.

_SPELL_INDEX = None


def spell_index():
    """(name, level) by lower-cased source spell name, across every spell file.

    A spell the SRD prints under another name maps to that name, since that is
    the name the app's own spell list carries.
    """
    global _SPELL_INDEX
    if _SPELL_INDEX is None:
        _SPELL_INDEX = {}
        for path in sorted(glob.glob(data_path("spells", "spells-*.json"))):
            with open(path, "r", encoding="utf-8") as f:
                for spell in json.load(f).get("spell", []):
                    key = spell["name"].lower()
                    alias = spell.get("srd52")
                    if key not in _SPELL_INDEX or isinstance(alias, str):
                        name = alias if isinstance(alias, str) else spell["name"]
                        _SPELL_INDEX[key] = (name, spell.get("level"))
    return _SPELL_INDEX


def spell_ref(ref):
    """(name, level) for a reference such as "mage hand|xphb#c"."""
    key = ref.split("|")[0].split("#")[0].strip().lower()
    return spell_index().get(key) or (string.capwords(key), None)


def _per_rest_usage(cast, count_key):
    """The app's usage token for `count_key` castings per "daily" or "rest".

    >>> _per_rest_usage("daily", "1e"), _per_rest_usage("daily", "3"), _per_rest_usage("rest", "1")
    ('long-rest', 'per-day-3', 'short-rest')
    >>> _per_rest_usage("daily", "int") is None, _per_rest_usage("rest", "2") is None
    (True, True)
    """
    count = count_key.rstrip("e")
    if not count.isdigit():
        return None  # a count read from an ability modifier
    if cast == "daily":
        return "long-rest" if count == "1" else f"per-day-{count}"
    return "short-rest" if count == "1" else None


def _grants_in(option):
    """Each grant in one additionalSpells option, as (usage, level, item).

    usage is the app's usage token, None for always prepared. level is the
    character level the grant arrives at, None for with the grant itself. item
    is a spell reference string, or a {"choose": ...} object.

    >>> _grants_in({"prepared": {"3": ["bless"], "s2": ["aid"]},
    ...             "innate": {"_": {"daily": {"1": ["misty step"]}, "ritual": ["alarm"]}},
    ...             "expanded": {"s1": ["shield"]}})
    [(None, 3, 'bless'), ('long-rest', None, 'misty step')]
    """
    grants = []
    for kind in ("prepared", "known", "innate"):
        for level_key, value in (option.get(kind) or {}).items():
            if level_key == "_":
                level = None
            elif level_key.isdigit():
                level = int(level_key)
            else:
                continue  # waits on a spell-slot level
            if isinstance(value, list):
                usage = "at-will" if kind == "innate" else None
                grants += [(usage, level, item) for item in value]
                continue
            for cast, spells in value.items():
                if cast == "will":
                    grants += [("at-will", level, item) for item in spells]
                elif cast in ("daily", "rest"):
                    for count_key, items in spells.items():
                        usage = _per_rest_usage(cast, count_key)
                        if usage:
                            grants += [(usage, level, item) for item in items]
    return grants


def _chosen_option(additional):
    """The option a grant applies without asking, or None.

    Unnamed options are fallbacks behind the first ("if you already know it,
    choose another"); named ones are a choice the app leaves to the DM.

    >>> _chosen_option([{"known": 1}, {"known": 2}])
    {'known': 1}
    >>> _chosen_option([{"name": "Dao"}, {"name": "Djinni"}]) is None
    True
    """
    if not additional:
        return None
    if len(additional) == 1 or not any(option.get("name") for option in additional):
        return additional[0]
    return None


def _grant_feature(features, level):
    """The feature that should carry a grant arriving at `level`.

    The feature gained at that level, or failing one the latest before it; a
    grant listed before the first feature arrives with the first. A feature
    named "... Spells" wins a tie. None when every candidate already carries a
    grant.

    >>> features = [{"name": "Circle", "level": 3}, {"name": "Grave Spells", "level": 3},
    ...             {"name": "Reaper", "level": 17}]
    >>> _grant_feature(features, 5)["name"], _grant_feature(features, 1)["name"]
    ('Grave Spells', 'Grave Spells')
    >>> _grant_feature(features, 17)["name"]
    'Reaper'
    """
    free = [f for f in features if "spellsGranted" not in f]
    if not free:
        return None
    reached = [f for f in free if level is not None and f["level"] <= level]
    if reached:
        target = max(f["level"] for f in reached)
    elif level is None or all(f["level"] > level for f in features):
        target = min(f["level"] for f in free)
    else:
        return None
    at_level = [f for f in free if f["level"] == target]
    return next((f for f in at_level if f["name"].endswith("Spells")), at_level[0])


def attach_spell_grants(features, additional):
    """Write a class's or subclass's fixed spell grants onto its features.

    Grants cast the same way share one feature. Returns how many spells were
    placed and how many had no feature to go on.
    """
    option = _chosen_option(additional)
    if option is None:
        return 0, 0
    groups = {}
    for usage, level, item in _grants_in(option):
        if isinstance(item, str):
            name = spell_ref(item)[0]
            spells = groups.setdefault(usage, [])
            if name not in (n for _, n in spells):
                spells.append((level, name))

    placed = unplaced = 0
    for usage, spells in groups.items():
        levels = [lvl for lvl, _ in spells if lvl is not None]
        feature = _grant_feature(features, min(levels) if levels else None)
        if feature is None:
            unplaced += len(spells)
            continue
        feature["spellsGranted"] = ", ".join(
            name if lvl is None or lvl <= feature["level"] else f"{lvl}:{name}"
            for lvl, name in spells)
        if usage:
            feature["spellUsageType"] = usage
        placed += len(spells)
    return placed, unplaced


def _choose_filter(text):
    """(class, spell level, ritual only) for a "choose" filter, or None.

    Only a filter on one spell level, optionally one or more classes (the
    first is taken) and the ritual tag, can be drawn from by the app.

    >>> _choose_filter("level=0|class=cleric;Wizard")
    ('Cleric', 0, False)
    >>> _choose_filter("level=1|components & miscellaneous=ritual")
    ('Any', 1, True)
    >>> _choose_filter("level=1|school=E;D") is None, _choose_filter("level=0;1|class=Bard") is None
    (True, True)
    """
    filters = {}
    for part in text.split("|"):
        key, _, value = part.partition("=")
        filters[key.strip().lower()] = value.strip()
    ritual = filters.pop("components & miscellaneous", None)
    level = filters.pop("level", "")
    class_list = filters.pop("class", None)
    if filters or not level.isdigit() or ritual not in (None, "ritual"):
        return None
    spell_class = class_list.split(";")[0].strip().capitalize() if class_list else "Any"
    return spell_class, int(level), ritual == "ritual"


def feat_spell_grant(additional):
    """The app's grantsSpells JSON string for a feat, or None if nothing fits.

    The app gives a feat one usage for its leveled spells; a cantrip is at will
    whatever it says. Leveled grants cast another way than the first are
    dropped, as is a choice from a second class list or one that arrives after
    level 1.
    """
    option = _chosen_option(additional)
    if option is None:
        return None
    usage = None
    usage_set = False
    fixed, counts = [], {}
    spell_class, ritual_only = None, False

    def usage_fits(item_usage, spell_level):
        nonlocal usage, usage_set
        if spell_level == 0:
            return True
        if not usage_set:
            usage, usage_set = item_usage, True
        return item_usage == usage

    for item_usage, level, item in _grants_in(option):
        if isinstance(item, str):
            name, spell_level = spell_ref(item)
            if usage_fits(item_usage, spell_level):
                entry = name if level is None or level <= 1 else f"{level}:{name}"
                if entry not in fixed:
                    fixed.append(entry)
            continue
        choice = item.get("choose")
        if not isinstance(choice, str) or (level is not None and level > 1):
            continue
        parsed = _choose_filter(choice)
        if parsed is None:
            continue
        choice_class, spell_level, ritual = parsed
        if spell_class not in (None, choice_class) or not usage_fits(item_usage, spell_level):
            continue
        spell_class, ritual_only = choice_class, ritual_only or ritual
        key = "cantrips" if spell_level == 0 else f"level{spell_level}"
        counts[key] = counts.get(key, 0) + item.get("count", 1)

    if not fixed and not counts:
        return None
    grant = {}
    if usage:
        grant["usageType"] = usage
    if fixed:
        grant["fixedSpells"] = fixed
    if counts:
        grant["class"] = spell_class
        grant["spells"] = counts
        if ritual_only:
            grant["ritualOnly"] = True
    return json.dumps(grant, ensure_ascii=False)


def extract_phb_subclasses():
    """Extract non-SRD subclasses from the books in SUBCLASS_SOURCES."""
    # 2024 SRD subclass shortNames to exclude (the source's srd52 flag is incomplete)
    # Official 2024 SRD includes these 12 subclasses:
    SRD_SUBCLASS_SHORTNAMES = {
        'Berserker',        # Barbarian - Path of the Berserker
        'Lore',             # Bard - College of Lore
        'Life',             # Cleric - Life Domain
        'Land',             # Druid - Circle of the Land
        'Champion',         # Fighter - Champion
        'Open Hand',        # Monk - Way of the Open Hand
        'Devotion',         # Paladin - Oath of Devotion
        'Hunter',           # Ranger - Hunter
        'Thief',            # Rogue - Thief
        'Draconic',         # Sorcerer - Draconic Bloodline
        'Fiend',            # Warlock - The Fiend
        'Evocation'         # Wizard - School of Evocation
    }

    try:
        class_dir = data_path('class')
        class_files = [f for f in os.listdir(class_dir) if f.startswith('class-') and not f.startswith('fluff-')]

        subclasses = []

        for class_file in class_files:
            with open(os.path.join(class_dir, class_file), 'r', encoding='utf-8') as f:
                data = json.load(f)

                for sc in data.get('subclass', []):
                    sc_short_name = sc.get('shortName', sc.get('name'))
                    sc_source = sc.get('source')

                    if sc_source not in SUBCLASS_SOURCES:
                        continue
                    # Only the 2024 PHB needs the SRD filter; the supplements
                    # are non-SRD in their entirety.
                    if sc_source == 'XPHB' and sc_short_name in SRD_SUBCLASS_SHORTNAMES:
                        continue

                    class_name = sc.get('className')
                    sc_name = sc.get('name', sc.get('shortName'))
                    sc_short_name = sc.get('shortName', sc_name)

                    # Get description from the level 3 subclassFeature entry (introductory feature)
                    desc = ""
                    for feature in data.get('subclassFeature', []):
                        if (feature.get('className') == class_name and
                            feature.get('subclassShortName') == sc_short_name and
                            feature.get('source') == sc_source and
                            feature.get('level') == 3 and
                            feature.get('name') == sc_name):
                            # Try to extract description from this feature
                            feature_desc = entries_to_text(feature.get('entries', []))
                            if feature_desc:  # Use the first non-empty description found
                                desc = feature_desc
                                break

                    # Fallback to subclass entries if no feature found
                    if not desc:
                        desc = entries_to_text(sc.get('entries', []))

                    subclasses.append({
                        "id": 0,
                        "parentClassId": None,
                        "parentClassName": class_name,
                        "name": sc_name,
                        "description": desc,
                        "features": [],
                        # Tracked for deduplication, feature matching and
                        # spell grants; all stripped before the JSON is written.
                        "_source": sc_source,
                        "_shortName": sc_short_name,
                        "_additionalSpells": sc.get('additionalSpells')
                    })

        # Remove duplicates, keeping the highest-precedence printing
        seen = {}  # key -> subclass_dict
        duplicates_found = {}  # Track which subclasses have duplicates

        for sc in subclasses:
            key = (sc['parentClassName'], sc['name'])
            sc_source = sc['_source']
            current_priority = SOURCE_PRIORITY.get(sc_source, 999)

            if key not in seen:
                # First time seeing this subclass
                seen[key] = sc
                continue

            # We've seen this before - track it
            existing_source = seen[key]['_source']
            if key not in duplicates_found:
                duplicates_found[key] = [existing_source]
            duplicates_found[key].append(sc_source)

            if current_priority < SOURCE_PRIORITY.get(existing_source, 999):
                # Current source has higher priority, replace
                seen[key] = sc

        # Print duplicate resolution info
        if duplicates_found:
            precedence = ' > '.join(SUBCLASS_SOURCES)
            print(f"\nDuplicate subclasses found (prioritizing {precedence}):")
            for (parent_class, sc_name), sources in sorted(duplicates_found.items()):
                chosen_source = seen[(parent_class, sc_name)]['_source']
                print(f"  {parent_class} - {sc_name}: {sources} → chose {chosen_source}")

        # Sort by class name, then subclass name
        unique_subclasses = sorted(seen.values(),
                                   key=lambda x: (x['parentClassName'], x['name']))

        print(f"Extracted {len(unique_subclasses)} non-SRD subclasses from "
              f"{'/'.join(SUBCLASS_SOURCES)}")
        return unique_subclasses

    except FileNotFoundError:
        print("Warning: class files not found")
        return []

# ── Monsters ────────────────────────────────────────────────────────────────
# Read straight from the source bestiary, like every other extractor here.
# The helpers below turn one bestiary entry into the stat-block text the app
# stores: the header lines, then each section as "**Name.** body" entries.


# {@actSaveFail 2} is a numbered failure, printed "Second Failure:".
_ORDINAL = {"1": "First", "2": "Second", "3": "Third", "4": "Fourth", "5": "Fifth"}


# A handful of tags render to something other than their first argument.
def _tag_replace(m):
    tag, _, body = m.group(1).partition(" ")
    parts = body.split("|")
    first = parts[0].strip()
    display = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else first
    if tag in ("dice", "damage", "autodice"):
        return first
    # The 2024 stat-block labels. Each tag stands alone before the text
    # it labels, so it renders as the printed label and nothing else.
    if tag == "actSaveFail":
        return f"{_ORDINAL.get(first, first)} Failure:" if first else "Failure:"
    if tag == "actSaveSuccess":
        return "Success:"
    if tag == "actSaveSuccessOrFail":
        return "Failure or Success:"
    if tag == "actSaveFailBy":
        return f"Failure by {first} or More:"
    if tag == "actTrigger":
        return "Trigger:"
    if tag == "actResponse":
        # {@actResponse d} runs straight into a save:
        # "Response—Wisdom Saving Throw".
        return "Response\u2014" if first == "d" else "Response:"
    if tag in ("scaledice", "scaledamage"):
        # {@scaledamage base|levelRange|perLevel(|mode(|display))}. These appear
        # only in at-higher-levels text, where the sentence reads "the damage
        # increases by X for each spell slot level above N", so X is the
        # per-level increment, not the base.
        if len(parts) >= 5 and parts[4].strip():
            return parts[4].strip()
        return parts[2].strip() if len(parts) >= 3 and parts[2].strip() else first
    if tag == "hit":
        n = first
        return f"+{n}" if not n.startswith(("+", "-")) else n
    if tag == "dc":
        return f"DC {first}"
    if tag == "chance":
        return f"{first} percent"
    if tag == "recharge":
        return f"(Recharge {first}+)" if first else "(Recharge)"
    if tag in ("h",):
        return "Hit: "
    if tag in ("atk",):
        amap = {"mw": "Melee Weapon Attack:", "rw": "Ranged Weapon Attack:",
                "ms": "Melee Spell Attack:", "rs": "Ranged Spell Attack:",
                "m": "Melee Attack:", "r": "Ranged Attack:"}
        return amap.get(first, "Attack:")
    if tag in ("note", "i", "b", "bold", "italic", "s", "u", "style", "color",
               "highlight", "comic", "comicH1"):
        return display
    # spell/item/condition/skill/creature/variantrule/action/status/quickref/etc.
    return display


_TAG_RE = re.compile(r"\{@([^{}]+)\}")


def strip_markup(text):
    if not isinstance(text, str):
        return text
    prev = None
    out = text
    # iterate to resolve nested tags
    while prev != out:
        prev = out
        out = _TAG_RE.sub(_tag_replace, out)
    # tidy whitespace
    out = out.replace("—", "—").replace("’", "’")
    return out.strip()


def flatten(entries, depth=0):
    """Render a source entry (str | dict | list) to a markdown string."""
    if entries is None:
        return ""
    if isinstance(entries, str):
        return strip_markup(entries)
    if isinstance(entries, list):
        return "\n\n".join(p for p in (flatten(e, depth) for e in entries) if p)
    if isinstance(entries, dict):
        return _flatten_dict(entries, depth)
    return strip_markup(str(entries))


def _flatten_dict(e, depth):
    etype = e.get("type", "entries")
    name = e.get("name")
    if etype in ("entries", "section", "inset", "insetReadaloud", "variantInner",
                 "variant", "flowBlock", "optfeature"):
        body = flatten(e.get("entries", []), depth + 1)
        if name:
            return f"**{strip_markup(name)}.** {body}".strip()
        return body
    if etype == "list":
        items = []
        for it in e.get("items", []):
            txt = flatten(it, depth + 1)
            items.append(f"- {txt}" if txt and not txt.startswith("- ") else txt)
        return "\n".join(items)
    if etype == "item":
        body = flatten(e.get("entries", e.get("entry", [])), depth + 1)
        if name:
            return f"**{strip_markup(name)}.** {body}".strip()
        return body
    if etype == "table":
        return _flatten_table(e)
    if etype in ("cell", "row"):
        return flatten(e.get("entries", e.get("roll", "")), depth)
    if "entries" in e:
        body = flatten(e["entries"], depth + 1)
        return f"**{strip_markup(name)}.** {body}".strip() if name else body
    if "entry" in e:
        return flatten(e["entry"], depth)
    return ""


def _flatten_table(e):
    cols = [strip_markup(c) if isinstance(c, str) else flatten(c) for c in e.get("colLabels", [])]
    lines = []
    if e.get("caption"):
        lines.append(f"*{strip_markup(e['caption'])}*")
    if cols:
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("| " + " | ".join("---" for _ in cols) + " |")
    for row in e.get("rows", []):
        cells = row.get("row", row) if isinstance(row, dict) else row
        rendered = []
        for c in cells:
            rendered.append(flatten(c).replace("\n", " ") if not isinstance(c, str) else strip_markup(c))
        lines.append("| " + " | ".join(rendered) + " |")
    return "\n".join(lines)


def _fmt_ac(ac):
    out = []
    for a in ac or []:
        if isinstance(a, int):
            out.append(str(a))
        elif isinstance(a, dict):
            s = str(a.get("ac", ""))
            if a.get("from"):
                s += f" ({', '.join(strip_markup(x) for x in a['from'])})"
            out.append(s)
    return ", ".join(out)


def _speed_value(v):
    """One movement value -> its printed distance, condition and all.

    The source writes a mode either as a bare number (30) or as
    {"number": 90, "condition": "(hover)"}; the SRD prints the condition
    alongside the distance ("Fly 90 ft. (hover)"). None for anything
    that isn't a distance — notably the canHover flag (bool is an int
    subclass, so it has to be rejected before the int check) and the "choose"
    / "alternate" sub-objects, which carry no "number" of their own.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, str)):
        return f"{v} ft."
    if isinstance(v, dict) and "number" in v:
        cond = strip_markup(str(v.get("condition") or "")).strip()
        return f"{v['number']} ft. {cond}".strip()
    return None


def _fmt_speed(sp):
    """Movement modes -> the printed Speed line (run: python3 -m doctest extract_homebrew.py).

    >>> _fmt_speed({"walk": 10, "fly": {"number": 90, "condition": "(hover)"},
    ...             "canHover": True})  # Air Elemental
    '10 ft., fly 90 ft. (hover)'
    >>> _fmt_speed({"walk": 30,  # Werebear
    ...             "alternate": {"walk": [{"number": 40, "condition": "(bear form only)"}]},
    ...             "climb": {"number": 30, "condition": "(bear form only)"}})
    '30 ft., 40 ft. (bear form only), climb 30 ft. (bear form only)'
    >>> _fmt_speed({"walk": 20, "choose": {"from": ["climb", "fly"], "amount": 20,
    ...                                    "note": "(DM's choice)"}})  # Swarm of Insects
    "20 ft., climb or fly 20 ft. (DM's choice)"
    """
    if isinstance(sp, (int, str)):
        return f"{sp} ft."
    sp = sp or {}
    parts, others = [], []
    for k, v in sp.items():
        seg = _speed_value(v)
        if seg is None:
            continue
        (parts if k == "walk" else others).append(seg if k == "walk" else f"{k} {seg}")
    # A shapechanger's alternate-form speeds sit under "alternate", one list per
    # mode. They print right after the base walking speed, and a walking speed
    # there carries no mode label: "30 ft., 40 ft. (bear form only)".
    for k, vs in (sp.get("alternate") or {}).items():
        for v in vs if isinstance(vs, list) else [vs]:
            seg = _speed_value(v)
            if seg is not None:
                parts.append(seg if k == "walk" else f"{k} {seg}")
    # One distance for whichever of several modes the creature takes, as when
    # a swarm climbs or flies.
    choose = sp.get("choose")
    if isinstance(choose, dict) and choose.get("from"):
        note = strip_markup(str(choose.get("note") or "")).strip()
        others.append(f"{' or '.join(choose['from'])} {choose.get('amount')} ft. {note}".strip())
    return ", ".join(parts + others)


def _fmt_cr(cr):
    if isinstance(cr, dict):
        return str(cr.get("cr", ""))
    return str(cr) if cr is not None else ""


def _abilities(m):
    return {a: m.get(a) for a in ("str", "dex", "con", "int", "wis", "cha") if m.get(a) is not None}


def _named_block_list(items):
    """Stat-block entries -> "**Name.** body" strings, one per entry."""
    out = []
    for it in items or []:
        nm = strip_markup(it.get("name", "")) if isinstance(it, dict) else ""
        body = flatten(it.get("entries", []) if isinstance(it, dict) else it)
        out.append(f"**{nm}.** {body}".strip() if nm else body)
    return [p for p in out if p]


# Books printed under the 2024 rules. Their stat blocks use the 2024 layout:
# "At Will:" / "1/Day Each:" spell lists and the "Legendary Action Uses" line.
# The 2014-era books (TCE, XGE, MPMM) print "At will:" / "1/day each:" and the
# older "can take 3 legendary actions" paragraph.
_MODERN_SOURCES = {"XPHB", "XDMG", "XMM", "EFA", "FRAiF", "FRHoF", "RHW", "AU"}


_SIZE_WORD = {"T": "Tiny", "S": "Small", "M": "Medium", "L": "Large", "H": "Huge", "G": "Gargantuan"}


_TYPE_PLURAL = {"aberration": "Aberrations", "beast": "Beasts", "celestial": "Celestials",
                "construct": "Constructs", "dragon": "Dragons", "elemental": "Elementals",
                "fey": "Fey", "fiend": "Fiends", "giant": "Giants", "humanoid": "Humanoids",
                "monstrosity": "Monstrosities", "ooze": "Oozes", "plant": "Plants",
                "undead": "Undead"}


def _fmt_type(t):
    """A monster's creature type, a swarm's included.

    >>> _fmt_type({"type": "beast", "swarmSize": "T"})  # Swarm of Rats
    'swarm of Tiny Beasts'
    >>> _fmt_type({"type": "undead", "swarmSize": "T"})
    'swarm of Tiny Undead'
    >>> _fmt_type("dragon")
    'dragon'
    """
    if not isinstance(t, dict):
        return t
    base = t.get("type")
    if t.get("swarmSize") and isinstance(base, str):
        plural = _TYPE_PLURAL.get(base, base.capitalize() + "s")
        return f"swarm of {_SIZE_WORD.get(t['swarmSize'], t['swarmSize'])} {plural}"
    return base


# A monster's spellcasting lives in its own array upstream, apart from its
# traits and actions; each entry says which section it prints in.
_SC_SECTION = {"trait": "traits", "action": "actions", "bonus": "bonus_actions",
               "reaction": "reactions", "legendary": "legendary_actions"}


# The order the source lists a spellcasting entry's frequencies in.
_SC_LIST_PROPS = ("constant", "will", "recharge", "legendary", "charges", "rest",
                  "restLong", "daily", "weekly", "monthly", "yearly", "ritual")


_SC_PLAIN_LABEL = {"constant": "Constant", "will": "At Will", "ritual": "Rituals"}


_SC_PER = {"rest": "Rest", "restLong": "Long Rest", "daily": "Day", "weekly": "Week",
           "monthly": "Month", "yearly": "Year"}


def _uses_count(key):
    """ "2e" (two uses of each) or "2" -> 2."""
    return int(key[:-1]) if key.endswith("e") else int(key)


def _spell_list_label(prop, key, modern=True):
    """The label before one spell list, as the book prints it.

    >>> _spell_list_label("daily", "1e"), _spell_list_label("daily", "3")
    ('1/Day Each', '3/Day')
    >>> _spell_list_label("daily", "2e", modern=False), _spell_list_label("will", None, modern=False)
    ('2/day each', 'At will')
    >>> _spell_list_label("legendary", "2")
    '2 Legendary Actions'
    """
    if prop in _SC_PLAIN_LABEL:
        label = _SC_PLAIN_LABEL[prop]
        return label if modern else label[0] + label[1:].lower()
    n = _uses_count(key)
    if prop == "recharge":
        label = f"(Recharge {n}+)"
    elif prop == "legendary":
        label = f"{n} Legendary Action{'' if n == 1 else 's'}"
    elif prop == "charges":
        label = f"{n} Charge{'' if n == 1 else 's'}"
    else:
        label = f"{n}/{_SC_PER[prop]}"
    if key.endswith("e"):
        label += " Each"
    return label if modern else label.lower()


def _spell_list(items):
    """One frequency's spells, comma-separated, in the order the book prints them."""
    names = []
    for it in items or []:
        if isinstance(it, dict):
            if it.get("hidden"):
                continue
            it = it.get("entry", "")
        text = strip_markup(it)
        if text:
            names.append(text)
    return ", ".join(names)


def _spellcasting_block(sc, modern=True):
    """One upstream spellcasting entry -> a "**Name.** body" block.

    The header sentence comes first, then each visible spell list on a line of
    its own, the way the SRD prints them. A list the header
    already spells out is marked hidden upstream and stays out.

    >>> print(_spellcasting_block({"name": "Spellcasting", "headerEntries": [
    ...     "The mage casts one of the following spells (spell save {@dc 14}):"],
    ...     "will": ["{@spell Light|XPHB}", "{@spell Detect Magic|XPHB}"],
    ...     "daily": {"1e": ["{@spell Fly|XPHB}"], "2e": ["{@spell Invisibility|XPHB}"]}}))
    **Spellcasting.** The mage casts one of the following spells (spell save DC 14):
    At Will: Light, Detect Magic
    2/Day Each: Invisibility
    1/Day Each: Fly
    >>> _spellcasting_block({"name": "Misty Step (3/Day)", "headerEntries": [
    ...     "The mage casts {@spell Misty Step|XPHB}."], "daily": {"3": ["{@spell Misty Step|XPHB}"]},
    ...     "hidden": ["daily"]})
    '**Misty Step (3/Day).** The mage casts Misty Step.'
    """
    hidden = set(sc.get("hidden") or [])
    lines = []
    for prop in _SC_LIST_PROPS:
        value = sc.get(prop)
        if not value or prop in hidden:
            continue
        if isinstance(value, list):
            lines.append(f"{_spell_list_label(prop, None, modern)}: {_spell_list(value)}")
            continue
        for key in sorted(value, key=_uses_count, reverse=True):
            lines.append(f"{_spell_list_label(prop, key, modern)}: {_spell_list(value[key])}")
    body = "\n\n".join(p for p in (flatten(e) for e in sc.get("headerEntries") or []) if p)
    if lines:
        body = (body + "\n" if body else "") + "\n".join(lines)
    footer = [p for p in (flatten(e) for e in sc.get("footerEntries") or []) if p]
    if footer:
        body += "\n\n" + "\n\n".join(footer)
    name = strip_markup(sc.get("name", ""))
    return f"**{name}.** {body}".strip() if name else body


_ATTACK_BODY = re.compile(r"(?:m|r|m,r) [+-]\d")


def _block_title(block):
    m = re.match(r"\*\*(.+?)\.\*\*", block)
    return m.group(1) if m else ""


def _leads_section(block):
    """Is this an entry the SRD prints ahead of a section's alphabetical run?

    That is Multiattack, the attacks and the Legendary Action Uses line, plus
    any untitled lead-in paragraph.
    """
    title = _block_title(block)
    if not title or title == "Multiattack" or title.startswith("Legendary Action Uses"):
        return True
    return bool(_ATTACK_BODY.match(block[len(title) + 5:].lstrip()))


def _insert_in_order(blocks, block):
    """Place a spellcasting entry where the SRD prints it, in place.

    SRD 5.2.1 orders a section as Multiattack, the attacks, then everything
    else alphabetically, which puts the Adult Gold Dragon's Spellcasting between
    Fire Breath and Weakening Breath.

    >>> blocks = ["**Multiattack.** x", "**Rend.** m +14, reach 10 ft.", "**Fire Breath.** x",
    ...           "**Weakening Breath.** x"]
    >>> _insert_in_order(blocks, "**Spellcasting.** x")
    >>> [_block_title(b) for b in blocks]
    ['Multiattack', 'Rend', 'Fire Breath', 'Spellcasting', 'Weakening Breath']
    """
    i = 0
    while i < len(blocks) and _leads_section(blocks[i]):
        i += 1
    key = _block_title(block).lower()
    while i < len(blocks) and _block_title(blocks[i]).lower() < key:
        i += 1
    blocks.insert(i, block)


def _short_name(m, text=""):
    """How a stat block refers to its creature: "the dragon", "the mummy".

    An age-and-colour dragon shortens to "dragon"; otherwise the whole name is
    used. Some blocks shorten further, "the mummy" for the Mummy Lord and "the
    sphinx" for both sphinxes, and the block's own text shows which. So when
    the full name never appears after "the" in its entries, take the first or
    last word of the name if one of those does.

    >>> _short_name({"name": "Adult Gold Dragon"})
    'the dragon'
    >>> _short_name({"name": "Mummy Lord"}, "The mummy makes two Rotting Fist attacks.")
    'the mummy'
    >>> _short_name({"name": "Aboleth"}, "The aboleth makes two Tentacle attacks.")
    'the aboleth'
    """
    if m.get("isNamedCreature"):
        short = m.get("shortName")
        return short if isinstance(short, str) else m["name"].split(",")[0].split(" ")[0]
    short = m.get("shortName")
    if short is True:
        return f"the {m['name']}"
    if isinstance(short, str):
        return f"the {short.lower()}"
    base = re.sub(r"(?:adult|ancient|young) \w+ (dragon|dracolich)", r"\1",
                  m["name"].split(",")[0], flags=re.I).lower()
    if text and not re.search(rf"\bthe {re.escape(base)}\b", text, re.I):
        words = base.split()
        for candidate in (words[0], words[-1]):
            if re.search(rf"\bthe {re.escape(candidate)}\b", text, re.I):
                return f"the {candidate}"
    return f"the {base}"


def _legendary_intro(m, modern=True, text=""):
    """The paragraph a Legendary Actions section opens with.

    The 2024 layout prints a "Legendary Action Uses" entry, the 2014 one the
    "can take 3 legendary actions" paragraph; upstream's legendaryHeader, when
    present, replaces either.

    >>> _legendary_intro({"name": "Adult Gold Dragon", "legendaryActionsLair": 4})
    ["**Legendary Action Uses: 3 (4 in Lair).** Immediately after another creature's turn, the dragon can expend a use to take one of the following actions. The dragon regains all expended uses at the start of each of its turns."]
    """
    if m.get("legendaryHeader"):
        return [p for p in (flatten(e) for e in m["legendaryHeader"]) if p]
    uses = m.get("legendaryActions") or 3
    lair = m.get("legendaryActionsLair") or uses
    short = _short_name(m, text)
    title_short = short[0].upper() + short[1:]
    pronoun = "their" if m.get("isNamedCreature") else "its"
    if modern:
        in_lair = f" ({lair} in Lair)" if lair != uses else ""
        return [f"**Legendary Action Uses: {uses}{in_lair}.** Immediately after another "
                f"creature's turn, {short} can expend a use to take one of the following "
                f"actions. {title_short} regains all expended uses at the start of each of "
                f"{pronoun} turns."]
    in_lair = f" (or {lair} when in {pronoun} lair)" if lair != uses else ""
    return [f"{title_short} can take {uses} legendary action{'s' if uses > 1 else ''}{in_lair}, "
            f"choosing from the options below. Only one legendary action can be used at a "
            f"time and only at the end of another creature's turn. {title_short} regains "
            f"spent legendary actions at the start of {pronoun} turn."]


_MONSTER_SECTIONS = (("trait", "traits"), ("action", "actions"), ("reaction", "reactions"),
                     ("bonus", "bonus_actions"), ("legendary", "legendary_actions"))


def _monster_sections(m):
    """A monster's text sections, spellcasting folded in, as "**Name.** body" lists."""
    modern = m.get("source") in _MODERN_SOURCES
    sections = {label: _named_block_list(m.get(key)) for key, label in _MONSTER_SECTIONS}
    for sc in m.get("spellcasting") or []:
        label = _SC_SECTION.get(sc.get("displayAs") or "trait", "traits")
        _insert_in_order(sections[label], _spellcasting_block(sc, modern))
    if sections["legendary_actions"]:
        text = "\n\n".join(blk for blocks in sections.values() for blk in blocks)
        sections["legendary_actions"][:0] = _legendary_intro(m, modern, text)
    return sections


_ALIGN = {"L": "Lawful", "C": "Chaotic", "N": "Neutral", "NX": "Neutral", "NY": "Neutral",
          "G": "Good", "E": "Evil", "U": "Unaligned", "A": "Any alignment"}


def _fmt_alignment(al):
    """Source alignment codes -> the printed line: ["C", "E"] -> "Chaotic Evil"."""
    if not al:
        return None
    parts = []
    for a in al:
        if isinstance(a, dict):
            if a.get("special"):
                parts.append(a["special"])
            elif a.get("alignment"):
                parts.append(_fmt_alignment(a["alignment"]))
        else:
            parts.append(_ALIGN.get(a, a))
    return strip_markup(" ".join(p for p in parts if p)) or None


def _cap(s):
    """Damage types and conditions are lowercase in the source data; the SRD prints them capitalised."""
    return s[:1].upper() + s[1:] if isinstance(s, str) else s


def _fmt_typed_list(items, key):
    """immune/resist/vulnerable/conditionImmune -> one printed line.

    Plain tokens join with ", " in source order. A conditional group
    ({key: [...], "note": "from nonmagical attacks"}) keeps its note, and
    groups are separated with "; " the way the 2024 stat blocks print them.
    """
    if not items:
        return None
    out, run = [], []

    def flush():
        if run:
            out.append(", ".join(run))
            run.clear()

    for it in items:
        if isinstance(it, dict):
            flush()
            if it.get("special"):
                out.append(strip_markup(it["special"]))
            else:
                inner = ", ".join(_cap(strip_markup(x)) for x in it.get(key, []))
                out.append((inner + " " + strip_markup(it.get("note", ""))).strip())
        else:
            run.append(_cap(strip_markup(it)))
    flush()
    return "; ".join(g for g in out if g) or None


def _fmt_skills(sk):
    """Skill bonuses keyed by lowercase skill name, values as printed ("+5").

    The rare "other" -> oneOf form (a creature with one skill of the
    listener's choice) flattens to a single "one of" entry.
    """
    if not sk:
        return None
    out = {}
    for k, v in sk.items():
        if k == "other":
            for o in v or []:
                one = o.get("oneOf") if isinstance(o, dict) else None
                if one:
                    out["one of"] = ", ".join(f"{_cap(n)} {b}" for n, b in one.items())
        else:
            out[k] = v
    return out or None


def _joined(items):
    if not items:
        return None
    return ", ".join(strip_markup(x) for x in items if isinstance(x, str)) or None


# Books whose non-SRD monsters we import, in the order a name collision is
# resolved: 2024-rules books first (XMM is the 2025 Monster Manual, whose SRD
# blocks are skipped; the rest are 2024-era releases), then the 2014-era books.
# The homebrew importer matches on name and updates in place, so one file must
# carry one block per name.
MONSTER_SOURCES = ["XMM", "XPHB", "AU", "EFA", "FRAiF", "FRHoF", "RHW", "MPMM", "TCE", "XGE"]

VALID_MONSTER_SIZES = {"T", "S", "M", "L", "H", "G"}
ABILITY_ABBR = {"str": "Str", "dex": "Dex", "con": "Con", "int": "Int", "wis": "Wis", "cha": "Cha"}


def _printed_bonuses(bonuses, label_for):
    """{"dex": "+6", "wis": "+7"} -> "Dex +6, Wis +7", in source order."""
    if not bonuses:
        return None
    return ", ".join(f"{label_for(k)} {v}" for k, v in bonuses.items())


def _skill_label(key):
    # "sleight of hand" -> "Sleight of Hand"; the "one of" pseudo-key stays as is.
    if key == "one of":
        return "one of"
    return " ".join(w if w == "of" else w.capitalize() for w in key.split())


def convert_monster(m):
    """One bestiary_record() -> the app's SerializableHomebrewMonster shape.

    Uses the same fields and formats as the app's built-in SRD monsters, so an
    imported monster renders like a built-in one. The stat-block header lines
    travel as printed strings: the record keeps saves/skills as dicts, the app
    stores one text line each.
    """
    ab = m["abilities"]
    return {
        "id": 0,
        "name": m["name"],
        "size": ",".join(m["size"]),
        "type": m["type"],
        "challengeRating": m["cr"],
        "armorClass": str(m["ac"]),
        "hitPoints": m["hp"],
        "speed": m["speed"],
        "strength": ab["str"],
        "dexterity": ab["dex"],
        "constitution": ab["con"],
        "intelligence": ab["int"],
        "wisdom": ab["wis"],
        "charisma": ab["cha"],
        "alignment": m.get("alignment"),
        "saves": _printed_bonuses(m.get("saves"), lambda k: ABILITY_ABBR.get(k, k.capitalize())),
        "skills": _printed_bonuses(m.get("skills"), _skill_label),
        "senses": m.get("senses"),
        "passivePerception": m.get("passive_perception"),
        "languages": m.get("languages"),
        "damageImmunities": m.get("damage_immunities"),
        "damageResistances": m.get("damage_resistances"),
        "damageVulnerabilities": m.get("damage_vulnerabilities"),
        "conditionImmunities": m.get("condition_immunities"),
        "traits": m.get("traits"),
        "actions": m.get("actions"),
        "bonusActions": m.get("bonus_actions"),
        "reactions": m.get("reactions"),
        "legendaryActions": m.get("legendary_actions"),
    }


def bestiary_record(m):
    """One source bestiary entry -> the fields convert_monster() reads."""
    typ = _fmt_type(m.get("type"))
    rec = {"name": m["name"], "source": m["source"], "srd52": bool(m.get("srd52")),
           "size": m.get("size"), "type": typ, "cr": _fmt_cr(m.get("cr")),
           "ac": _fmt_ac(m.get("ac")),
           "hp": (m.get("hp", {}) or {}).get("average") if isinstance(m.get("hp"), dict) else m.get("hp"),
           "speed": _fmt_speed(m.get("speed")), "abilities": _abilities(m)}
    extras = {
        "alignment": _fmt_alignment(m.get("alignment")),
        "saves": m.get("save") or None,
        "skills": _fmt_skills(m.get("skill")),
        "senses": _joined(m.get("senses")),
        "passive_perception": m.get("passive"),
        "languages": _cap(_joined(m.get("languages"))),
        "damage_immunities": _fmt_typed_list(m.get("immune"), "immune"),
        "damage_resistances": _fmt_typed_list(m.get("resist"), "resist"),
        "damage_vulnerabilities": _fmt_typed_list(m.get("vulnerable"), "vulnerable"),
        "condition_immunities": _fmt_typed_list(m.get("conditionImmune"), "conditionImmune"),
    }
    rec.update({k: v for k, v in extras.items() if v is not None})
    for label, blocks in _monster_sections(m).items():
        if blocks:
            rec[label] = "\n\n".join(blocks)
    return rec


def extract_all_monsters():
    """Every non-SRD monster from MONSTER_SOURCES in the source bestiary, one per name."""
    print("Extracting monsters from the source bestiary...")
    by_source = {}
    bestiary_dir = data_path('bestiary')
    for fname in sorted(os.listdir(bestiary_dir)):
        if not fname.startswith('bestiary-') or not fname.endswith('.json'):
            continue
        with open(os.path.join(bestiary_dir, fname), 'r', encoding='utf-8') as f:
            for entry in json.load(f).get('monster', []):
                if entry.get('source') in MONSTER_SOURCES:
                    by_source.setdefault(entry['source'], []).append(bestiary_record(entry))

    by_name = {}
    skipped = []
    for source in MONSTER_SOURCES:
        for m in sorted(by_source.get(source, []), key=lambda r: r.get("name", "")):
            name = m["name"]
            if name in by_name:
                continue  # an earlier (higher-priority) book already has it
            if m.get("srd52"):
                continue  # SRD content; the app seeds it
            if m.get("hp") is None:
                skipped.append((source, name, "no fixed HP (spell-summon block)"))
                continue
            typ = m.get("type")
            if isinstance(typ, dict) and typ.get("choose"):
                # Empyrean is "Celestial or Fiend"; the app's type is one line of text.
                m = dict(m, type=" or ".join(typ["choose"]))
            elif not isinstance(typ, str):
                skipped.append((source, name, "structured type"))
                continue
            if not m.get("cr") or not str(m.get("ac", "")).strip():
                skipped.append((source, name, "blank CR/AC"))
                continue
            bad_size = [s for s in m.get("size", []) if s not in VALID_MONSTER_SIZES]
            if bad_size or not m.get("size"):
                skipped.append((source, name, f"size {m.get('size')!r}"))
                continue
            by_name[name] = convert_monster(m)
    for source, name, why in skipped:
        print(f"  ! skipped {source}/{name}: {why}")
    monsters = [by_name[n] for n in sorted(by_name, key=str.lower)]
    print(f"  {len(monsters)} monsters from {len(MONSTER_SOURCES)} books ({len(skipped)} skipped)")
    return monsters


def load_class_description(class_name, sources=("EFA", "TCE")):
    """First two sentences of a class's source fluff, first match in `sources` order.

    Both books follow those two sentences with a pointer to the chapter, which
    means nothing inside the app, so the blurb stops there.
    """
    try:
        with open(data_path('class', f'fluff-class-{class_name.lower()}.json'), 'r') as f:
            fluff = [entry for entry in json.load(f).get('classFluff', [])
                     if entry.get('name') == class_name and entry.get('entries')]
    except FileNotFoundError:
        return ""  # a class with no fluff file still exports, just without a blurb

    def first_paragraph(entries):
        for entry in entries:
            if isinstance(entry, str):
                return entry
            if isinstance(entry, dict):
                found = first_paragraph(entry.get('entries', []))
                if found:
                    return found
        return None

    for source in sources:
        for entry in fluff:
            if entry.get('source') == source:
                paragraph = first_paragraph(entry['entries'])
                if paragraph:
                    sentences = re.split(r'(?<=[.!?])\s+', entries_to_text([paragraph]))
                    return ' '.join(sentences[:2])
    return ""


# Classes to skip even though they are not in the SRD: Tasha's sidekicks are
# companion stat templates, not player classes an NPC is built from.
def _is_player_class(cls):
    return not cls.get("isSidekick")


def find_non_srd_classes():
    """Every class in the source data the SRD does not print, with the book to take it from.

    A class is skipped when any printing of it is in the SRD (the 2014 or 2024
    one), when none of its printings is from a book we import, or when it is a
    sidekick. The printing kept is the highest in SOURCE_PRECEDENCE, so a class
    reprinted in a newer book comes from that book.
    """
    printings = {}
    for path in sorted(glob.glob(data_path("class", "class-*.json"))):
        with open(path, "r", encoding="utf-8") as f:
            for cls in json.load(f).get("class", []):
                printings.setdefault(cls["name"], []).append((path, cls))

    found = []
    for name, versions in sorted(printings.items()):
        if any(v.get("srd") or v.get("srd52") for _, v in versions):
            continue
        ours = [(path, v) for path, v in versions
                if v.get("source") in SOURCE_PRIORITY and _is_player_class(v)]
        if not ours:
            continue
        ours.sort(key=lambda pv: SOURCE_PRIORITY[pv[1]["source"]])
        found.append((name, tuple(v["source"] for _, v in ours), ours[0][0]))
    return found


ABILITY_NAMES = {
    "str": "Strength", "dex": "Dexterity", "con": "Constitution",
    "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma",
}


def build_class(class_name, sources, class_file):
    """A homebrew class record for `class_name`, from its source class file.

    Takes the first printing in `sources` order. Spell slots come from the
    class table's spell-slot rows, one progression entry per level, so the app
    can show slots on the sheet and count prepared spells against them; the
    spell list comes from sources.json's class lists for the same printing.
    """
    with open(class_file, "r", encoding="utf-8") as f:
        printings = [c for c in json.load(f).get("class", []) if c.get("name") == class_name]
    by_source = {c.get("source"): c for c in printings}
    source = next((s for s in sources if s in by_source), None)
    if source is None:
        raise SystemExit(f"No {class_name} printing from {sources} in the class data")
    cls = by_source[source]

    primary = next(iter(cls.get("primaryAbility") or [{}]), {})
    spell_ability = cls.get("spellcastingAbility")
    slot_rows = next(
        (g["rowsSpellProgression"] for g in cls.get("classTableGroups", []) if "rowsSpellProgression" in g),
        [],
    )
    # Cantrips and prepared spells per level, where the class prints them. The
    # app reads these ahead of its own guess from the slot total (#991); an app
    # older than that ignores the keys, so they are safe to emit either way.
    cantrips = cls.get("cantripProgression") or []
    prepared = cls.get("preparedSpellsProgression") or []

    def level_entry(level, row):
        entry = {
            "level": level,
            "features": [],
            "spellSlots": {str(slot_level): count
                           for slot_level, count in enumerate(row, start=1) if count > 0},
        }
        if level <= len(cantrips):
            entry["cantripsKnown"] = cantrips[level - 1]
        if level <= len(prepared):
            entry["preparedSpells"] = prepared[level - 1]
        return entry

    progression = [level_entry(level, row) for level, row in enumerate(slot_rows, start=1)]

    return {
        "id": 0,
        "name": class_name,
        "description": load_class_description(class_name, sources),
        "hitDie": f"d{cls.get('hd', {}).get('faces', 8)}",
        "primaryAbility": ", ".join(ABILITY_NAMES[a] for a in primary if a in ABILITY_NAMES),
        "savingThrows": [ABILITY_NAMES[a] for a in cls.get("proficiency", []) if a in ABILITY_NAMES],
        "proficiencies": [],
        "equipment": [],
        "spellcasting": bool(cls.get("casterProgression")),
        "spellcastingAbility": ABILITY_NAMES.get(spell_ability) if spell_ability else None,
        "spellList": class_spell_list(class_name, source),
        "progression": progression,
        "features": [],
        # Placed on the features once they are known, then stripped.
        "_additionalSpells": cls.get("additionalSpells"),
    }


def class_spell_list(class_name, source):
    """Spell names on `class_name`'s list as printed in `source`, sorted."""
    with open(data_path("spells", "sources.json"), "r", encoding="utf-8") as f:
        lookup = json.load(f)
    names = set()
    for spells in lookup.values():
        for spell_name, info in spells.items():
            for key in ("class", "classVariant"):
                for entry in info.get(key) or []:
                    if entry.get("name") == class_name and entry.get("source") == source:
                        names.add(spell_name)
    return sorted(names)


def parse_args(argv=None):
    """Command-line arguments, with the data directory checked and resolved."""
    parser = argparse.ArgumentParser(
        description="Extract non-SRD content from a source data directory into "
                    "the app's homebrew import format (homebrew.json).")
    parser.add_argument("data_dir",
                        help="the data folder of the source dataset, or its parent folder")
    args = parser.parse_args(argv)
    data_dir = os.path.abspath(os.path.expanduser(args.data_dir))
    if not os.path.isdir(os.path.join(data_dir, "class")) and \
            os.path.isdir(os.path.join(data_dir, "data", "class")):
        data_dir = os.path.join(data_dir, "data")  # given the checkout root
    missing = [d for d in ("class", "bestiary", "spells") if not os.path.isdir(os.path.join(data_dir, d))]
    if missing:
        parser.error(f"{data_dir} doesn't look like a source data directory "
                     f"(no {', '.join(missing)} folder inside it)")
    args.data_dir = data_dir
    return args


def main(argv=None):
    global DATA
    DATA = parse_args(argv).data_dir
    print("Extracting non-SRD content from supplements...")

    result = {
        "classes": [build_class(name, sources, path) for name, sources, path in find_non_srd_classes()],
        "subclasses": [],
        "species": [],
        "feats": [],
        "spells": [],
        "equipment": [],
        "backgrounds": [],
        "monsters": [],
        "exportedAt": int(time.time() * 1000),
        "version": "1.0"
    }

    # Extract from each supplement
    all_subclasses = extract_phb_subclasses()
    result["subclasses"].extend(all_subclasses)

    result["species"].extend(extract_supplement_species())

    # The subclasses we kept carry their own shortName, so features can be
    # filtered to exactly those printings.
    non_srd_subclass_shortnames = {sc["_shortName"] for sc in result["subclasses"]}

    # Extract all subclass features from class JSON files (filtered to non-SRD only)
    artificer_features, all_subclass_features = extract_all_subclass_features(non_srd_subclass_shortnames)
    result["classes"][0]["features"] = artificer_features

    # Match subclass features to the exact printing each subclass came from,
    # then drop the tracking fields.
    missing_features = []
    for subclass in result["subclasses"]:
        key = (subclass.pop("_shortName"), subclass.pop("_source"))
        subclass["features"] = all_subclass_features.get(key, [])
        if not subclass["features"]:
            missing_features.append(f'{subclass["parentClassName"]} - {subclass["name"]}')

    if missing_features:
        print(f"\nWarning: {len(missing_features)} subclasses have no features: "
              f"{', '.join(missing_features)}")

    # Fixed spell grants go on the features that confer them.
    granting, unplaced = [], []
    for owner in result["classes"] + result["subclasses"]:
        placed, missed = attach_spell_grants(owner["features"], owner.pop("_additionalSpells"))
        if placed:
            granting.append(owner["name"])
        if missed:
            unplaced.append(f'{owner["name"]} ({missed})')
    print(f"\nSpell grants placed on the features of {len(granting)} classes and subclasses")
    if unplaced:
        print(f"Warning: spells with no feature to carry them: {', '.join(unplaced)}")

    # Extract spells
    all_spells = extract_all_spells()
    result["spells"].extend(all_spells)

    # Extract feats
    phb_feats = extract_phb_feats()
    result["feats"].extend(phb_feats)
    print(f"Spell grants on {sum(1 for f in phb_feats if 'grantsSpells' in f)} feats")

    # Extract backgrounds
    phb_backgrounds = extract_phb_backgrounds()
    result["backgrounds"].extend(phb_backgrounds)

    # Extract equipment
    all_equipment = extract_all_equipment()
    result["equipment"].extend(all_equipment)

    # Extract monsters
    result["monsters"].extend(extract_all_monsters())

    # Output JSON
    with open("homebrew.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n=== EXTRACTION SUMMARY ===")
    print(f"✓ Extracted {len(result['classes'])} classes")
    print(f"✓ Extracted {len(result['subclasses'])} subclasses")
    print(f"✓ Extracted {len(result['species'])} species")
    print(f"✓ Extracted {len(result['spells'])} spells")
    print(f"✓ Extracted {len(result['feats'])} feats")
    print(f"✓ Extracted {len(result['backgrounds'])} backgrounds")
    print(f"✓ Extracted {len(result['equipment'])} equipment items")
    print(f"✓ Extracted {len(result['monsters'])} monsters")
    print("✓ Output written to homebrew.json")

if __name__ == "__main__":
    main()
