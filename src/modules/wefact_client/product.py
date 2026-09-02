from modules.models.line_item import LineItem


def product_data_id(code):
    """Return the WeFact payload that identifies a product by its product code."""
    return {"ProductCode": code}


def product_data_id_from_model(line_item: LineItem):
    """Identify the WeFact product for a line item; the HubSpot SKU is the product code."""
    return product_data_id(line_item.hs_sku)


def product_data_add(code, name, key_phrase, price, cost_center):
    """Return the WeFact payload for creating a product."""
    return {
        "ProductCode": code,
        "ProductName": name,
        "ProductKeyPhrase": key_phrase,
        "PriceExcl": price,
        "AccountingCostCentre": cost_center,
    }


def product_data_edit(id, code, name, key_phrase, price, cost_center):
    """Return the WeFact payload for updating the product with the given Identifier."""
    return {
        "Identifier": id,
        "ProductCode": code,
        "ProductName": name,
        "ProductKeyPhrase": key_phrase,
        "PriceExcl": price,
        "AccountingCostCentre": cost_center,
    }


def product_data_add_from_model(line_item: LineItem):
    """Build the create-product payload from a line item.

    The line-item name doubles as the product key phrase, and kostenplaats
    becomes the WeFact accounting cost centre.
    """
    return product_data_add(
        line_item.hs_sku,
        line_item.name,
        line_item.name,
        line_item.price,
        line_item.kostenplaats,
    )


def product_data_edit_from_model(id, line_item: LineItem):
    """Build the update-product payload from a line item for an existing Identifier."""
    return product_data_edit(
        id,
        line_item.hs_sku,
        line_item.name,
        line_item.name,
        line_item.price,
        line_item.kostenplaats,
    )
