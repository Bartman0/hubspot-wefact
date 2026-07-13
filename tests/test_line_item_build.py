from hubspot_api.api import _build_line_item


def base_args(**overrides):
    """Mimic the raw HubSpot line-item property dict (all values are strings)."""
    args = {
        "hs_sku": "SKU1",
        "name": "Widget",
        "quantity": "2",
        "amount": "20",
        "price": "10",
        "btw": "0.21",
        "discount": "0",
        "hs_discount_percentage": "0",
    }
    args.update(overrides)
    return args


def test_string_values_are_coerced_to_numbers():
    item = _build_line_item(base_args())
    assert item.quantity == 2 and isinstance(item.quantity, int)
    assert item.amount == 20.0
    assert item.price == 10.0


def test_btw_is_scaled_to_a_percentage():
    item = _build_line_item(base_args(btw="0.21"))
    assert item.btw == 21.0


def test_btw_none_or_empty_defaults_to_zero():
    assert _build_line_item(base_args(btw=None)).btw == 0.0
    assert _build_line_item(base_args(btw="")).btw == 0.0


def test_discount_amount_is_converted_to_line_percentage():
    # 5 discount on subtotal 2 x 10 = 20 -> 25% off
    item = _build_line_item(base_args(discount="5", hs_discount_percentage="0"))
    assert item.hs_discount_percentage == 25.0


def test_zero_discount_keeps_supplied_percentage():
    item = _build_line_item(base_args(discount="0", hs_discount_percentage="7.5"))
    assert item.hs_discount_percentage == 7.5
    assert item.discount == 0.0


def test_discount_percentage_is_rounded_to_two_decimals():
    # 1 discount on 3 x 7 = 21 -> 4.7619... -> 4.76
    item = _build_line_item(base_args(quantity="3", price="7", amount="21", discount="1"))
    assert item.hs_discount_percentage == 4.76
