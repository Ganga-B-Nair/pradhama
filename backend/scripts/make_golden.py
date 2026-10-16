"""Build the synthetic golden evidence bundle (docs/HACKATHON_PLAN.md §9).

All names, numbers and accounts are fictional. Writes to golden/bundle/ (the
demo upload set) and golden/followup/ (the record that answers G-01/G-09 on
stage). The narration clip is made with Google TTS (needs internet once):

    python scripts/make_golden.py            # text, images, expected.json
    python scripts/make_golden.py --audio    # also narration_ml.mp3 (gTTS)
"""
import json
import os
import random
import sys
from fractions import Fraction

import piexif
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "golden"))
OUT = os.path.join(ROOT, "bundle")
FOLLOW = os.path.join(ROOT, "followup")

CALLER = "+91 98470 41207"
WHATSAPP = f"""[01/10/26 10:18] {CALLER}: Good morning madam, calling from bank KYC department.
[01/10/26 10:18] {CALLER}: Your KYC is pending. Account will be blocked today.
[01/10/26 10:19] Lakshmi: What should I do?
[01/10/26 10:20] {CALLER}: Open this link and update details: hxxp://kyc-update-help[.]in/verify
[01/10/26 10:27] Lakshmi: Opened the link. Now?
[01/10/26 10:29] {CALLER}: You will get an OTP. Tell me the number for verification.
[01/10/26 10:31] Lakshmi: 482913
[01/10/26 10:32] {CALLER}: Thank you madam. KYC updated.
[01/10/26 14:51] Lakshmi: Money has gone from my account!
[01/10/26 14:52] Lakshmi: Hello? Please reply
"""
BANK_SMS = """01-10-26 14:05 Dear Customer, A/c XX2290 debited by Rs.50,000.00 on 01Oct26, transfer to A/c XXXX4471 (IFSC HDFC0004471). -Bank
01-10-26 14:09 Dear Customer, A/c XX2290 debited by Rs.50,000.00 on 01Oct26, transfer to A/c XXXX4471 (IFSC HDFC0004471). -Bank
01-10-26 14:22 Dear Customer, A/c XX2290 debited by Rs.40,000.00 on 01Oct26, UPI/kychelp.desk@ybl Ref 627114. -Bank
01-10-26 14:40 Dear Customer, A/c XX2290 debited by Rs.20,000.00 on 01Oct26, IMPS to A/c XXXX9032. -Bank
01-10-26 14:41 Available balance in A/c XX2290 is Rs.12,310.55. -Bank
"""
CALL_LOG = f"""date,time,number,type,duration
2026-10-01,10:12,{CALLER},incoming,00:06:40
2026-10-01,14:55,{CALLER},outgoing,00:00:00
"""
FOLLOWUP_SMS = """02-10-26 16:40 Dear Customer, A/c XX2290 debited by Rs.25,000.00 on 02Oct26, UPI/arun.k.pay@okaxis Ref 731882. -Bank
"""
# Spoken narration, Malayalam (what the complainant says at the counter).
NARRATION_ML = [
    "ഒക്ടോബർ ഒന്നിന് രാവിലെ ബാങ്കിൽ നിന്നാണെന്ന് പറഞ്ഞ് ഒരാൾ എന്നെ വിളിച്ചു.",
    "എന്റെ കെ വൈ സി പുതുക്കണമെന്നും ഇല്ലെങ്കിൽ അക്കൗണ്ട് ബ്ലോക്ക് ആകുമെന്നും പറഞ്ഞു.",
    "അയാൾ വാട്ട്സ്ആപ്പിൽ ഒരു ലിങ്ക് അയച്ചു, ഞാൻ ഒ ടി പി പറഞ്ഞുകൊടുത്തു.",
    "അന്ന് ഉച്ചയ്ക്ക് ശേഷം എന്റെ അക്കൗണ്ടിൽ നിന്ന് പല തവണ പണം പോയി.",
    "ഒക്ടോബർ രണ്ടിന് അരുൺ എന്ന് പേരുള്ള ഒരാൾ വീണ്ടും വിളിച്ച് ഇരുപത്തയ്യായിരം രൂപ കൂടി അയയ്ക്കാൻ പറഞ്ഞു, ഞാൻ അയച്ചു.",
    "ആകെ ഒരു ലക്ഷത്തി എൺപത്തയ്യായിരം രൂപ നഷ്ടപ്പെട്ടു.",
]
NARRATION_EN = [
    "On 1 October in the morning, a man called me saying he was from the bank.",
    "He said my KYC had to be updated, or the account would be blocked.",
    "He sent a link on WhatsApp, and I told him the OTP.",
    "That afternoon, money was taken from my account several times.",
    "On 2 October a man named Arun called again and asked me to send Rs 25,000 more, and I sent it.",
    "In total I lost Rs 1,85,000.",
]


