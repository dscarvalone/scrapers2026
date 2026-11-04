from common.pdf_ocr import _num


def test_num_accepts_grouped_and_short_numbers():
    assert _num("25,564", "x") == 25564
    assert _num("799", "x") == 799
    assert _num("0", "x") == 0
    assert _num(",6,420", "x") == 6420  # stray leading comma from a leader dot


def test_num_rejects_misreads():
    for bad in ("", "2550211", "25,56", "1,2345"):
        try:
            _num(bad, "x")
        except RuntimeError:
            continue
        raise AssertionError(f"{bad!r} should be rejected")
