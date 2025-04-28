def debtor_data_id(code):
    return {"DebtorCode": code}

def debtor_data_add(code, name, address, zipcode, city, email):
    return {"DebtorCode": code, "CompanyName": name, "Address": address, "ZipCode": zipcode, "City": city, "EmailAddress": email}
