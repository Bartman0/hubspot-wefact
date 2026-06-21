# Field mapping: HubSpot → model → WeFact

This document traces how data flows through the three layers of the integration:

**HubSpot property → Pydantic model field → WeFact API field**

## Overview diagram

```mermaid
flowchart LR
    %% ---------- Invoice ----------
    subgraph HS_INV["HubSpot · Invoice"]
        direction TB
        h_number["hs_number"]
        h_status["hs_invoice_status"]
        h_invdate["hs_invoice_date"]
        h_duedate["hs_due_date"]
        h_disc["hs_total_discount"]
        h_betreft["betreft_factuurniveau"]
        h_ref["referentie_wefact__factuur_"]
        h_org["organisatie__factuur_"]
        h_tav["ter_attentie_van__factuur_"]
        h_adres["adres__factuur_"]
        h_post["postcode__factuur_"]
        h_plaats["plaats__factuur_"]
        h_land["land__factuur_"]
        h_relnr["relatienummer_factuur"]
    end

    subgraph M_INV["Model · Invoice"]
        direction TB
        m_number["number"]
        m_status["status"]
        m_invdate["invoice_date"]
        m_duedate["due_date"]
        m_korting["korting"]
        m_betreft["betreft"]
        m_ref["referentie"]
        m_org["organisatie"]
        m_tav["ter_attentie_van"]
        m_adres["adres"]
        m_post["postcode"]
        m_plaats["plaats"]
        m_plaats_land["land"]
        m_relnr["relatienummer"]
    end

    subgraph WF_INV["WeFact · Invoice"]
        direction TB
        w_code["InvoiceCode"]
        w_date["Date"]
        w_term["Term (due - invoice)"]
        w_disc["Discount"]
        w_country["Country"]
        w_cf["CustomFields.*"]
    end

    h_number --> m_number --> w_code
    h_status --> m_status
    h_invdate --> m_invdate --> w_date
    h_duedate --> m_duedate --> w_term
    m_invdate --> w_term
    h_disc --> m_korting --> w_disc
    h_betreft --> m_betreft --> w_cf
    h_ref --> m_ref --> w_cf
    h_org --> m_org --> w_cf
    h_tav --> m_tav --> w_cf
    h_adres --> m_adres --> w_cf
    h_post --> m_post --> w_cf
    h_plaats --> m_plaats --> w_cf
    h_land --> m_plaats_land --> w_cf
    m_plaats_land --> w_country
    h_relnr --> m_relnr --> w_cf

    %% ---------- Company ----------
    subgraph HS_CO["HubSpot · Company"]
        direction TB
        c_relnr["relatie_nummer"]
        c_name["name"]
        c_addr["address"]
        c_zip["zip"]
        c_city["city"]
        c_mail["mailadres_factuur"]
    end

    subgraph M_CO["Model · Company"]
        direction TB
        mc_relnr["relatienummer"]
        mc_name["name"]
        mc_addr["address"]
        mc_zip["zip"]
        mc_city["city"]
        mc_mail["mailadres_factuur"]
    end

    subgraph WF_DEB["WeFact · Debtor"]
        direction TB
        d_code["DebtorCode"]
        d_name["CompanyName"]
        d_addr["Address"]
        d_zip["ZipCode"]
        d_city["City"]
        d_mail["EmailAddress"]
    end

    c_relnr --> mc_relnr --> d_code
    c_name --> mc_name --> d_name
    c_addr --> mc_addr --> d_addr
    c_zip --> mc_zip --> d_zip
    c_city --> mc_city --> d_city
    c_mail --> mc_mail --> d_mail
    mc_relnr -. "DebtorCode on invoice" .-> w_code

    %% ---------- Line item ----------
    subgraph HS_LI["HubSpot · Line item"]
        direction TB
        l_sku["hs_sku"]
        l_name["name"]
        l_price["price"]
        l_qty["quantity"]
        l_btw["btw"]
        l_discpct["hs_discount_percentage"]
        l_disc["discount"]
    end

    subgraph M_LI["Model · LineItem"]
        direction TB
        ml_sku["hs_sku"]
        ml_name["name"]
        ml_price["price"]
        ml_qty["quantity"]
        ml_btw["btw (x100)"]
        ml_discpct["hs_discount_percentage"]
        ml_disc["discount"]
    end

    subgraph WF_PROD["WeFact · Product"]
        direction TB
        p_code["ProductCode"]
        p_name["ProductName / KeyPhrase"]
        p_price["PriceExcl"]
    end

    subgraph WF_LINE["WeFact · Invoice line"]
        direction TB
        il_code["ProductCode"]
        il_num["Number"]
        il_tax["TaxPercentage"]
        il_disc["DiscountPercentage"]
    end

    l_sku --> ml_sku
    ml_sku --> p_code
    ml_sku --> il_code
    l_name --> ml_name --> p_name
    l_price --> ml_price --> p_price
    l_qty --> ml_qty --> il_num
    l_btw --> ml_btw --> il_tax
    l_discpct --> ml_discpct --> il_disc
    l_disc --> ml_disc -. "recomputes %" .-> ml_discpct

    %% Contact is fetched but never mapped to a WeFact object
```

