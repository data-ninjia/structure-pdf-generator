# Input File Requirements

This document defines the required structure of the Excel input file
for the RDS-PP tree generator. Keeping the input consistent eliminates
the need to adjust the parser per project.

---

## 1. Required Columns

The file must contain at least these three columns
(exact name is flexible — the parser matches by keyword):

| Column | Matches keyword | Example values |
|---|---|---|
| **F0** | `F0 ANNN` or `F0` | `G001`, `T001`, `W101` |
| **F1** | `F1 AAANN` or `F1` | `AHA`, `AHA10`, `MDA11` |
| **Description** | `RDS-PP Code Description` or `Description` | `Busbar System 1, 33 kV` |

Extra columns (Plant, Reference, Comments, etc.) are ignored.

---

## 2. F0 Column Format

- Pattern: **1–3 letters + 3–4 digits**, e.g. `G001`, `T001`, `W101`, `B001`
- Multiple instances of the same system type (e.g. `G001`–`G028`)
  are grouped automatically by the parser
- The **F0 description** goes in a row where F0 has a value and F1 is empty:

```
F0      F1      Description
G001            Photovoltaic Field 1   ← F0 description row
G001    MQA     Photovoltaic generator system
G001    MQA01   Photovoltaic Generator System 1
```

---

## 3. F1 Column Format — Two Row Types

Every F1 entry is one of two types:

### 3a. Section header
- **Letters only, 2–5 characters, no digits**
- Marks the start of a new subsystem group
- Its description is the section title

```
F1      Description
AHA     Distribution for 30 kV ≤ Un < 45 kV   ← section header
AHA01   Busbar Coupling System 1, ...           ← leaf
AHA10   Busbar System 1, ...                    ← leaf
AHA11   Bay 1, Busbar System 1, ...             ← leaf
```

### 3b. Leaf code
- **2–3 letters + exactly 2 digits**, e.g. `AHA01`, `MDA11`, `MQA20`
- Must appear **after** its section header row
- The first row of each unique leaf code is its **node title**
- Subsequent rows with the same code are sub-items (shown as count)

---

## 4. Grouping Rules (handled automatically)

The parser groups leaf codes into ranges based on two conditions:

1. **Same description template** — descriptions must be identical
   after replacing all numbers with `#`
2. **Last digit varies** — codes differ only in their last character

```
AHA11 "Bay 1, Busbar System 1"  ┐
AHA12 "Bay 2, Busbar System 1"  ├─ grouped → =AHA11..19
...                              │
AHA19 "Bay 9, Busbar System 1"  ┘

MDA11 "Rotor blade system A"    ← NOT grouped (descriptions differ)
MDA12 "Rotor blade system B"    ← NOT grouped
MDA13 "Rotor blade system C"    ← NOT grouped
```

---

## 5. Common vs Exception

- A leaf (or range) is **common** if it appears in **all** F0 instances
- If it appears in only some instances → shown as **exception** (`*`)
  with a legend listing which instances have it (or don't,
  whichever list is shorter)

---

## 6. Description Guidelines

- Keep descriptions **concise** — they must fit inside a node box
- Recommended max length: **60 characters**
- Numbers used for **enumeration** (System 1, Bay 3) are fine —
  they drive the grouping logic
- Avoid using numbers for anything other than enumeration
  (e.g. voltage levels like `33 kV` are fine and kept as-is)

---

## 7. Minimal Valid Example

```
F0 ANNN | F1 AAANN | RDS-PP Code Description
G001    |          | Photovoltaic Field 1
G001    | MQA      | Photovoltaic generator system
G001    | MQA01    | Photovoltaic Generator System 1
G001    | MQA02    | Photovoltaic Generator System 2
G002    |          | Photovoltaic Field 2
G002    | MQA      | Photovoltaic generator system
G002    | MQA01    | Photovoltaic Generator System 1
G002    | MQA02    | Photovoltaic Generator System 2
```

Result: one F0 group `=G00n` (2 instances), one section `MQA`,
one common leaf `=MQA01..02`.
