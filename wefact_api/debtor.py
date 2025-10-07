from models.company import Company


def debtor_data_id(code):
    return {"DebtorCode": code}


def debtor_data_id_from_model(company: Company):
    return debtor_data_id(company.relatienummer)


def debtor_data_add(code, name, address, zipcode, city, email):
    return {"DebtorCode": code, "CompanyName": name, "Address": address, "ZipCode": zipcode, "City": city,
            "EmailAddress": email}


def debtor_data_add_from_model(company: Company):
    return debtor_data_add(company.relatienummer, company.name, company.address, company.zip, company.city,
                           company.email)
