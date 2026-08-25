# hubspot-wefact

One-way synchronisation of invoices from **HubSpot** to **WeFact**.

The tool reads invoices from the HubSpot CRM, creates the matching debtor,
products and invoice in WeFact, downloads the resulting invoice PDF and attaches
that PDF back to the HubSpot company as a note. A small SQLite database keeps
track of what has already been done, so a run is safe to repeat.

## How it works

```
HubSpot invoices ──> state db check ──> WeFact (debtor, products, invoice)
                                             │
                                             └──> invoice PDF ──> HubSpot note on company
```

For each invoice on a page of HubSpot results:

1. **Look up progress.** `src/modules/state/db.py` reports what was already synced for this
   invoice number: `unknown`, `open` or `paid`.
2. **Decide the action** (`_determine_action` in `src/main.py`):

   | HubSpot status | state db | action                                                |
   | -------------- | -------- | ----------------------------------------------------- |
   | `open`         | unknown  | create the invoice in WeFact                          |
   | `paid`         | unknown  | create the invoice in WeFact first                    |
   | `paid`         | open     | fetch the paid invoice and its PDF                    |
   | same as db     | –        | already processed, skip                               |
   | anything else  | –        | not synced, skip (e.g. `draft`, `voided`)             |

3. **Fetch the details.** The associated company, contact and line items are
   read from HubSpot. A line item without an `hs_sku` cannot be mapped onto a
   WeFact product, so the invoice is skipped and a high-priority HubSpot **task**
   is created on the company instead.
4. **Push to WeFact.** The debtor is created or updated, then every product, then
   the invoice itself (created directly as *Verzonden*).
5. **Attach the PDF.** The invoice PDF is uploaded to the HubSpot `/invoices`
   folder and linked to the company through a note.
6. **Record it.** The invoice number and status are written to the state
   database, so the next run skips this phase.

Paging repeats this until HubSpot stops returning a cursor.

## Layout

| Path                       | What lives there                                                                  |
| -------------------------- | --------------------------------------------------------------------------------- |
| `src/main.py`              | The sync run: paging, per-invoice decisions, PDF attachment                        |
| `src/modules/hubspot_client/` | HubSpot client, invoice/company/contact/line-item reads, notes, tasks, file upload |
| `src/modules/wefact_client/`  | WeFact v2 client (`api.py`) and the request builders per object type               |
| `src/modules/models/`      | Pydantic models shared by both sides: `Invoice`, `LineItem`, `Company`, `Contact`  |
| `src/modules/state/db.py`  | The SQLite progress database                                                      |
| `service/`                 | Optional FastAPI service that triggers a sync run in a Docker container            |
| `web/`                     | Static trigger page plus the Caddy config that fronts the service                 |
| `tests/`                   | pytest suite; no network calls, everything is faked                                |
| `docs/`                    | Field mapping (`field-mapping.md`) and process diagrams                            |

`src/` is the import root: `src/main.py` imports the packages under
`src/modules/` as `modules.<package>`, and pytest picks the same root up via
`pythonpath` in `pyproject.toml`.

A note on naming: the models keep the Dutch HubSpot property names
(`betreft`, `relatienummer`, `kostenplaats`, `korting`) because they map
one-to-one onto WeFact custom fields. `docs/field-mapping.md` has the full
HubSpot → model → WeFact table.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker, only for the container and service routes

## Configuration

Both credentials are read from the environment at import time; the process fails
immediately if either is missing.

| Variable               | Required | Purpose                                                                 |
| ---------------------- | -------- | ----------------------------------------------------------------------- |
| `HUBSPOT_ACCESS_TOKEN` | yes      | HubSpot private-app token                                               |
| `WEFACT_API_KEY`       | yes      | WeFact v2 API key                                                       |
| `APPDATA`              | no       | Directory for the state database and downloaded PDFs                    |
| `API_KEY`              | service  | Bearer token callers must present to the FastAPI service                |
| `HOST_DATA_PATH`       | service  | Host directory the service mounts into the container at `/app/data`     |

`src/main.py` calls `load_dotenv()`, so a local `.env` file works too. `.env` and
`.envrc` are gitignored — **keep them out of version control, they hold live
credentials.**

Where state and PDFs land:

- state database: `$APPDATA/hubspot-wefact.db`, falling back to `./data/hubspot-wefact.db`
- downloaded PDFs: `$APPDATA/WeFactInvoices/`, falling back to `$HOME/WeFactInvoices/` or `/tmp/WeFactInvoices/`

## Running it

### Locally

```bash
uv sync
export HUBSPOT_ACCESS_TOKEN=...
export WEFACT_API_KEY=...
uv run python src/main.py
```

### With Docker

The Makefile builds only when a `.py` file or the Dockerfile changed, tracked
through a `.docker-build-stamp` file.

```bash
make build   # build the image
make run     # build if needed, then run one sync
make clean   # drop the build stamp to force a rebuild
```

`make run` passes `HUBSPOT_ACCESS_TOKEN` and `WEFACT_API_KEY` through from your
shell and mounts `./data` at `/app/data` so the state database persists.

### As a service

`service/main.py` exposes a small FastAPI app that starts the sync image as a
background Docker container. Every endpoint requires an
`Authorization: Bearer $API_KEY` header.

```bash
uv sync --group dev
uv run uvicorn main:app --app-dir service
```

`fastapi` lives in the `dev` group while `uvicorn` and `docker` are regular
dependencies, so a bare `uv sync` is not enough to run the service — use
`--group dev` as above.

| Endpoint             | Method | Description                                                     |
| -------------------- | ------ | --------------------------------------------------------------- |
| `/tasks`             | POST   | Queue a sync run; returns `202` with a `task_id`                 |
| `/tasks/{task_id}`   | GET    | Status of that run, plus exit code and container logs when done  |

Task state is held in memory, so it is lost when the service restarts.
`web/index.html` is a minimal page that calls these endpoints, and
`web/Caddyfile` serves it while proxying `/tasks*` to the service on port 8000.

## Tests

```bash
uv run pytest
```

The suite is offline: `tests/conftest.py` sets dummy credentials so modules that
read secrets at import time can be imported, and HubSpot and WeFact are faked
with `MagicMock` and `SimpleNamespace`. Covered areas are the status/action
decision table, the state database, HubSpot property mapping and type coercion,
the WeFact payload builders, and the model validation rules.
