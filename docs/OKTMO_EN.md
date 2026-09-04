# OKTMO and Project Keys

[Русский](OKTMO_RU.md) · [User Guide](USER_GUIDE_EN.md) · [Reference](REFERENCE_EN.md)

**Contents**

- [The Screen](#the-screen)
- [The Registry: Download and Update](#the-registry-download-and-update)
- [Search Scope: Region and Municipality](#search-scope-region-and-municipality)
- [Search Keys](#search-keys)
- [Pins](#pins)
- [How OKTMO Is Used in Work](#how-oktmo-is-used-in-work)
- [When Something Goes Wrong](#when-something-goes-wrong)

OKTMO is the Russian Classifier of Municipal Territories. The program uses it as
the source of truth for which settlements exist inside a chosen region and
municipality, and what their official names are.

Without the registry, address parsing still works but loses territorial context:
region and municipality lists are empty, and similar names from different
districts are nothing apart. With the registry, matching narrows down to the
intended territory and the `OKTMO_Code` and `OKTMO_Name` slots are filled with
the code and the official name.

## The Screen

The **OKTMO / project keys** tile is first in the command list. It opens the
**Project OKTMO keys** screen directly, without an intermediate menu.

Two buttons sit at the top of the screen:

* **UPDATE OKTMO DATABASE** — download a fresh Rosstat registry.
* **RESET OKTMO KEYS** — clear the current search keys. Pins are preserved.

Below is the **Territory** block: region selector, municipality selector, the key
panel, settlement search, and the pin panel.

## The Registry: Download and Update

**The registry is downloaded by a button.** Nothing has to be copied by hand and
placed into a folder.

While the registry file is missing, a red strip sits under the region field:

> OKTMO registry was not found: data/rosstat/data-\*.csv. Region and municipality
> lists will be incomplete.

On the right of that same strip is the **DOWNLOAD OKTMO** button. It runs exactly
the same operation as **UPDATE OKTMO DATABASE** at the top of the screen. The
only difference is that the first appears when the registry is missing, while the
second is always available.

**Updating is the same button.** There is no separate "update" operation: the
first download and every later refresh are the same action. When Rosstat
publishes a new monthly snapshot, press **UPDATE OKTMO DATABASE** again.

Once the strip is replaced by the line `OKTMO registry: data-…-structure-….csv`,
the registry is in place.

### What Happens on Click

1. **The link is resolved.** By default the Rosstat dataset page
   `https://rosstat.gov.ru/opendata/7708234640-oktmo/` is opened, every link of
   the form `data-YYYYMMDDTHHMM-structure-YYYYMMDDTHHMM.csv` is collected, and the
   file with the highest timestamp is taken. If the URL field holds a direct
   `data-*.csv` link, the page is not parsed — the file is taken directly.
2. **The file is downloaded to a temporary** `data/rosstat/.<name>.<stamp>.tmp`
   in one-megabyte chunks. Every 10 MB a progress line is written to the log, and
   the operation can be cancelled mid-download.
3. **The payload is validated.** The file must not be empty, must not start with
   `<html`, and for small files the semicolon separator is checked. If an error
   page arrived instead of CSV, the update aborts and the old registry stays
   untouched.
4. **The file is put in place.** Only after validation is the temporary file
   moved into `data/rosstat/`.
5. **Old snapshots are removed.** Every previous `data-*.csv` in the folder is
   deleted — exactly one current file remains. What was removed goes into the
   report.
6. **Caches are dropped.** Parsed in-memory indexes and the disk cache file are
   discarded.
7. **The cache is rebuilt immediately.** Not on the next screen open, not on the
   first match — right away, within the same operation. The log shows a line like:

   ```text
   OKTMO cache ready: regions=…, index_keys=…, contexts=…, bytes=…
   ```

8. **A report is written** to `report/rosstat_oktmo_update_summary.json`: the
   requested and resolved URL, the file path, the downloaded size, removed
   snapshots, the list of available files, and the resulting current file.

When it finishes, the region and municipality lists in the window reflect the new
registry at once — the UI option caches are dropped together with the indexes.

### Where Things Live

| Path | What it is |
| --- | --- |
| `data/rosstat/data-*.csv` | The registry itself. Always exactly one file |
| `data/rosstat/oktmo_lookup_cache.json` | The parsed index for fast lookup |
| `report/rosstat_oktmo_update_summary.json` | Report of the last update |

The disk cache is keyed to the CSV path and modification time and to the cache
format version. A registry file replaced by hand invalidates the cache
automatically — the index is rebuilt on first use. There is no need to clean the
cache separately.

### Manual Settings

**The URL field.** The update operation accepts a different address: the dataset
page or a direct `data-*.csv` link. An empty value and the default value are
equivalent.

**Environment variables.** When the field is empty, the address comes from the
first variable that is set: `AUDION_ADDRESS_PROCESSOR_ROSSTAT_OKTMO_URL`,
`AUDION_ROSSTAT_OKTMO_URL`, `AAP_ROSSTAT_OKTMO_URL`.

**OKTMO data folder.** The advanced `OKTMO data folder` field moves the registry
elsewhere. Give the folder that *contains* `rosstat/`; naming `rosstat` itself
resolves to its parent. Empty means the project `data` folder.

## Search Scope: Region and Municipality

**OKTMO search region** is a dropdown built from the local registry snapshot. The
field is searchable: typed text filters the list.

**OKTMO municipality** is built inside the selected region. Changing the region
clears the selected municipality and rebuilds its list.

Three buttons sit to the right of each field:

| Button | Action |
| --- | --- |
| Pin | Move the value to the top of the list. Pressing it again on an already pinned value raises it further |
| Unpin | Remove the pin |
| Add | Add the selected region or municipality to the search key file |

Add on the municipality field contributes not only the municipality itself but
all of its settlements with every grammatical form of their names. This is the
main way to collect keys for a whole district.

## Search Keys

Keys are the list of names by which the program recognises "its own" territory in
raw address text. Names are stored in grammatical forms, because real tables
contain «Синегорск», «Синегорска», and «Синегорске» alike.

File: `config/oktmo_current_keys.txt`, one form per line.

The **Current keys** panel shows the counter, the file path, and the keys
themselves. The copy icon puts the whole list on the clipboard; the expand icon
opens it full screen.

Panel buttons:

| Button | Action |
| --- | --- |
| Open | Open the key file in an external editor |
| Save | Write the keys of the selected region and municipality to the file |
| Load | Re-read the file from disk |
| Clear | Empty the key file |

**RESET OKTMO KEYS** at the top of the screen does what Clear does, and in
addition resets the selected region, municipality, and settlement search fields.
Pins remain.

### Searching for Individual Settlements

When you need a few villages rather than a whole district:

1. Type the name into the search field and press **Find candidates**. The search
   runs inside the selected region when one is set.
2. Choose the row you need in **Exact OKTMO row**. Found variants with codes are
   shown in the preview field.
3. Press **Add found places** — the selected row with every form of its name goes
   into the current keys.

## Pins

A pin is a fixed region or municipality value that is always shown at the top of
the dropdown. Pins do not affect matching; they save time when you work with the
same territories repeatedly.

Files:

| Path | What it is |
| --- | --- |
| `config/oktmo_region_pins.json` | Pinned regions |
| `config/oktmo_municipality_pins.json` | Pinned municipalities |
| `config/oktmo_pins_bundle.json` | The combined set, updated automatically |

The **OKTMO pins** panel:

| Button | Action |
| --- | --- |
| Open pins | Open the pin file in an external editor |
| Export pins | Save a timestamped copy |
| Import pins | Load a pin set from a file |
| Clear OKTMO pins | Delete every pin |

Import and clear drop the list caches, so changes are visible immediately.

## How OKTMO Is Used in Work

The **Enable OKTMO keys** checkbox (`use_oktmo`) appears on the address
collection, address alignment, reference normalization, and reference processing
screens.

When it is on:

* address parsing looks for a match against the project keys and determines the
  territorial context: subject, municipality, settlement;
* the found context is written into the `OKTMO_Code` and `OKTMO_Name` slots;
* during matching, a pair with an incompatible territory code is discarded before
  similarity is even scored, while a territory match adds weight to the right
  candidate.

That is why "улица Ленина, 12" from two neighbouring districts does not collapse
into one row.

Without the registry the checkbox still works, but there is no context to take:
the OKTMO slots stay empty and the territorial check degenerates into comparing
text names.

## When Something Goes Wrong

**"Could not find a Rosstat OKTMO data-\*.csv link".** No suitable link was found
on the page — Rosstat changed the markup, or the page is unavailable. Open the
dataset in a browser, copy the direct `data-*.csv` link, and paste it into the
URL field.

**"Downloaded Rosstat OKTMO payload looks like HTML, not CSV".** A page arrived
instead of a file — usually a stub or a network error. The old registry is
unharmed; try again.

**Region lists are empty although the file is there.** Check that the file sits in
`data/rosstat/` and its name matches the `data-*.csv` pattern. If the folder is
overridden by the `OKTMO data folder` field, the registry is looked for there.

**The registry updated but the lists are stale.** This should not happen: the
cache is rebuilt within the same operation. If it does, delete
`data/rosstat/oktmo_lookup_cache.json` — it will be rebuilt.
