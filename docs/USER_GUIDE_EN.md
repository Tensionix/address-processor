# User Guide

[Русский](USER_GUIDE_RU.md) · [Overview](README_EN.md) · [OKTMO](OKTMO_EN.md) · [Reference](REFERENCE_EN.md)

**Contents**

- [1. Launching](#1-launching)
- [2. Workspace Folders](#2-workspace-folders)
- [3. How a Command Screen Works](#3-how-a-command-screen-works)
- [4. Commands](#4-commands)
- [5. Maintenance](#5-maintenance)
- [6. Working Order](#6-working-order)

The program is driven from a window: commands are chosen with the mouse, columns
are given as Excel letters, and results go into a separate folder. Ordinary work
requires no editing of configuration files.

---

## 1. Launching

`launcher_gui.cmd` in the project root is the usual way. `Start.exe` does the
same.

The launcher resolves the portable environment (`runtime\pythonw.exe`, then
`runtime\python.exe`, then `runtime\python\`, then a system `py -3.12`) and
raises a local interface on `127.0.0.1:8080` in its own window.

If no window appears, set `AUDION_GUI_CONSOLE=1` and run the launcher again — it
opens in a console with error messages. Details are in [Install](INSTALL_EN.md).

---

## 2. Workspace Folders

The project works with six managed folders:

| Folder | Contents |
| --- | --- |
| `input` | Source files |
| `output` | Results |
| `report` | JSON run reports |
| `logs` | Operation logs |
| `workspace` | Intermediate files |
| `release` | Result archives |

**Source** and **Target** at the top of the window override `input` and `output`
for the current work. A path can be pinned, which keeps it first in the recent
list. Path history is stored in `config/path_history.json`.

Source buttons:

| Button | Action |
| --- | --- |
| Add file… / Add files… | Copy selected files into the sources |
| Add folder… | Copy the contents of a folder |
| List | Show the current source set |
| Delete | Remove one selected entry |
| Reset | Return to the initial state |

Spaces and Cyrillic in paths are supported.

**Check the list before starting.** A command works with the prepared set of
files, not with the last one you opened in Explorer.

---

## 3. How a Command Screen Works

Every command opens the same way.

* At the top: the command name, a **BACK** button, and a **RUN** button.
* **Parameters** — fields grouped by meaning: Files, Sheets, Columns, Data rows,
  Territory, Options.
* **Advanced** — fields rarely needed: data folder paths, manual overrides.
* **Operation log** — live output. The operation can be cancelled.
* **Artifacts** — three buttons after completion: **OUTPUT**, **REPORT**,
  **AUDIT**. They open the result folder, the report, and the audit sheet.

One operation runs at a time. While a run is in progress, a second command will
not start.

Operations that change the managed workspace ask for confirmation and show what
exactly will be affected.

### How Columns Are Given

As Excel letters: `B`, `C,D`, `AC`. Ordinal numbers are accepted too. Several
columns are separated by commas.

An empty field almost always means automatic mode, not an error.

Where a "header" field exists, the column can be chosen by its name from the
first row of the workbook. An explicitly given letter takes priority over the
header.

---

## 4. Commands

The tiles appear in this order:

1. OKTMO / project keys
2. Address collection
3. Address alignment
4. Reference normalization
5. Reference processing
6. Compare two tables
7. Move columns by address
8. Convert DOC/XLS
9. Diagnostics

### 4.1. OKTMO / Project Keys

The territory registry, search keys, and pins. The registry **is downloaded by a
button** and refreshed by the same button; the cache is rebuilt immediately.

This has its own document: [OKTMO and project keys](OKTMO_EN.md).

### 4.2. Address Collection

Recursively collects address-like values from XLSX, DOCX, ODT, TXT, CSV, MD, and
searchable PDF, merges slot evidence, drops incomplete rows, and writes an
address workbook.

Use it when you need an inventory first and matching later.

**Action**

* *New table* — collect everything from scratch.
* *Append to ready* — add collected addresses to an existing workbook.

**Sources.** "Source folder" is an optional folder for recursive scanning; empty
means the whole source folder. "Address table folder" is where the ready address
workbook lives.

**Columns.** "Address columns" restrict parsing to specific XLSX columns; empty
means all cells and all supported files are scanned. For append mode, set
"Collected address column" and "Target address column".

**Slots.** "Enabled slots" decide what the address line is built from; "Slot
order" decides in which order. The "Address line" field shows a read-only example
of the resulting address. The full slot list is in the
[Reference](REFERENCE_EN.md#slots).

**Options**

| Option | What it does |
| --- | --- |
| Skip microdistrict when street exists | The microdistrict column stays, but is excluded from the generated line |
| Clean new workbook | A compact workbook with the address column only, instead of the full one |
| Merge duplicates | Merge candidates with the same address key and vote for the best slot values |
| Sanitize incomplete | Drop street without house, house without street, subject-only addresses, and table dumps |
| Write rejected sheet | Rejected candidates go to a separate sheet for audit |
| Enable OKTMO keys | Resolve territory from the registry and the project keys |

**Benchmark workbook.** An optional workbook with a control address column. It is
used only to score collection quality and writes
`report/address_collection_benchmark.json`.

**Result.** An `AddressCollection_*.xlsx` workbook in the result folder and
`report/address_collection_summary.json`.

After collecting, check for: empty values, duplicates, cells holding several
addresses, and rows that name an organisation but no address.

### 4.3. Address Alignment

The main mode. Compares address columns against a reference column, rearranges
rows so that addresses line up with their pairs, and moves linked columns along
with them.

**Columns.** "GT column" is the reference address column (empty = auto-detect).
"Address columns" is what to align; empty means take up to five columns to the
right of the reference.

**Alignment mode**

* *Fast alignment* — matching with no extra processing.
* *Alignment + normalization* — the same search, then a cleanup of the aligned
  address columns in the result.

**Linked columns.** Values from linked columns travel together with the matched
address, so the data does not drift apart.

| Mode | Behaviour |
| --- | --- |
| Auto | The legacy automatic behaviour |
| None | Pure address-column alignment |
| Left of each address | Columns to the left of each address |
| Right of each address | Columns to the right of each address |
| Between GT and address | One distant column carries the whole block between the reference and itself |

The last mode answers a common case: the reference in `A`, the address in `AC`,
and all of `B:AB` has to move with `AC`.

The "Satellite columns" field sets links explicitly when automatic detection does
not fit.

**Alignment and normalization.** "Normalize before match" is a slower mode using
the common normalizer. "Collect before match" builds clean candidates from the
selected columns before searching; "Whole document" widens collection to the
entire workbook. "Default city" names the city removed from component keys during
normalized matching.

**Result.** A result workbook in the output folder and
`report/address_alignment_summary.json`. The log carries a per-column summary:
how many rows each pass matched, how many were precise, how many relaxed, and how
many stayed without a pair.

**How to read the summary.** A high share of relaxed hits is a reason to look
with your eyes. An exact match is evidence; an approximate one is a hypothesis.

### 4.4. Reference Normalization

Builds an address reference directory from sources, or brings an existing one to
the current slot set.

**Action**

* *Generate* — a new directory from the sources.
* *Update* — extend an existing one.
* *Clean slots* — rebuild obsolete slot columns.

**Options.** "Merge old duplicates" merges records with the same slot key.
"Rebuild old slots" drops obsolete slot columns and writes only the current set.
"Clean new workbook" produces a compact result.

**Result.** An `AddressReference_*.xlsx` workbook and
`report/reference_normalization_summary.json`.

Normalization is deterministic: whitespace, punctuation, case, abbreviations, and
component extraction are handled the same way from run to run. The original
address value is preserved in the result.

The normalized key helps the search but does not replace the evidential source
string.

### 4.5. Reference Processing

Sorts the reference address column by slots, or decomposes it into separate slot
columns.

**Action**: *Sort*, *Deconstruct*, *Sort + deconstruct*.

**Slot order** here defines the sorting hierarchy: which slot dominates first.
Region → municipality → settlement → street → building, or any other order.

**Slot column headers**: *Full* (`Postal_Index`, `Municipality`) or *Short*
(`Index`, `Municipality`).

**Remove source address column** — during deconstruction the slot columns are
inserted and the original is dropped.

**Result.** The processed workbook and
`report/reference_processing_summary.json`.

### 4.6. Compare Two Tables

Takes any two workbooks, assembles an address from the given columns of each,
normalizes, matches buildings, and creates a **separate** comparison workbook.
Both source workbooks stay untouched.

**Fields.** Table A and Table B, their sheets, the address columns of each, and
the first data row of each. B's address columns may sit in different positions
than A's.

**Sort addresses within groups.** Off — matched rows come first in A order, then
"only A" and "only B". On — rows are sorted by address inside each group.

**Result.** A comparison workbook with a status column and colour fill:

| Status | Colour | Meaning |
| --- | --- | --- |
| matched | green | Exactly one pair |
| matched: N rows of B | yellow | Several candidates, needs review |
| only A | A tint | No pair |
| only B | B tint | No pair |

Plus `report/table_comparison_summary.json`.

### 4.7. Move Columns by Address

Finds identical buildings in two workbooks and moves selected columns from the
source into the corresponding rows of the primary workbook.

Copying rows will not do here: the row order of the primary workbook, its
formulas, formatting, and sheets must stay in place. So the transfer runs through
Excel, and the primary workbook is first copied into the result folder — the copy
is what gets edited.

**Fields.** The primary and source workbooks, sheets (several may be checked in
the source), the address columns of both, "Fields to append" — what exactly to
carry over, the first data rows, and the output header row.

**Result.** A copy of the primary workbook with the added columns, a status
column, and an `AUDIT_ADDRESS_JOIN` audit sheet. Statuses: matched, matched with
a count, not found. The report is
`report/safe_table_join_summary.json`.

Check that one address did not resolve into several incompatible rows: that is
exactly what the status with a count shows.

### 4.8. Convert DOC/XLS

Turns legacy `.doc` and `.xls` in the sources into `.docx` and `.xlsx`.

**Overwrite existing** — when off, existing `.docx`/`.xlsx` files are preserved.
Same-name PDF/TXT/CSV/MD duplicates left over from earlier conversions are
removed as well.

The report is `report/legacy_office_conversion_report.json`.

### 4.9. Diagnostics

Two sub-commands.

**Run parser diagnostic** extracts parsed address components from the sources and
shows them as they are. This is how to understand why a particular address found
no pair: you see what the program took for a street, what for a building, and
what for a territory.

**Validate input** lists the supported spreadsheets in the source folder and
clears Office temporary files along the way.

---

## 5. Maintenance

| Command | What it does |
| --- | --- |
| Clear I/O | Delete the contents of the managed `input` and `output`; the folders remain |
| Remove empty rows | Create copies of results without rows that are empty across all columns |
| Package output as ZIP | Build `release/address_aligner_output.zip` from the result folder |

Empty-row removal only drops rows that are empty entirely. A row with data in a
single column counts as non-empty and stays.

Folder cleanup is confined to the managed workspace:
`cleanup_managed_workspace_only` and `never_delete_original_inputs` in
`config/project.yaml` keep it from reaching outside the project or deleting
originals.

---

## 6. Working Order

A typical run:

1. **Prepare the OKTMO registry** if you work with territorial context — once by
   button, then again as new snapshots are published.
2. **Collect the keys** of the region or municipality on the OKTMO screen.
3. **Place the sources**, check the list.
4. **Run on a small controlled set** — a dozen rows whose answer you know in
   advance.
5. **Run the full pass.**
6. **Read the report.** A run is not finished until the report has been reviewed.
7. **Open the result** in a spreadsheet application and verify headers, row order,
   formulas, and carried-over values.

### What to Look at in the Report

* empty addresses;
* duplicate keys;
* one-to-many and many-to-one links;
* building and block contradictions;
* low-confidence candidates;
* rows that did not reach the result;
* unexpected changes in row count.

### Rules for Safe Work

**Preserve the original row order** when it matters to the systems that will
consume the result.

**Do not hand-normalize part of a set** before an automatic comparison: half the
rows brought to one form and half raw gives a worse result than an entirely raw
set.

**Keep the sources and the report** until the result is accepted.

**After changing matching logic**, run a small controlled set first.

On failure, keep the log and the report. Fix the source, the reference, or the
column mapping — and repeat the run only after you understand the cause.
