from models.line_item import LineItem


def product_data_id(code):
    return {"ProductCode": code}


def product_data_id_from_model(line_item: LineItem):
    return product_data_id(line_item.hs_sku)


def product_data_add(code, name, key_phrase, price, cost_center):
    return {
        "ProductCode": code,
        "ProductName": name,
        "ProductKeyPhrase": key_phrase,
        "PriceExcl": price,
        "AccountingCostCentre": cost_center,
    }


def product_data_edit(id, code, name, key_phrase, price, cost_center):
    return {
        "Identifier": id,
        "ProductCode": code,
        "ProductName": name,
        "ProductKeyPhrase": key_phrase,
        "PriceExcl": price,
        "AccountingCostCentre": cost_center,
    }


def product_data_add_from_model(line_item: LineItem):
    return product_data_add(
        line_item.hs_sku,
        line_item.name,
        line_item.name,
        line_item.price,
        line_item.kostenplaats,
    )


def product_data_edit_from_model(id, line_item: LineItem):
    return product_data_edit(
        id,
        line_item.hs_sku,
        line_item.name,
        line_item.name,
        line_item.price,
        line_item.kostenplaats,
    )
