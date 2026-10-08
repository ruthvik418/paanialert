from agent.fallback import detect_lang, extract, is_complaint
from agent.runner import _history, guard


def test_hinglish_complaint():
    f = extract("Nal ka paani peela aa raha hai, badboo hai, 2 din se")
    assert (f["colour"], f["smell"], f["since_days"], f["sick_count"]) == ("yellow", "sewage", 2, None)
    assert detect_lang("Nal ka paani peela aa raha hai") == "hinglish"


def test_negation_means_nobody_sick():
    assert extract("paani ganda hai par kisi ko dast nahi hai")["sick_count"] == 0
    assert extract("No one is sick but the water tastes salty since last week")["sick_count"] == 0


def test_devanagari_sick_with_symptoms():
    f = extract("मेरे बच्चे को उल्टी और दस्त हो रहे हैं, पानी से बदबू आती है")
    assert f["sick_count"] == 1 and f["smell"] == "sewage"
    assert set(f["symptoms"]) == {"vomiting", "diarrhoea"}
    assert detect_lang("पानी से बदबू") == "hi"


def test_greeting_is_not_a_complaint():
    assert not is_complaint(extract("hello"))
    assert not is_complaint(extract("I will check tomorrow"))  # "will" must not read as "ill"


def test_guard_removes_safe_claims():
    out = guard("Your water is safe to drink. Thanks for reporting!", "en")
    assert "safe to drink" not in out and "boil" in out


def test_history_alternates_and_drops_trailing_user():
    turns = [
        {"role": "assistant", "text": "orphan"},
        {"role": "user", "text": "a"}, {"role": "user", "text": "b"},
        {"role": "assistant", "text": "c"}, {"role": "user", "text": "d"},
    ]
    msgs = _history(turns)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"][0]["text"] == "a\nb"
