# transit-parser

## Environment

Run Python through devenv and the locked uv environment:

```sh
devenv shell -- uv run --locked python <script> <mode>
```

The repository-root `.venv` is stale (it points at an old mise Python), so don't use it.

## Workflow

Modes for both scripts: `bart`, `dc-metro`, `link-light-rail`, `muni`, `nyc-subway`.

1. **Download:** `download_data.py <mode>` writes to `../transit-data/` (`original/` holds
   zstd-compressed downloads, `processed/` holds intermediate data). `nyc-subway` is slow,
   so run it in the background; it reuses turnstile files that were already downloaded.
2. **Upload:** sync `../transit-data/` to the Cloudflare R2 bucket through the `r2`
   rclone remote. Use `copy`, never `sync`, so nothing gets deleted from the bucket, and
   preview with `--dry-run` first:

   ```sh
   rclone copy ../transit-data r2:transit-data --checksum --exclude '*.tmp'
   ```

   The R2 token is scoped to the bucket, so `rclone lsd r2:` fails with 403. List
   `r2:transit-data` directly instead.
3. **Generate:** `generate_data.py <mode>` writes the chart data to
   `../transit-charts/data/`.

`../transit-data/` isn't a git repository. To see what a download changed, hash the files
before and after it.
