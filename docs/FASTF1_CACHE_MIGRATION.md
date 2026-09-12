# FastF1 cache migration

Completed 2026-09-12. This byte copy preserves parser-cache paths only.

| Item | Value |
|---|---|
| Source root | `track-shift/data` |
| Destination root | `data/fastf1data` |
| Files | 782 `.ff1pkl` files |
| Bytes | 4,025,789,262 |
| Years | 2024: 120; 2025: 192; 2026: 470 |

The inventory lists destination-relative paths, byte sizes, and SHA-256 hashes.

## Scope and checks

- Copied only FastF1 parser-cache files from `data/{2024,2025,2026}`.
- Excluded the HTTP SQLite cache, generated parquet and CSV data, model outputs, and source code.
- Created each destination path only when absent; no cache entry was deserialized.
- Source and destination inventories each contained 782 normalized SHA-256 entries and compared equal.
- The destination contains no file type other than `.ff1pkl` below `data/fastf1data`.
- Independent verification confirmed equal path sets, bytes, and full SHA-256 values, with no extra files, symlinks, or hard links.

## Phase 1 boundary

This archive is a cache, not an admitted learning corpus. Filename-only inventory found no 2026 Bahrain directory. The six Bahrain test days remain an acquisition and audit requirement; cached race sessions do not replace them.

## Bahrain source resolution

FastF1 3.8.3 resolves two Bahrain preseason tests: 11-13 February and 18-20 February 2026. Phase 1 stores new public records only in `data/phase1_fastf1_cache` and immutable exports in `data/acquisition`; neither path is committed.

Each day remains downstream-blocked until its stream coverage and entry exclusions have been reviewed. The proposed training, selection and final-evaluation split remains inactive pending human approval.

## Handoff

No commit was created. Confirm the Bahrain public source, exact day labels, and the treatment of incomplete subject coverage before Phase 1 begins.

## Repeatable verification

```sh
find data/fastf1data -type f -name '*.ff1pkl' | wc -l
find data/fastf1data -type f ! -name '*.ff1pkl' -print
while IFS=$'\t' read -r path bytes hash; do
  test "$(stat -f '%z' "$path")" = "$bytes" || exit 1
  test "$(shasum -a 256 "$path" | awk '{print $1}')" = "$hash" || exit 1
done < docs/FASTF1_CACHE_INVENTORY.sha256
```
