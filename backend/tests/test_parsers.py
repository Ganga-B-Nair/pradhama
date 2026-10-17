"""Parsers against the shapes real exports have. Strings are written inline to
mirror real formats; nothing here is case data."""
import io
import os
import zipfile

os.environ["MONGO_DB"] = "trace_test"

from app.agents import parsers  # noqa: E402

F = {"ev_id": "EV-001"}
Y = 2026


def at(e):
    return e["at"][:16]


def test_whatsapp_android_12h_multiline():
    lines = [
        "1/10/26, 10:18 am - +91 98470 41207: Calling from bank KYC department",
        "1/10/26, 10:20 am - +91 98470 41207: Open this link and update:",
        "hxxp://kyc-update-help[.]in/verify",
        "1/10/26, 10:31 am - Lakshmi Menon: 482913",
        "1/10/26, 2:51 pm - Lakshmi Menon: Money has gone from my account!",
        "1/10/26, 2:52 pm - Lakshmi Menon: <Media omitted>",
        "1/10/26, 2:53 pm - Messages and calls are end-to-end encrypted.",
    ]
    ev = parsers.parse_whatsapp(F, lines, "Lakshmi Menon", Y)
    assert [e["kinds"][0] for e in ev] == ["link", "otp", "money"]
    assert ev[0]["url"].startswith("hxxp://") and ev[0]["src"] == [{"f": "EV-001", "l": 2}]
    assert at(ev[2]) == "2026-10-01T14:51"  # pm read as 24-hour
    assert ev[1]["actor"] == "Complainant"


def test_whatsapp_iphone_format_with_direction_marks():
    lines = [
        "‎[01/10/26, 10:20:15 AM] +91 98470 41207: Open this link https://kyc.example/verify",
        "[01/10/26, 10:31:02 AM] Lakshmi: OTP is 482913",
    ]
    lines = [parsers.dates.clean(x) for x in lines]
    ev = parsers.parse_whatsapp(F, lines, "Lakshmi Menon", Y)
    assert [e["kinds"][0] for e in ev] == ["link", "otp"]
    assert at(ev[0]) == "2026-10-01T10:20"


def test_whatsapp_month_first_detected_from_file():
    lines = ["10/13/26, 9:05 PM - Ravi: I paid Rs 5,000", "10/14/26, 9:10 PM - Ravi: ok"]
    ev = parsers.parse_whatsapp(F, lines, "", Y)
    assert at(ev[0]) == "2026-10-13T21:05"


def test_chat_export_inside_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("WhatsApp Chat with Bank.txt", "1/10/26, 10:20 am - +91 98470 41207: link http://x.in\n")
        z.writestr("IMG-001.jpg", b"\xff\xd8\xff")
    assert "link http://x.in" in parsers._zip_chat(buf.getvalue())


def test_bank_sms_wordings():
    lines = [
        "Rs.5000.00 debited from a/c **1234 on 01-10-26 14:05 to VPA abc.pay@okicici (UPI Ref No 627114012345). Not you? Call 1800",
        "Your A/C XXXXX1234 Debited INR 20,000.00 on 01/10/26 -Transferred to Mr Arun. Avl Bal INR 12,310.55",
        "ICICI Bank Acct XX234 debited for Rs 40,000.00 on 01-Oct-26; kychelp.desk@ybl credited. UPI:627114012345",
        "123456 is your OTP for a transaction of Rs 9,999. Do not share it.",
        "Available balance in A/c XX2290 is Rs.12,310.55",
        "Dear Customer, Rs 2,500.00 credited to your a/c XX1234 on 03-10-26 by IMPS",
    ]
    ev = parsers.parse_alert_lines(F, lines, Y)
    assert [(e["amount"], e["kinds"][0]) for e in ev] == [(5000, "debit"), (20000, "debit"), (40000, "debit"), (2500, "credit")]
    assert ev[0]["upi"] == "abc.pay@okicici" and at(ev[0]) == "2026-10-01T14:05"
    assert ev[2]["upi"] == "kychelp.desk@ybl" and ev[2]["prec"] == "day"


def test_statement_rows_direction_from_balance():
    lines = [
        "Date Narration Chq/Ref Withdrawal Deposit Balance",
        "01/10/26 OPENING BALANCE 1,72,310.55",
        "01/10/26 UPI/kychelp.desk@ybl/627114 40,000.00 1,32,310.55",
        "01/10/26 IMPS/P2A/XXXX9032 20,000.00 1,12,310.55",
        "02/10/26 SALARY OCT 50,000.00 1,62,310.55",
    ]
    ev = parsers.parse_statement(F, lines, Y)
    assert [(e["amount"], e["kinds"][0]) for e in ev] == [(40000, "debit"), (20000, "debit"), (50000, "credit")]
    assert ev[0]["upi"] == "kychelp.desk@ybl"


def test_call_log_android_codes_epoch_and_seconds():
    lines = ["Number,Type,Date,Duration", "+919847041207,1,1790830320000,400", "+919847041207,2,1790846700000,0"]
    ev = parsers.parse_call_log(F, lines, Y)
    assert ev[0]["action"] == "Called the complainant (6 min 40 s)" and at(ev[0]) == "2026-10-01T10:22"
    assert ev[1]["actor"] == "Complainant" and "not answered" in ev[1]["action"]


def test_ocr_payment_receipt_text():
    lines = ["Payment successful", "", "₹40,000", "Paid to kychelp.desk@ybl", "UPI Ref 627114012345", "", "1 Oct 2026, 2:22 pm"]
    ev = parsers.parse_ocr(F, lines, Y)
    assert len(ev) == 1 and ev[0]["amount"] == 40000 and ev[0]["upi"] == "kychelp.desk@ybl"
    assert at(ev[0]) == "2026-10-01T14:22" and ev[0]["source_kinds"] == ["screenshot"]