> **Contact** (`lastname`, `factuur_toelichting`) is fetched but never mapped to any WeFact object, so it is omitted from the diagram.

## 1. Invoice

HubSpot invoice object (`get_invoices` / `hubspot_api/api.py:70`) → `Invoice` model
(`models/invoice.py`) → WeFact invoice (`invoice_data_from_model` / `wefact_api/invoice.py:41`).

| HubSpot property | `Invoice` field | WeFact field | Notes |
|---|---|---|---|
| `hs_number` | `number` | `InvoiceCode` | |
| `hs_invoice_status` | `status` | — | drives sync state (`state/db.py`), not sent; WeFact `Status` hardcoded to `Verzonden` |
| `hs_amount_billed` | `amount_billed` | — | fetched, not sent |
| `hs_invoice_date` | `invoice_date` | `Date` | |
| `hs_due_date` | `due_date` | — | combined with `invoice_date` → `Term` = `(due_date − invoice_date).days` |
| `hs_total_discount` | `korting` | `Discount` | |
| `betreft_factuurniveau` | `betreft` | `CustomFields.factuurbetreft` | |
| `referentie_wefact__factuur_` | `referentie` | `CustomFields.factuurreferentie` | |
| `organisatie__factuur_` | `organisatie` | `CustomFields.factuurorganisatie` | |
| `ter_attentie_van__factuur_` | `ter_attentie_van` | `CustomFields.factuurtav` | |
| `adres__factuur_` | `adres` | `CustomFields.factuuradres` | |
| `postcode__factuur_` | `postcode` | `CustomFields.factuurpostcode` | |
| `plaats__factuur_` | `plaats` | `CustomFields.factuurplaats` | |
| `land__factuur_` | `land` | `CustomFields.factuurland` **and** `Country` | only field mapping to two WeFact targets |
| `relatienummer_factuur` | `relatienummer` | `CustomFields.factuurrelatienummer` | informational only — does not set `DebtorCode` (intended) |
| `hs_balance_due`, `hs_discount_percentage` | — | — | requested in `properties` but never read into the model |

WeFact `DebtorCode` comes from `company.relatienummer` (`wefact_api/invoice.py:55`), not the invoice.

## 2. Company → Debtor

HubSpot company (`_fetch_company` / `hubspot_api/api.py:159`) → `Company` model
(`models/company.py`) → WeFact debtor (`wefact_api/debtor.py`).

| HubSpot property | `Company` field | WeFact field | Notes |
|---|---|---|---|
| `relatie_nummer` | `relatienummer` | `DebtorCode` | falls back to `company_id` if empty (`hubspot_api/api.py:170`) |
| `name` | `name` | `CompanyName` | |
| `address` | `address` | `Address` | |
| `zip` | `zip` | `ZipCode` | |
| `city` | `city` | `City` | |
| `mailadres_factuur` | `mailadres_factuur` | `EmailAddress` | |
| `email` | `email` | — | fetched, not sent |
| `land` | `land` | — | fetched, not sent to debtor |

## 3. Line item → Product + Invoice line

HubSpot line_item (`_fetch_line_items` / `hubspot_api/api.py:202`) → `LineItem` model
(`models/line_item.py`) → WeFact product (`wefact_api/product.py`) and invoice line
(`wefact_api/invoice.py:63`).

| HubSpot property | `LineItem` field | WeFact field | Notes |
|---|---|---|---|
| `hs_sku` | `hs_sku` | `ProductCode` (product + line) | required; line skipped if missing |
| `name` | `name` | `ProductName` **and** `ProductKeyPhrase` | |
| `price` | `price` | `PriceExcl` (product) | |
| `quantity` | `quantity` | `Number` (line) | cast to int |
| `btw` | `btw` | `TaxPercentage` (line) | multiplied ×100 in `_build_line_item` |
| `hs_discount_percentage` | `hs_discount_percentage` | `DiscountPercentage` (line) | recomputed from `discount` if a discount amount is present |
| `discount` | `discount` | — | only used to derive the percentage above |
| `amount` | `amount` | — | fetched, not sent |
| `voorraadnummer`, `kostenplaats`, `grootboek`, `gewicht`, `artikelsoort`, `artikelgroep`, `hs_tax_rate_group_id` | same names | — | in model but never sent to WeFact |

## 4. Contact

`Contact` (`_fetch_contact` / `hubspot_api/api.py:174`) is fetched (`lastname`,
`factuur_toelichting`) and returned from `get_invoice_details`, but is **never mapped to any
WeFact object** in the current code.
