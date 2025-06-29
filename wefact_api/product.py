from models.line_item import LineItem


def product_data_id(code):
    return {"ProductCode": code}


def product_data_id_from_model(line_item: LineItem):
    return product_data_id(line_item.hs_sku)


def product_data_add(code, name, key_phrase, price):
    return {"ProductCode": code, "ProductName": name, "ProductKeyPhrase": key_phrase, "PriceExcl": price}


def product_data_add_from_model(line_item: LineItem):
    return product_data_add(line_item.hs_sku, line_item.name, line_item.name, line_item.price)
