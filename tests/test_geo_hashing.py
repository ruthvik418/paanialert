from common.geo import centre, decode, encode, geohash6, neighbourhood
from common.hashing import normalise_number, phone_hash


def test_known_geohash():
    # Reference value from the standard geohash algorithm.
    assert encode(57.64911, 10.40744, 11) == "u4pruydqqvj"


def test_round_trip_lands_in_same_cell():
    cell = geohash6(22.7196, 75.8577)
    lat, lon = centre(cell)
    assert geohash6(lat, lon) == cell
    _, _, dlat, dlon = decode(cell)
    assert abs(lat - 22.7196) <= dlat and abs(lon - 75.8577) <= dlon


def test_neighbourhood_is_nine_distinct_cells_self_first():
    cell = geohash6(28.6139, 77.2090)
    cells = neighbourhood(cell)
    assert cells[0] == cell
    assert len(cells) == 9 and len(set(cells)) == 9


def test_number_normalising_and_hash_is_stable():
    assert normalise_number("whatsapp:+91 98765-43210") == "+919876543210"
    a = phone_hash("whatsapp:+919876543210", key="k")
    assert a == phone_hash("+91 98765 43210", key="k")
    assert a != phone_hash("+919876543210", key="other")
