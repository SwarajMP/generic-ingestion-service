from app.connectors.extractor import dotted_get, extract_id, extract_records


def test_dotted_get_root():
    assert dotted_get({"a": 1}, "$") == {"a": 1}


def test_dotted_get_nested():
    assert dotted_get({"a": {"b": 5}}, "a.b") == 5


def test_dotted_get_missing_returns_default():
    assert dotted_get({"a": {}}, "a.b.c", default="x") == "x"


def test_dotted_get_list_index():
    assert dotted_get({"a": [10, 20, 30]}, "a.1") == 20


def test_extract_records_named_field():
    payload = {"results": [{"id": 1}, {"id": 2}]}
    assert extract_records(payload, "results") == [{"id": 1}, {"id": 2}]


def test_extract_records_root_array():
    payload = [{"id": 1}]
    assert extract_records(payload, "$") == [{"id": 1}]


def test_extract_records_missing_path_returns_empty():
    assert extract_records({"other": []}, "results") == []


def test_extract_records_single_object_is_wrapped():
    assert extract_records({"result": {"id": 1}}, "result") == [{"id": 1}]


def test_extract_id_uses_field():
    assert extract_id({"name": "bulbasaur"}, "name") == "bulbasaur"


def test_extract_id_falls_back_to_content_hash_when_field_missing():
    result = extract_id({"a": 1}, None)
    assert len(result) == 64  # sha256 hex digest


def test_extract_id_hash_is_order_independent():
    r1 = extract_id({"a": 1, "b": 2}, None)
    r2 = extract_id({"b": 2, "a": 1}, None)
    assert r1 == r2


def test_extract_id_falls_back_when_id_field_absent_from_record():
    # id_field configured but this particular record doesn't have it
    result = extract_id({"other": "x"}, "name")
    assert len(result) == 64
