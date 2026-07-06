from aerosend_utils.bounce_classifier import classify


def test_user_unknown_is_hard():
    assert classify(550, "550 5.1.1 <a@b.com>: Recipient address rejected: User unknown") == "HARD"


def test_spamhaus_is_block():
    assert classify(554, "554 5.7.1 Service unavailable; Client host blocked using zen.spamhaus.org") == "BLOCK"


def test_mailbox_full_is_soft():
    assert classify(452, "452 4.2.2 Mailbox full") == "SOFT"
