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


def test_stale_feed_threshold():
    from common.timing import stale_feed
    assert stale_feed(0, 20327)            # zero report vs SOS: stale
    assert not stale_feed(0, 0)            # nothing anywhere
    assert not stale_feed(0, None)         # no SOS row
    assert not stale_feed(47904, 47873)    # feed ahead of SOS
    assert not stale_feed(40000, 40900)    # one batch behind (<1,000)
    assert not stale_feed(400000, 415000)  # 15k behind but <5%
    assert stale_feed(10000, 12000)        # 2,000 and 17% behind
