def product_data_id(code):
    return {"ProductCode": code}

def product_data_add(code, name, keyphrase, price):
    return {"ProductCode": code, "ProductName": name, "ProductKeyPhrase": keyphrase, "PriceExcl": price}