def font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def phone_screenshot(lines: list[str], w=540, h=960, seed=0) -> Image.Image:
    img = Image.new("RGB", (w, h), (236, 229, 221))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 80], fill=(7, 94, 84))
    d.text((24, 26), "Bank Alerts", fill="white", font=font(26))
    y = 120
    for line in lines:
        d.rounded_rectangle([20, y, w - 60, y + 120], radius=14, fill="white")
        words, row, rows = line.split(), "", []
        for wd in words:
            if len(row + wd) > 34:
                rows.append(row)
                row = ""
            row += wd + " "
        rows.append(row)
        for i, r in enumerate(rows[:4]):
            d.text((36, y + 12 + i * 26), r, fill=(30, 30, 30), font=font(19))
        y += 150
    rnd = random.Random(seed)
    for _ in range(4000):  # mild sensor-like noise so images aren't perfectly flat
        x, yy = rnd.randrange(w), rnd.randrange(h)
        px = img.getpixel((x, yy))
        img.putpixel((x, yy), tuple(max(0, min(255, c + rnd.randint(-6, 6))) for c in px))
    return img


def to_rational(x: float):
    f = Fraction(x).limit_denominator(10000)
    return (f.numerator, f.denominator)


def dms(v: float):
    deg = int(v)
    mins = int((v - deg) * 60)
    secs = (v - deg - mins / 60) * 3600
    return (to_rational(deg), to_rational(mins), to_rational(round(secs, 2)))


def main(with_audio: bool):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(FOLLOW, exist_ok=True)
    for name, text in (("whatsapp_chat_export.txt", WHATSAPP), ("bank_sms_alerts.txt", BANK_SMS), ("call_log.csv", CALL_LOG)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    with open(os.path.join(FOLLOW, "bank_sms_02oct.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(FOLLOWUP_SMS)

    # 4 near-duplicate screenshots of the debit SMS (dedup demo): re-saves and tiny crops.
    sms = [ln.split(" Dear Customer, ")[1] for ln in BANK_SMS.splitlines()[:4]]
    base = phone_screenshot(sms, seed=1)
    for i, (crop, q) in enumerate([(0, 92), (6, 88), (3, 90), (9, 85)], start=1):
        im = base.crop((0, crop, base.width, base.height - crop)).resize(base.size)
        im.save(os.path.join(OUT, f"screenshot_debit_0{i}.jpg"), quality=q)

    # payment receipt: an amount region pasted in after upscaling (resampling
    # leaves periodic traces) and an EXIF Software=Adobe Photoshop tag.
    rec = phone_screenshot(["Payment successful", "Paid to kychelp.desk@ybl", "UPI Ref 627114",
                            "01 Oct 2026, 14:22"], seed=2)
    patch = Image.new("RGB", (110, 34), "white")
    ImageDraw.Draw(patch).text((4, 4), "40,000", fill=(0, 120, 0), font=font(24))
    patch = patch.resize((330, 102), Image.BILINEAR).resize((233, 72), Image.BILINEAR)
    rec.paste(patch, (150, 700))
    ex = Image.Exif()
    ex[0x0131] = "Adobe Photoshop 25.0 (Windows)"
    ex[0x010F] = "Apple"
    ex[0x0110] = "iPhone 12"
    rec.save(os.path.join(OUT, "payment_receipt.png"), exif=ex.tobytes())

    # passbook photo with GPS (Kakkanad) and capture time.
    pb = Image.new("RGB", (1200, 900), (250, 248, 240))
    d = ImageDraw.Draw(pb)
    d.text((60, 50), "PASSBOOK  A/c XX2290", fill=(20, 20, 90), font=font(40))
    rows = ["01-10-26  TRF XXXX4471   50,000.00 Dr", "01-10-26  TRF XXXX4471   50,000.00 Dr",
            "01-10-26  UPI kychelp    40,000.00 Dr", "01-10-26  IMPS XXXX9032  20,000.00 Dr", "Balance          12,310.55"]
    for i, r in enumerate(rows):
        d.text((60, 160 + i * 70), r, fill=(30, 30, 30), font=font(34))
    pb = pb.filter(ImageFilter.GaussianBlur(0.8))
    exif = {"0th": {piexif.ImageIFD.Make: b"samsung", piexif.ImageIFD.Model: b"SM-A146B"},
            "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2026:10:03 11:42:10"},
            "GPS": {piexif.GPSIFD.GPSLatitudeRef: b"N", piexif.GPSIFD.GPSLatitude: dms(10.0159),
                    piexif.GPSIFD.GPSLongitudeRef: b"E", piexif.GPSIFD.GPSLongitude: dms(76.3419)}}
    pb.save(os.path.join(OUT, "photo_passbook.jpg"), quality=90, exif=piexif.dump(exif))

    expected = {
        "complainant": {"name": "Lakshmi Menon", "contact": "+91 94470 77812", "address": "Kakkanad, Ernakulam", "language": "Malayalam"},
        "narration_english": NARRATION_EN,
        "events": 11,
        "gaps_rules": sorted(["G-01", "G-02", "G-03", "G-05", "G-07", "G-07", "G-09"]),
        "bns_sections": ["BNS s.318(4)", "BNS s.319(2)", "IT Act s.66C", "IT Act s.66D"],
        "referrals_min": 1,
        "duplicates_grouped": 3,
        "metadata_conflicts": ["payment_receipt.png"],
        "after_followup_resolved_rules": ["G-01", "G-09"],
    }
    with open(os.path.join(ROOT, "expected.json"), "w", encoding="utf-8") as f:
        json.dump(expected, f, indent=2, ensure_ascii=False)

    if with_audio:
        from gtts import gTTS
        gTTS(" ".join(NARRATION_ML), lang="ml", slow=True).save(os.path.join(OUT, "narration_ml.mp3"))
    print("golden bundle written to", OUT)


if __name__ == "__main__":
    main("--audio" in sys.argv)
