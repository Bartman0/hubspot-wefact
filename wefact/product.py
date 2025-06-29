def product_data_id(code):
    return {"ProductCode": code}


def product_data_add(code, name, key_phrase, price):
    return {"ProductCode": code, "ProductName": name, "ProductKeyPhrase": key_phrase, "PriceExcl": price}
