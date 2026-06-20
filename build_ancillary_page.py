#!/usr/bin/env python3
"""WH3 ancillary data -> self-contained browsable HTML reference.
Equippable ancillaries by faction -> category: rendered stat buffs / abilities
(with ability descriptions), banner effects, set bonuses, rarity-coloured icons,
character-lock notes, internal keys, and hover tooltips.

Run:  python3 build_ancillary_page.py   ->  ancillaries.html
"""
import os, re, html, glob, sys
from urllib.parse import quote
from collections import defaultdict

# paths are relative to this script, so the repo works wherever it's checked out
# (place your RPFM extraction in a "fullExtraction/" folder beside this script)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("WH3_EXTRACT", os.path.join(HERE, "fullExtraction"))
DB   = os.path.join(ROOT, "db")
LOCD = os.path.join(ROOT, "text", "db")
WEB  = "--no-assets" in sys.argv   # asset-free build for public hosting: no CA images, CSS placeholders
OUT  = os.path.join(HERE, "ancillaries_web.html" if WEB else "ancillaries.html")

def read_tsv(name):
    with open(os.path.join(DB, name, "data__.tsv"), encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    header = lines[0].split("\t")
    return [dict(zip(header, l.split("\t"))) for l in lines[2:] if l.strip()]

# ---- merged loc + {{tr:}} resolution --------------------------------------
print("loading loc…")
LOC, TR_TOKEN = {}, {}
for path in glob.glob(os.path.join(LOCD, "*.loc.tsv")):
    with open(path, encoding="utf-8", errors="replace") as f:
        for l in f.read().split("\n"):
            if not l or l.startswith("#"): continue
            p = l.split("\t")
            if len(p) < 2 or p[0] == "key": continue
            LOC[p[0]] = p[1]
            if p[0].startswith("ui_text_replacements_localised_text_"):
                tok = re.split(r"_wh\d?_", p[0][len("ui_text_replacements_localised_text_"):], 1)[0]
                TR_TOKEN.setdefault(tok, p[1])
TR_RE = re.compile(r"\{\{tr:([^}]+)\}\}")
def resolve(text, depth=0):
    if not text: return ""
    if "{{" in text and depth < 6:
        text = TR_RE.sub(lambda m: LOC.get(m.group(1)) or TR_TOKEN.get(m.group(1)) or "", text)
        text = resolve(text, depth + 1)
    text = re.sub(r"\[\[/?img[^\]]*\]\]", "", text)
    text = re.sub(r"\[\[.*?\]\]", "", text)
    return text.strip()

# ---- tables ---------------------------------------------------------------
print("loading tables…")
anc   = read_tsv("ancillaries_tables")
types = {r["type"]: r["ui_icon"] for r in read_tsv("ancillary_types_tables")}

eff_by_anc = defaultdict(list)
for r in read_tsv("ancillary_to_effects_tables"):
    eff_by_anc[r["ancillary"]].append((r["effect"], r.get("value", "0")))

banner_bundle  = {r["banner"]: r["effect_bundle"] for r in read_tsv("banners_tables")}
bundle_effects = defaultdict(list)
for r in read_tsv("effect_bundles_to_effects_junctions_tables"):
    bundle_effects[r["effect_bundle_key"]].append((r["effect_key"], r.get("value", "0")))

eff_to_ability = {r["effect"]: r["unit_ability"] for r in read_tsv("effect_bonus_value_unit_ability_junctions_tables")}
# the junction's bonus_value_id says WHAT the link does: 'enable' = grants the ability;
# 'cost_mod'/'recharge_mod'/'miscast_*'/… = MODIFIES an existing spell the caster already has.
eff_junctions = defaultdict(list)
for r in read_tsv("effect_bonus_value_unit_ability_junctions_tables"):
    eff_junctions[r["effect"]].append((r["bonus_value_id"], r["unit_ability"]))

# the REAL mechanics of a granted ability live in special_ability_phases, not the flavour tooltip
ability_phases = defaultdict(list)            # special_ability -> [phase_key, …]
for r in read_tsv("special_ability_to_special_ability_phase_junctions_tables"):
    ability_phases[r["special_ability"]].append(r["phase"])
phase_row = {r["id"]: r for r in read_tsv("special_ability_phases_tables")}
usab      = {r["key"]: r for r in read_tsv("unit_special_abilities_tables")}

# auto-deactivate flags = the CONDITION an ability runs under (these gate it OFF, so the
# player-facing condition is the inverse: engaged_in_melee deactivate -> "only out of melee")
deact_flags = defaultdict(list)
for r in read_tsv("special_ability_to_auto_deactivate_flags_tables"):
    deact_flags[r["special_ability"]].append(r["deactivate_flag"])

# the stat buffs a phase applies WHILE ACTIVE (e.g. Festering Shroud = +10 missile resist out of melee)
phase_stats = defaultdict(list)
for r in read_tsv("special_ability_phase_stat_effects_tables"):
    phase_stats[r["phase"]].append((r["stat"], r.get("value", "0"), r.get("how", "add")))

anc_subtypes = defaultdict(list)
for r in read_tsv("ancillaries_included_agent_subtypes_tables"):
    anc_subtypes[r["ancillary"]].append(r["agent_subtype"])

anc_sets, set_members, set_effects = defaultdict(list), defaultdict(list), defaultdict(list)
for r in read_tsv("ancillary_set_ancillary_junctions_tables"):
    anc_sets[r["ancillary_key"]].append(r["set_key"]); set_members[r["set_key"]].append(r["ancillary_key"])
for r in read_tsv("ancillary_set_effect_junctions_tables"):
    set_effects[r["set_key"]].append((r["effect_key"], r.get("value", "0")))

NAME = {r["key"]: resolve(LOC.get("ancillaries_onscreen_name_" + r["key"], "")).strip() for r in anc}

# ---- rendering helpers ----------------------------------------------------
def fmt_num(v):
    try: f = float(v)
    except ValueError: return v
    return str(int(round(f))) if abs(f - round(f)) < 1e-9 else f"{f:g}"

def stat_line(effect, value):
    tmpl = LOC.get("effects_description_" + effect)
    if not tmpl: return None
    n = fmt_num(value); signed = ("+" + n) if not n.startswith("-") else n
    return resolve((tmpl.replace("%+n%", signed + "%").replace("%+n", signed)
                        .replace("%n%", n + "%").replace("%n", n))) or None

def _f(v):
    try: return float(v)
    except (ValueError, TypeError): return 0.0

def _contact_name(key):
    # imbue_contact holds a special_ability_phases key (e.g. ..._unit_contact_discouraged = "Discouraged!")
    nm = resolve(LOC.get("special_ability_phases_onscreen_name_" + key, "")).strip()
    nm = re.split(r"[\\\n]", nm)[0].strip().rstrip("!").strip()   # name only; cut at first backslash/newline, drop "!"
    return nm or re.sub(r"^wh.*?_unit_contact_", "", key).replace("_", " ").title()

# special_ability_phases columns -> human label (the effect-bearing ones only)
PHASE_LABELS = [
    ("mana_regen_mod",            lambda v: f"Winds of Magic recharge rate ×{fmt_num(v)}"),
    ("mana_max_depletion_mod",    lambda v: f"Winds of Magic reserve — depletion ×{fmt_num(v)} (larger pool)"),
    ("ability_recharge_change",   lambda v: f"Ability recharge {'+' if _f(v) > 0 else ''}{fmt_num(v)}"),
    ("inspiration_aura_range_mod",lambda v: f"Aura range ×{fmt_num(v)}"),
    ("fatigue_change_ratio",      lambda v: f"Fatigue gain ×{fmt_num(v)}"),
    ("freeze_fatigue",            lambda v: "Immune to fatigue"),
    ("freeze_recharge",           lambda v: "Freezes ability recharge"),
    ("heal_amount",               lambda v: f"Regenerates {fmt_num(_f(v)*100)}% max HP" if 0 < _f(v) < 1 else f"Heals {fmt_num(v)} HP"),
    ("barrier_heal_amount",       lambda v: f"Restores {fmt_num(v)} barrier"),
    ("hp_change_frequency",       lambda v: f"HP tick every {fmt_num(v)}s"),
    ("damage_amount",             lambda v: f"Deals {fmt_num(v)} damage"),
    ("max_damaged_entities",      lambda v: f"affects up to {fmt_num(v)} entities"),
    ("execute_ratio",             lambda v: f"Executes below {fmt_num(v)} HP"),
    ("resurrect",                 lambda v: "Resurrects slain models"),
    ("replenish_ammo",            lambda v: "Replenishes ammunition"),
    ("imbue_magical",             lambda v: "Imbues attacks: magical"),
    ("imbue_ignition",            lambda v: "Imbues attacks: flaming"),
    ("imbue_contact",             lambda v: f"Imbues attacks: {_contact_name(v)}"),
    ("remove_magical",            lambda v: "Removes magical attacks"),
    ("cant_move",                 lambda v: "Roots target (cannot move)"),
    ("spreading",                 lambda v: "Spreads to nearby units"),
]
_PHASE_SKIP = {"", "0", "0.0", "0.0000", "0.000", "false", "none"}

# deactivate_flag -> player-facing condition (phrased as the ACTIVE condition, i.e. inverted)
_DEACT = {
    "engaged_in_melee":                          "Active only when out of melee",
    "out_of_melee":                              "Active only while in melee",
    "out_of_melee_anything":                     "Active only while in melee",
    "moving":                                    "Active only while stationary",
    "not_moving":                                "Active only while moving",
    "unit_is_not_charging":                      "Active only while charging",
    "winning_melee_combat":                      "Inactive while winning the melee",
    "losing_melee_combat":                       "Inactive while losing the melee",
    "morale_is_broken_or_lower":                 "Inactive when morale is broken",
    "morale_is_lower_than_half_of_base_morale":  "Inactive when morale drops below half",
    "morale_is_wavering_or_lower":               "Inactive when morale wavers",
    "is_not_under_missile_fire":                 "Active only while under missile fire",
    "is_not_on_fire":                            "Active only while on fire",
    "is_not_rampaging":                          "Active only while rampaging",
    "flying_currently":                          "Inactive while flying",
    "grounded":                                  "Inactive while grounded",
    "climbing":                                  "Inactive while climbing",
    "manning_equipment":                         "Inactive while manning equipment",
}
def _deactivate_text(flag):
    if flag in _DEACT: return _DEACT[flag]
    m = re.match(r"health_(above|below)_(\d+)%", flag)
    if m:
        return f"Active only {'below' if m.group(1) == 'above' else 'above'} {m.group(2)}% HP"
    m = re.match(r"mana_below_value_(\d+)", flag)
    if m: return f"Active only when Winds of Magic ≥ {m.group(1)}"
    return f"Deactivates while: {flag.replace('_', ' ')}"   # honest raw fallback for niche flags

# stat keys -> readable names (phase stat effects); prettify fallback for the rest
STAT_LABELS = {
    "stat_resistance_missile": "Missile resistance", "stat_resistance_physical": "Physical resistance",
    "stat_resistance_magic": "Magic resistance", "stat_magical_resistance": "Ward save",
    "stat_armour": "Armour", "stat_melee_attack": "Melee attack", "stat_melee_defence": "Melee defence",
    "stat_melee_damage_base": "Melee damage (base)", "stat_melee_damage_ap": "Melee damage (AP)",
    "stat_missile_damage_base": "Missile damage (base)", "stat_morale": "Leadership", "stat_speed": "Speed",
    "stat_charge_bonus": "Charge bonus", "stat_bonus_vs_large": "Bonus vs large",
    "stat_bonus_vs_infantry": "Bonus vs infantry", "stat_ammo": "Ammunition", "stat_health": "Health",
    "stat_reload_time": "Reload time", "stat_fatigue": "Fatigue",
}
def _fmt_stat_effect(stat, value, how):
    name = STAT_LABELS.get(stat) or re.sub(r"^(stat_|scalar_)", "", stat).replace("_", " ").capitalize()
    if how == "mult":
        return f"{name} ×{fmt_num(value)}"
    v = _f(value)
    pct = "%" if ("resistance" in stat or "ward" in stat) else ""
    return f"{name} {'+' if v >= 0 else ''}{fmt_num(value)}{pct}"

def _unit_name(key):
    for pre in ("land_units_onscreen_name_", "land_units_name_", "units_custom_battle_name_"):
        nm = resolve(LOC.get(pre + key, ""))
        if nm: return nm
    s = re.sub(r"^wh\d?_[a-z0-9]+_", "", key)         # drop wh2_dlc15_
    s = re.sub(r"^[a-z]{3}_[a-z]{2,4}_", "", s)        # drop grn_mon_
    s = re.sub(r"_summoned.*$|_\d+$", "", s)           # drop _summoned_0
    return s.replace("_", " ").title()

def _ability_kind(a):
    """Classify the ability: summon / vortex / bombardment / magic missile (None for plain augments)."""
    if not a: return None
    if a.get("spawned_unit"):        return "Summon: " + _unit_name(a["spawned_unit"])
    if a.get("vortex"):              return "Vortex spell"
    if a.get("bombardment") == "true": return "Bombardment"
    if a.get("activated_projectile"): return "Magic missile"
    aoe = a.get("targetting_aoe", "")
    if "vortex" in aoe:  return "Vortex spell"
    if "missile" in aoe: return "Magic missile"
    if "spawn" in aoe:   return "Summon"
    return None

def ability_mechanics(ab):
    """Real mechanical effects of a granted ability: kind + timing + targeting + phase numbers + stat buffs."""
    lines = []
    a = usab.get(ab)
    if a:
        at, rt, nu = _f(a.get("active_time")), _f(a.get("recharge_time")), _f(a.get("num_uses"))
        if rt > 0:
            parts = ([f"{fmt_num(at)}s duration"] if at > 0 else []) + [f"{fmt_num(rt)}s recharge"]
            if nu > 0: parts.append(f"{fmt_num(nu)} use(s)")
            lines.append("Active — " + ", ".join(parts))
        elif _f(a.get("effect_range")) > 0:
            lines.append("Passive aura")
        elif at > 0:
            lines.append(f"Lasts {fmt_num(at)}s")
    kind = _ability_kind(a)
    if kind: lines.append(kind)
    # targeting profile — who the ability's effects actually land on
    self_t  = bool(a) and any(a.get(c) == "true" for c in ("affect_self", "always_affect_self", "target_self"))
    allies  = bool(a) and (_f(a.get("num_effected_friendly_units")) != 0 or a.get("target_friends") == "true")
    enemies = bool(a) and (_f(a.get("num_effected_enemy_units")) != 0 or a.get("target_enemies") == "true")
    self_only = self_t and not allies and not enemies
    tgt = (["enemies"] if enemies else []) + (["allies"] if allies else [])
    if self_t: tgt.append("self (caster)" if self_only else "self")
    if tgt: lines.append("Targets: " + ", ".join(tgt))
    for flag in deact_flags.get(ab, []):
        txt = _deactivate_text(flag)
        if txt and txt not in lines: lines.append(txt)
    seen = set()
    for ph_key in (ability_phases.get(ab) or [ab]):
        ph = phase_row.get(ph_key)
        if ph:
            for col, fmt in PHASE_LABELS:
                v = ph.get(col, "")
                if v in _PHASE_SKIP: continue
                txt = fmt(v)
                if txt not in seen: seen.add(txt); lines.append(txt)
        for stat, value, how in phase_stats.get(ph_key, []):
            txt = _fmt_stat_effect(stat, value, how)
            if txt and txt not in seen: seen.add(txt); lines.append(txt)
    if self_only:   # every effect lands on the caster: clarify damage, drop redundant entity count
        fixed = []
        for ln in lines:
            if ln.startswith("affects up to"): continue
            if ln.startswith("Deals ") and ln.endswith(" damage"): ln += " to self"
            fixed.append(ln)
        lines = fixed
    return lines

def fmt_signed(value):
    n = fmt_num(value)
    return n if n.startswith("-") else "+" + n

# bonus_value_id (non-enable) -> how it modifies an EXISTING spell/ability
SPELL_MOD = {
    "cost_mod":                     lambda v: f"{fmt_signed(v)} Winds of Magic cost",
    "cost_percentage_mod":          lambda v: f"{fmt_signed(v)}% Winds of Magic cost",
    "recharge_mod":                 lambda v: f"{fmt_signed(v)}s cooldown",
    "shared_cooldown_mod":          lambda v: f"{fmt_signed(v)}s shared cooldown",
    "miscast_percentage_mod":       lambda v: f"{fmt_signed(v)}% miscast chance",
    "uses_mod":                     lambda v: f"{fmt_signed(v)} use(s)",
    "effect_range_mod":             lambda v: f"{fmt_signed(v)} effect range",
    "active_time_mod":              lambda v: f"{fmt_signed(v)}s duration",
    "target_intercept_range_mod":   lambda v: f"{fmt_signed(v)} intercept range",
    "spell_mastery_percentage_mod": lambda v: f"{fmt_signed(v)}% spell mastery",
    "enable_overchage":             lambda v: "overcast enabled",
    "disable":                      lambda v: "disabled",
    "disable_overchage":            lambda v: "overcast disabled",
}
def _spell_name(ab):
    return resolve(LOC.get("unit_abilities_onscreen_name_" + ab, "")) or \
           re.sub(r".*?_spell_|.*?_abilities_", "", ab).replace("_", " ").title()

def render_effects(pairs):
    """pairs -> list of ('stat', text) / ('ability', name, desc, mechanics)."""
    out, seen = [], set()
    def emit(t):
        if not t: return
        key = t[:2] if t[0] == "ability" else t   # list member unhashable; dedup on (kind, name)
        if key not in seen: seen.add(key); out.append(t)
    for effect, value in pairs:
        js = eff_junctions.get(effect)
        if js:
            grant = next((ab for bvid, ab in js if bvid == "enable"), None)
            if grant:                                    # the item GRANTS this ability
                nm = resolve(LOC.get("unit_abilities_onscreen_name_" + grant, "")) or \
                     (effect.split("enable_")[-1].replace("_", " ").title())
                desc = resolve(LOC.get("unit_abilities_tooltip_text_" + grant, ""))
                emit(("ability", nm, desc, ability_mechanics(grant)))
            else:                                        # the item MODIFIES existing spell(s)
                by_type = defaultdict(list)
                for bvid, ab in js:
                    if bvid in SPELL_MOD: by_type[bvid].append(ab)
                for bvid, abl in by_type.items():
                    mod = SPELL_MOD[bvid](value)
                    if len(abl) > 5:                     # blanket modifier (Warp-Gem hits 187 spells) -> collapse
                        emit(("stat", f"All spells: {mod}"))
                    else:
                        for ab in abl:
                            emit(("stat", f"{_spell_name(ab)}: {mod}"))
            continue
        s = stat_line(effect, value)
        if s:
            emit(("stat", s))
        else:
            m = re.search(r"_ability_enable_(.+)$", effect)
            if m: emit(("ability", m.group(1).replace("_", " ").title(), "", []))
    return out

# rarity
RC = {"common":"#b9bec6","uncommon":"#4caf50","rare":"#4083e6","legendary":"#b659e0","crafted":"#21c0cf"}
RL = {"common":"Common","uncommon":"Uncommon","rare":"Rare","legendary":"Unique","crafted":"Crafted"}
RANK = {"legendary":0,"crafted":1,"rare":2,"uncommon":3,"common":4,None:5}
def rarity(score):
    try: s = int(round(float(score)))
    except (ValueError, TypeError): return (None, "#5a6070", "")
    t = ("crafted" if s in (199,151,-999,-998) else "legendary" if s>=200 else
         "rare" if s>=130 else "uncommon" if s>=80 else "common" if s>=35 else None)
    return (t, RC.get(t, "#5a6070"), RL.get(t, ""))

def icon_src(typ):
    if WEB: return ""                  # asset-free build: no CA image paths at all
    p = types.get(typ); return ("fullExtraction/" + quote(p, safe="/")) if p else ""

# character-lock
ROLES = {"lord","lords","hero","heroes","general","captain","champion","wizard","engineer","priest",
         "prophet","mage","dignitary","spy","runesmith","paladin","damsel","necromancer","caster"}
RACE_CODE = {"grn":"Greenskins","emp":"The Empire","dwf":"Dwarfs","hef":"High Elves","def":"Dark Elves",
    "lzd":"Lizardmen","skv":"Skaven","vmp":"Vampire Counts","cst":"Vampire Coast","tmb":"Tomb Kings",
    "brt":"Bretonnia","wef":"Wood Elves","nor":"Norsca","bst":"Beastmen","chs":"Warriors of Chaos",
    "cth":"Grand Cathay","ksl":"Kislev","ogr":"Ogre Kingdoms","chd":"Chaos Dwarfs","kho":"Khorne",
    "nur":"Nurgle","sla":"Slaanesh","tze":"Tzeentch","dae":"Daemons of Chaos"}
def subtype_info(st):
    s = re.sub(r"^wh\d?_[a-z0-9]+_", "", st)              # drop wh?_<set>_
    m = re.match(r"^([a-z]{2,4})_", s)
    race = m.group(1) if m else ""
    name = re.sub(r"^[a-z]{2,4}_", "", s).replace("_", " ").title()
    return name, race, s
def char_lock(key):
    """-> (character names, races) for items locked to <=4 named characters."""
    sts = anc_subtypes.get(key, [])
    if not sts or len(sts) > 4: return [], []            # general / broad class
    names, races = [], []
    for st in sts:
        name, race, raw = subtype_info(st)
        if raw.split("_")[-1] in ROLES: continue         # generic class subtype, not a character
        if name and name not in names: names.append(name)
        fac = RACE_CODE.get(race)
        if fac and fac not in races: races.append(fac)
    return names, races

# faction / category
RACE_TOKENS = [("vampire_counts","Vampire Counts"),("vampire_coast","Vampire Coast"),("chaos_dwarfs","Chaos Dwarfs"),
    ("ogre_kingdoms","Ogre Kingdoms"),("dark_elves","Dark Elves"),("high_elves","High Elves"),("wood_elves","Wood Elves"),
    ("tomb_kings","Tomb Kings"),("greenskins","Greenskins"),("lizardmen","Lizardmen"),("slaanesh","Slaanesh"),
    ("tzeentch","Tzeentch"),("beastmen","Beastmen"),("bretonnia","Bretonnia"),("daemons","Daemons of Chaos"),
    ("khorne","Khorne"),("nurgle","Nurgle"),("kislev","Kislev"),("skaven","Skaven"),("norsca","Norsca"),
    ("cathay","Grand Cathay"),("empire","The Empire"),("dwarfs","Dwarfs"),("greenskin","Greenskins"),("chaos","Warriors of Chaos")]
GENERAL, SHARED = "General (All Factions)", "Shared / Other"
def parse_factions(fs):
    if fs in ("all",""): return [GENERAL]
    if "except" in fs:   return [SHARED]
    rem, found = fs, []
    for tok, disp in RACE_TOKENS:
        if tok in rem and disp not in found: found.append(disp); rem = rem.replace(tok," ")
    return found or [SHARED]
EQUIP = {"weapon":"Weapons","armour":"Armour","talisman":"Talismans","enchanted_item":"Enchanted Items","arcane_item":"Arcane Items"}
def display_group(cat, sub):
    sub = sub or ""
    if sub == "follower": return "Followers"
    if sub in ("banner","banner_rune"): return "Banners"
    if "rune" in sub: return "Runes"
    return EQUIP.get(cat)
CAT_ORDER = ["Weapons","Armour","Talismans","Enchanted Items","Arcane Items","Runes","Followers","Banners"]

# ---------------------------------------------------------------------------
print("building model…")
data, counts, n_items = defaultdict(lambda: defaultdict(list)), defaultdict(int), 0
for r in anc:
    key = r["key"]; name = NAME.get(key, "")
    if not name: continue
    group = display_group(r.get("category",""), r.get("subcategory",""))
    if not group: continue
    pairs = list(eff_by_anc.get(key, []))
    pb = r.get("provided_banner", "")                       # banner effects
    if pb and pb in banner_bundle:
        pairs += bundle_effects.get(banner_bundle[pb], [])
    effects = render_effects(pairs)
    sets = []
    for sk in anc_sets.get(key, []):
        sets.append({
            "name": resolve(LOC.get("ancillary_sets_name_" + sk, "")) or sk,
            "effects": render_effects(set_effects.get(sk, [])),
            "members": [NAME.get(m, m) for m in set_members.get(sk, []) if m != key and NAME.get(m)],
        })
    tier, color, rlabel = rarity(r.get("uniqueness_score",""))
    lock_names, lock_races = char_lock(key)
    item = {"name":name,"key":key,"effects":effects,"sets":sets,"lock":lock_names,
            "flavor":resolve(LOC.get("ancillaries_colour_text_"+key,"")),
            "tier":tier,"color":color,"rlabel":rlabel,"rank":RANK[tier],
            "icon":icon_src(r.get("type","")),"legendary":r.get("legendary_item","false")=="true"}
    facs = parse_factions(r.get("faction_set","all"))
    if facs == [GENERAL] and lock_races:                 # quest item left "all" but locked to a character: file under their faction
        facs = lock_races
    for fac in facs:
        data[fac][group].append(item); counts[fac] += 1
    n_items += 1
print(f"{n_items} equippable ancillaries across {len(data)} factions")

# ---------------------------------------------------------------------------
def esc(s): return html.escape(s or "")
def eff_html(effs):
    out = []
    for e in effs:
        if e[0] == "stat":
            out.append(f'<li>{esc(e[1])}</li>')
        else:
            mech = e[3] if len(e) > 3 else []
            mech_html = ('<ul class="abmech">' + "".join(f'<li>{esc(m)}</li>' for m in mech) + '</ul>') if mech else ""
            desc = f'<div class="abdesc">{esc(e[2])}</div>' if e[2] else ""
            out.append(f'<li class="ab"><span class="abname">✦ {esc(e[1])}</span>{mech_html}{desc}</li>')
    return "".join(out) or '<li class="none">no stat effects</li>'

def render_item(it):
    lock = (f'<div class="lock" title="Can only be equipped by these characters">🔒 Only: '
            f'{esc(", ".join(it["lock"]))}</div>') if it["lock"] else ""
    setb = ""
    for s in it["sets"]:
        mem = f'<div class="setmem">Set with: {esc(", ".join(s["members"]))}</div>' if s["members"] else ""
        setb += (f'<div class="setblk"><div class="setname">⊟ Set bonus — {esc(s["name"])}</div>'
                 f'<ul class="eff">{eff_html(s["effects"])}</ul>{mem}</div>')
    leg = '<span class="badge leg">★</span>' if it["legendary"] else ""
    img = (f'<img class="ico" loading="lazy" src="{esc(it["icon"])}" onerror="this.classList.add(\'broken\')">'
           if it["icon"] else '<span class="ico ph">◆</span>')
    rar = f'<span class="rar" style="color:{it["color"]}">{esc(it["rlabel"])}</span>' if it["rlabel"] else ""
    tip = f'<div class="tip">{esc(it["flavor"])}</div>' if it["flavor"] else ""
    return (f'<div class="item" data-name="{esc(it["name"]).lower()}" data-rar="{it["tier"] or "none"}" style="--rar:{it["color"]}">'
            f'<div class="ihead">{img}<span class="iname">{esc(it["name"])}{leg}</span>{rar}</div>'
            f'{lock}<ul class="eff">{eff_html(it["effects"])}</ul>{setb}'
            f'<div class="ikey" title="internal key (for RPFM)">{esc(it["key"])}</div>{tip}</div>')

print("writing HTML…")
factions = sorted(data.keys(), key=lambda f: (0 if f==GENERAL else 2 if f==SHARED else 1, f))
nav = "".join(f'<button class="fbtn" data-f="{esc(f)}">{esc(f)} <span class="cnt">{counts[f]}</span></button>' for f in factions)
sections = []
for f in factions:
    blocks = []
    for g in CAT_ORDER:
        items = data[f].get(g)
        if not items: continue
        items.sort(key=lambda x: (x["rank"], x["name"]))
        blocks.append(f'<h3 class="cat">{esc(g)} <span class="cnt">{len(items)}</span></h3>'
                      f'<div class="grid">{"".join(render_item(it) for it in items)}</div>')
    sections.append(f'<section class="faction" data-f="{esc(f)}"><h2>{esc(f)}</h2>{"".join(blocks)}</section>')
legend = "".join(f'<span class="lg" style="--c:{RC[t]}">{RL[t]}</span>' for t in ["common","uncommon","rare","legendary","crafted"])

HTML = f"""<!doctype html><html><head><meta charset="utf-8"><title>WH3 Ancillaries</title>
<style>
:root{{--bg:#15171c;--panel:#1d212a;--edge:#2c323e;--txt:#d7dbe2;--mut:#8a93a3;--acc:#6fb3ff;--gold:#d8b863}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);font:13.5px/1.45 system-ui,Segoe UI,Roboto,sans-serif}}
header{{position:sticky;top:0;background:#111317f2;backdrop-filter:blur(6px);border-bottom:1px solid var(--edge);padding:9px 16px;z-index:10}}
header h1{{margin:0 0 7px;font-size:17px}} #search{{width:100%;max-width:420px;padding:7px 10px;background:var(--panel);border:1px solid var(--edge);border-radius:6px;color:var(--txt)}}
.legend{{display:inline-flex;gap:10px;margin-left:14px;font-size:11px}} .lg::before{{content:"";display:inline-block;width:9px;height:9px;border-radius:2px;background:var(--c);margin-right:4px}}
#nav{{margin-top:7px;display:flex;flex-wrap:wrap;gap:5px}}
.fbtn{{background:var(--panel);border:1px solid var(--edge);color:var(--mut);border-radius:14px;padding:3px 10px;cursor:pointer;font-size:12px}}
.fbtn:hover,.fbtn.active{{color:var(--txt);border-color:var(--acc)}} .cnt{{color:var(--mut);font-size:11px}}
main{{padding:12px 16px;max-width:1500px;margin:0 auto}}
.faction>h2{{font-size:20px;border-bottom:2px solid var(--gold);padding-bottom:4px;margin:24px 0 8px}}
.cat{{font-size:13px;color:var(--gold);text-transform:uppercase;letter-spacing:.5px;margin:14px 0 6px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:8px}}
.item{{position:relative;background:var(--panel);border:1px solid var(--edge);border-left:4px solid var(--rar);border-radius:7px;padding:7px 9px}}
.item:hover{{border-color:var(--acc);border-left-color:var(--rar)}}
.ihead{{display:flex;align-items:center;gap:8px;margin-bottom:4px}}
.ico{{width:34px;height:34px;flex:0 0 34px;object-fit:contain;border:1px solid var(--rar);border-radius:4px;background:#0e1014}} .ico.broken{{visibility:hidden}}
.ico.ph{{display:inline-flex;align-items:center;justify-content:center;color:var(--rar);font-size:15px;opacity:.75}}
.iname{{font-weight:600;flex:1}} .rar{{font-size:10px;text-transform:uppercase;letter-spacing:.5px}} .badge.leg{{color:var(--gold);margin-left:5px}}
.lock{{font-size:11.5px;color:#e0894f;margin:0 0 4px}}
.eff{{margin:0;padding-left:16px;color:#b6e3b0}} .eff li{{margin:1px 0}} .eff .none{{color:var(--mut);list-style:none;margin-left:-16px}}
.eff .ab{{list-style:none;margin-left:-16px;color:#cdb3ee}} .abname{{font-weight:600}}
.abdesc{{color:var(--mut);font-style:italic;font-size:12px;margin:1px 0 3px 10px;border-left:2px solid #3a3050;padding-left:7px}}
.abmech{{margin:2px 0 2px 10px;padding-left:13px;color:#9fd0ff;font-size:12px;list-style:none}} .abmech li{{margin:1px 0;position:relative}} .abmech li::before{{content:"▸";position:absolute;left:-12px;color:#5a7fb0}}
.setblk{{margin-top:6px;padding:5px 8px;background:#191d26;border:1px dashed #4a5a3a;border-radius:5px}}
.setname{{color:#cfe08a;font-weight:600;font-size:12px}} .setblk .eff{{color:#cfe08a}} .setmem{{color:var(--mut);font-size:11.5px;margin-top:3px}}
.ikey{{margin-top:5px;font:11px/1.3 ui-monospace,Consolas,monospace;color:#6b7280;user-select:all;word-break:break-all}}
.tip{{display:none;position:absolute;left:0;top:100%;z-index:20;width:min(360px,90vw);margin-top:3px;background:#0e1014;border:1px solid var(--gold);border-radius:7px;padding:9px 11px;color:#c9b98f;font-style:italic;box-shadow:0 6px 20px #000a}}
.item:hover .tip{{display:block}} .hidden{{display:none!important}}
</style></head><body>
<header><h1>WH3 — Equippable Ancillaries <span class="cnt">({n_items} items)</span><span class="legend">{legend}</span></h1>
<input id="search" placeholder="Search name / effect / ability / key…  (Esc clears)">
<div id="nav"><button class="fbtn active" data-f="*">All <span class="cnt">{len(factions)} factions</span></button>{nav}</div></header>
<main>{"".join(sections)}</main>
<script>
const q=document.getElementById('search'),items=[...document.querySelectorAll('.item')],facs=[...document.querySelectorAll('.faction')],btns=[...document.querySelectorAll('.fbtn')];
let curF='*';
function apply(){{const t=q.value.trim().toLowerCase();
 facs.forEach(s=>s.classList.toggle('hidden',!(curF==='*'||s.dataset.f===curF)));
 items.forEach(it=>it.classList.toggle('hidden',!(!t||it.dataset.name.includes(t)||it.textContent.toLowerCase().includes(t))));
 document.querySelectorAll('.faction:not(.hidden)').forEach(s=>{{
   s.querySelectorAll('.cat').forEach(h=>{{const g=h.nextElementSibling,any=[...g.children].some(c=>!c.classList.contains('hidden'));h.classList.toggle('hidden',!any);g.classList.toggle('hidden',!any);}});
   if(![...s.querySelectorAll('.grid')].some(g=>!g.classList.contains('hidden'))) s.classList.add('hidden');}});}}
q.addEventListener('input',apply);q.addEventListener('keydown',e=>{{if(e.key==='Escape'){{q.value='';apply();}}}});
btns.forEach(b=>b.addEventListener('click',()=>{{curF=b.dataset.f;btns.forEach(x=>x.classList.toggle('active',x===b));apply();}}));
</script></body></html>"""
with open(OUT, "w", encoding="utf-8") as f: f.write(HTML)
print("wrote", OUT)
