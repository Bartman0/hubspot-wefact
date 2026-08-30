# hubspot-wefact

Synchronisation of invoices between **HubSpot** and **WeFact**. Invoices are
created in WeFact from HubSpot; payment status travels back the other way.

The tool reads invoices from the HubSpot CRM, creates the matching debtor,
products and invoice in WeFact, downloads the resulting invoice PDF and attaches
that PDF back to the HubSpot company as a note. For invoices it created on an
earlier run it asks WeFact whether they have been paid, and marks them paid in
HubSpot when they have. A small SQLite database keeps track of what has already
been done, so a run is safe to repeat.

## How it works

```
                        ┌─ never synced ──> WeFact (debtor, products, invoice)
                        │                            │
HubSpot invoices ──> state db check                  └──> invoice PDF ──> HubSpot note
                        │
                        └─ created earlier ──> paid in WeFact? ──> HubSpot invoice set to paid
```

For each invoice on a page of HubSpot results:

1. **Look up progress.** `src/modules/state/db.py` reports what was already
   synced for this invoice number: `unknown`, `open` or `paid`. An invoice keeps
   one row per status it passed through and the most advanced one wins, so
   `paid` beats `open` beats `unknown`.

2. **Decide the action** (`_determine_action` in `src/main.py`):

   | HubSpot status | state db | action                                                          |
   | -------------- | -------- | --------------------------------------------------------------- |
   | `open`         | unknown  | create it in WeFact                                              |
   | `paid`         | unknown  | create it in WeFact                                              |
   | `open`         | `open`   | ask WeFact whether it is paid and carry that back to HubSpot     |
   | `paid`         | `open`   | nothing at all — see [the paid/open no-op](#the-paidopen-no-op)  |
   | `paid`         | `paid`   | fully settled, skip                                              |
   | anything else  | –        | not synced, skip (e.g. `draft`, `voided`)                        |
   | `open`         | `paid`   | raises `ValueError` and aborts the run: an invoice cannot regress |

### Creating the invoice in WeFact

3. **Fetch the details.** The associated company, contact and line items are
   read from HubSpot. A line item without an `hs_sku` cannot be mapped onto a
   WeFact product, so the invoice is not sent and a high-priority HubSpot **task**
   is created on the company instead. If the invoice has no associated company
   the failure is only logged — a task needs a company to hang off.
4. **Push to WeFact.** The debtor is created or updated, then every product, then
   the invoice itself (created directly as *Verzonden*). If WeFact already has an
   invoice with this code nothing is created: the invoice is recorded as done and
   step 5 is skipped, so no PDF is attached.
5. **Attach the PDF.** The invoice PDF is downloaded from WeFact, uploaded to the
   HubSpot `/invoices` folder and linked to the company through a note.
6. **Record it.** The invoice number and its *current HubSpot status* are written
   to the state database. That status is not always `open`: an invoice that
   HubSpot already reported as `paid` the first time it was seen is recorded as
   `paid`, so it is skipped from then on and its WeFact counterpart stays
   *Verzonden*. When WeFact returns an error nothing is recorded and the next run
   retries the invoice.

### Carrying a payment back to HubSpot

An invoice the state database holds as `open` and HubSpot still reports as `open`
was created by an earlier run, so the sync asks WeFact for its current status.
When WeFact reports it as paid (status `4`, *Betaald*), `hs_invoice_status` on the
HubSpot invoice is set to `paid` and the invoice is recorded as `paid` in the
state database.

Anything else leaves HubSpot untouched: a failed lookup, a missing `Status` field
or a value that will not parse all count as not paid. The check fails closed,
because marking an unpaid invoice as paid corrupts the bookkeeping in HubSpot.

### The paid/open no-op

An invoice the state database holds as `open` while HubSpot already reports
`paid` — someone marked it paid in HubSpot by hand — is skipped entirely.
`_determine_action` returns `ACTION_PAID`, but `process_batch_of_invoices`
handles that case alongside `ACTION_SKIP`, so there is no WeFact lookup, no PDF
and no update. The invoice stays in this state on every subsequent run.

Paging repeats all of this until HubSpot stops returning a cursor.

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
uv sync
uv run uvicorn main:app --app-dir service
```

`fastapi`, `uvicorn` and `docker` are all regular dependencies, so a bare
`uv sync` is enough. The `dev` group holds only `pytest`.

`service/requirements.txt` is generated from the lock and is what
`service/Dockerfile` installs:

```bash
uv export --format requirements.txt --no-dev --no-hashes > service/requirements.txt
```

Regenerate it whenever a runtime dependency changes, or the service image will
be built against a stale set.

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
