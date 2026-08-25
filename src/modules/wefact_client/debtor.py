from modules.models.company import Company


def debtor_data_id(code):
    """Return the WeFact payload that identifies a debtor by its debtor code."""
    return {"DebtorCode": code}


def debtor_data_id_from_model(company: Company):
    """Identify the WeFact debtor for a company; relatienummer is the debtor code."""
    return debtor_data_id(company.relatienummer)


def debtor_data_add(code, name, address, zipcode, city, email):
    """Return the WeFact payload for creating a debtor."""
    return {"DebtorCode": code, "CompanyName": name, "Address": address, "ZipCode": zipcode, "City": city,
            "EmailAddress": email}


def debtor_data_edit(id, code, name, address, zipcode, city, email):
    """Return the WeFact payload for updating the debtor with the given Identifier."""
    return {"Identifier": id, "DebtorCode": code, "CompanyName": name, "Address": address, "ZipCode": zipcode,
            "City": city, "EmailAddress": email}

def debtor_data_add_from_model(company: Company):
    """Build the create-debtor payload from a Company.

    The debtor email is taken from mailadres_factuur, the invoicing address, not
    from the company's generic email field.
    """
    return debtor_data_add(company.relatienummer, company.name, company.address, company.zip, company.city,
                           company.mailadres_factuur)

def debtor_data_edit_from_model(id: int, company: Company):
    """Build the update-debtor payload from a Company for an existing Identifier."""
    return debtor_data_edit(id, company.relatienummer, company.name, company.address, company.zip, company.city,
                           company.mailadres_factuur)
