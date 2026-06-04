# core/excel_parser.py
from __future__ import annotations

import re
from collections import defaultdict, OrderedDict

import pandas as pd

from core.data_models import F0Group, F1Section, F1Leaf

# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════


def parse(excel_path: str) -> tuple[list[F0Group], dict[str, str]]:
    """
    Read Excel file and return list of F0Group objects,
    each containing generalised F1 sections and leaves.

    Returns:
        groups: list of F0Group
        col_labels: {'f0': 'F0 ANNN, 'f1': 'F1 AAANN'}
    """
    df = _load(excel_path)
    f0_col, f1_col, desc_col = _detect_columns(df)
    raw_groups = _group_f0(df, f0_col, f1_col, desc_col)
    groups = [_build_f0_group(df, rec, f0_col, f1_col, desc_col) for rec in raw_groups]
    col_labels = {"f0": f0_col, "f1": f1_col}
    return groups, col_labels


# ═════════════════════════════════════════════════════════════════════════════
# Loading & column detection
# ═════════════════════════════════════════════════════════════════════════════


def _load(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    return df.fillna("").apply(
        lambda col: col.str.strip() if col.dtype == "object" else col
    )


def _detect_columns(df: pd.DataFrame) -> tuple[str, str, str]:
    def find(candidates: list[str]) -> str:
        for cand in candidates:
            for col in df.columns:
                if cand.lower() in col.lower():
                    return col
        raise ValueError(
            f"Cannot find column matching {candidates}. "
            f"Available: {list(df.columns)}"
        )

    return (
        find(["F0 ANNN", "F0"]),
        find(["F1 AAANN", "F1"]),
        find(["RDS-PP Code Description", "Description"]),
    )


# ═════════════════════════════════════════════════════════════════════════════
# F0 grouping
# ═════════════════════════════════════════════════════════════════════════════


def _f0_group_key(code: str) -> str:
    """G001 → 'G00',  W101 → 'W10',  B00n → 'B00n'."""
    m = re.match(r"^([A-Za-z]+)(\d+)$", code)
    if not m:
        return code
    return m.group(1) + m.group(2)[:-1]


def _generalise_f0_code(instances: list[str]) -> str:
    """['G001'..'G028'] → '=G00n',  ['K001'] → '=K001'."""
    if len(instances) == 1:
        code = instances[0]
        return code if code.startswith("=") else f"={code}"

    common = []
    for chars in zip(*instances):
        if len(set(chars)) == 1:
            common.append(chars[0])
        else:
            break
    prefix = "".join(common)

    m = re.match(r"^([A-Za-z]+)(\d+)$", instances[0])
    if m:
        letters = m.group(1)
        digit_len = len(m.group(2))
        digit_prefix = prefix[len(letters) :]
        padded = (digit_prefix + "0" * digit_len)[: digit_len - 1]
        return "=" + letters + padded + "n"

    return "=" + prefix + "n"


def _generalise_single_desc(desc: str) -> str:
    """
    Strip trailing instance numbers for use as a grouping key.
    Used to compare whether two descriptions belong to the same group.
    '  Busbar System 1, 33 kV'  → 'Busbar System n, 33 kV'
    '  Busbar System 2, 33 kV'  → 'Busbar System n, 33 kV'  ← same key
    '  Shunt Reactor System 1'  → 'Shunt Reactor System n'   ← different key
    Note: replaces ALL standalone numbers with n here — used only as key,
    not as display text.
    """
    tokens = re.split(r"(\d+)", desc)
    return "".join("n" if i % 2 == 1 else t for i, t in enumerate(tokens))


def _generalise_desc_from_list(descs: list[str]) -> str:
    """
    Produce a display description by comparing all descriptions in a group.
    Only numbers that DIFFER across descriptions are replaced with 'n'.
    Numbers that are the same in all descriptions are kept as-is.

    Example:
      ["Busbar System 1, 33 kV, Substation 1",
       "Busbar System 2, 33 kV, Substation 1",
       "Busbar System 3, 33 kV, Substation 1"]
      → "Busbar System n, 33 kV, Substation 1"
         (33 and 1 at end stay — only 1/2/3 after 'System' differs)
    """
    if not descs:
        return ""
    if len(descs) == 1:
        return descs[0]

    def tokenise(s: str) -> list[str]:
        return re.split(r"(\d+)", s)

    tokenised = [tokenise(d) for d in descs]

    # If structure differs — fall back to first description
    if len(set(len(t) for t in tokenised)) > 1:
        return descs[0]

    result = []
    for i, token in enumerate(tokenised[0]):
        all_values = [t[i] for t in tokenised]
        if i % 2 == 1:
            # Number token — replace with 'n' only if values differ
            result.append("n" if len(set(all_values)) > 1 else token)
        else:
            # Text token — always keep
            result.append(token)

    return "".join(result)


def _generalise_code_from_list(codes: list[str]) -> str:
    """
    Generalise code by comparing all codes character by character.
    Positions that differ → 'n', positions that are same → keep.

    Examples:
      ["AHA10", "AHA20", "AHA30"] → "=AHAn0"
      ["AHA11", "AHA12", "AHA19"] → "=AHA1n"
      ["AHA10"]                   → "=AHA10"
    """
    if not codes:
        return ""
    if len(codes) == 1:
        return "=" + codes[0]

    # All codes must be same length
    if len(set(len(c) for c in codes)) > 1:
        common = []
        for chars in zip(*codes):
            if len(set(chars)) == 1:
                common.append(chars[0])
            else:
                break
        return "=" + "".join(common) + "n"

    result = []
    for chars in zip(*codes):
        result.append(chars[0] if len(set(chars)) == 1 else "n")

    return "=" + "".join(result)


def _group_f0(
    df: pd.DataFrame,
    f0_col: str,
    f1_col: str,
    desc_col: str,
) -> list[dict]:
    """
    Group F0 codes into generalised series.
    Returns list of dicts: code, description, instances, count.
    """
    # Collect descriptions from rows where F1 is empty
    f0_desc: dict[str, str] = {}
    for _, row in df.iterrows():
        f0 = row[f0_col]
        f1 = row[f1_col]
        desc = row[desc_col]
        if f0 and not f1 and desc and f0 not in f0_desc:
            f0_desc[f0] = desc

    # Group by key (letters + all-but-last digit)
    raw: dict[str, list[str]] = defaultdict(list)
    for f0 in df[f0_col].dropna().unique():
        f0 = f0.strip()
        if f0:
            raw[_f0_group_key(f0)].append(f0)

    # Build records
    records = []
    for key, instances in raw.items():
        instances_sorted = sorted(instances)
        gen_code = _generalise_f0_code(instances_sorted)
        raw_desc = f0_desc.get(instances_sorted[0], "")
        gen_desc = (
            _generalise_desc_from_list([f0_desc.get(i, "") for i in instances_sorted])
            if len(instances) > 1
            else raw_desc
        )
        records.append(
            {
                "code": gen_code,
                "description": gen_desc,
                "instances": instances_sorted,
                "count": len(instances),
            }
        )

    # Post-merge: same letter prefix + same description → one group
    merged: OrderedDict[str, dict] = OrderedDict()
    for rec in records:
        m = re.match(r"^=?([A-Za-z]+)", rec["code"])
        letter = m.group(1) if m else rec["code"]
        mkey = letter + "|" + rec["description"]
        if mkey in merged:
            merged[mkey]["instances"].extend(rec["instances"])
            merged[mkey]["count"] += rec["count"]
        else:
            merged[mkey] = dict(rec)

    # Re-generalise merged codes
    result = []
    for rec in merged.values():
        rec["instances"] = sorted(rec["instances"])
        if rec["count"] > 1:
            rec["code"] = _generalise_f0_code(rec["instances"])
        result.append(rec)

    return sorted(result, key=lambda r: r["code"])


# ═════════════════════════════════════════════════════════════════════════════
# F0Group builder
# ═════════════════════════════════════════════════════════════════════════════


def _build_f0_group(
    df: pd.DataFrame,
    rec: dict,
    f0_col: str,
    f1_col: str,
    desc_col: str,
) -> F0Group:
    sections = _parse_f1(df, rec["instances"], f0_col, f1_col, desc_col)
    return F0Group(
        code=rec["code"],
        description=rec["description"],
        instances=rec["instances"],
        count=rec["count"],
        f1_sections=sections,
    )


# ═════════════════════════════════════════════════════════════════════════════
# F1 parsing helpers
# ═════════════════════════════════════════════════════════════════════════════


def _is_l1_header(f1: str) -> bool:
    """
    True if F1 is an explicit section header:
    2-5 letters only, no digits (e.g. BFA, MQA, AHA).
    """
    return bool(re.match(r"^[A-Za-z]{2,5}$", f1.strip()))


# ═════════════════════════════════════════════════════════════════════════════
# F1 parsing — main function
# ═════════════════════════════════════════════════════════════════════════════


def _parse_f1(
    df: pd.DataFrame,
    f0_instances: list[str],
    f0_col: str,
    f1_col: str,
    desc_col: str,
) -> list[F1Section]:
    total = len(f0_instances)
    f0_set = set(f0_instances)

    rows = df[(df[f0_col].isin(f0_set)) & (df[f1_col] != "")]

    # ── Step 1: collect per-instance sections preserving Excel order ──────
    instance_sections: dict[str, OrderedDict] = {
        f0: OrderedDict() for f0 in f0_instances
    }

    for _, row in rows.iterrows():
        f0 = row[f0_col]
        f1 = row[f1_col]
        desc = row[desc_col]

        if f0 not in instance_sections:
            continue

        if _is_l1_header(f1):
            if f1 not in instance_sections[f0]:
                instance_sections[f0][f1] = {"desc": desc, "leaves": []}
        else:
            m = re.match(r"^([A-Za-z]+)", f1)
            prefix = m.group(1) if m else None
            if prefix and prefix in instance_sections[f0]:
                instance_sections[f0][prefix]["leaves"].append((f1, desc))
            # No header → skip silently

    # ── Step 2: collect unique sections, leaf coverage and order ──────────
    all_prefixes: OrderedDict[str, str] = OrderedDict()
    leaf_coverage: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    leaf_desc_map: dict[str, dict[str, str]] = defaultdict(dict)
    leaf_order: dict[str, list[str]] = defaultdict(list)

    for f0, sections in instance_sections.items():
        for prefix, data in sections.items():
            if prefix not in all_prefixes:
                all_prefixes[prefix] = data["desc"]
            for leaf_code, leaf_desc in data["leaves"]:
                leaf_coverage[prefix][leaf_code].add(f0)
                if leaf_code not in leaf_desc_map[prefix]:
                    leaf_desc_map[prefix][leaf_code] = leaf_desc
                if leaf_code not in leaf_order[prefix]:
                    leaf_order[prefix].append(leaf_code)

    # ── Step 3: group leaves by generalised description ───────────────────
    result: list[F1Section] = []

    for prefix, sec_desc in all_prefixes.items():
        section = F1Section(
            prefix=prefix,
            label=prefix,
            description=sec_desc,
            leaves=[],
        )

        # Group leaf codes by their generalised description (used as key only)
        groups: OrderedDict[str, list[str]] = OrderedDict()

        for leaf_code in leaf_order[prefix]:
            raw_desc = leaf_desc_map[prefix].get(leaf_code, "")
            gen_key = _generalise_single_desc(raw_desc)
            if gen_key not in groups:
                groups[gen_key] = []
            groups[gen_key].append(leaf_code)

        # Build one F1Leaf per group
        for gen_key, codes in groups.items():
            codes_sorted = sorted(codes)

            # common/specific via intersection of f0 coverage
            f0s_min = set(f0_instances)
            for code in codes_sorted:
                f0s_min &= leaf_coverage[prefix].get(code, set())

            # Generalise code character-by-character
            gen_code = _generalise_code_from_list(codes_sorted)

            # Generalise description — only vary numbers that actually differ
            raw_descs = [leaf_desc_map[prefix].get(c, "") for c in codes_sorted]
            gen_desc = _generalise_desc_from_list(raw_descs)

            section.leaves.append(
                F1Leaf(
                    code=gen_code,
                    description=gen_desc,
                    is_common=len(f0s_min) == total,
                    count=len(codes_sorted),
                    present_in=sorted(f0s_min),
                )
            )

        if section.leaves:
            result.append(section)

    return result
