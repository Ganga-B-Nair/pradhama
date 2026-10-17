"""Write samples/ip_trace_report_sample.pdf: a sample IP trace report in the
format TRACE reads for Jurisdiction Lookup.

Format (one table, pipe-separated, text-based PDF — not a scan):

    IP Address | Date/Time (IST) | ISP | PIN Code | Area
    203.0.113.24 | 01-10-2026 10:20 | Example Telecom | 682304 | Maradu, Ernakulam

Any row with an IPv4/IPv6 address and a 6-digit PIN is read. The header row
names the columns; without one, TRACE still picks out the IP, PIN and time.

The IP addresses are from the documentation ranges (RFC 5737), so they
cannot identify anyone. The PIN codes are real Kerala PINs so the lookup
returns real stations.

    python scripts/make_ip_trace_sample.py
"""
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "samples", "ip_trace_report_sample.pdf")

LINES = [
    ("F2", 15, "IP ADDRESS TRACE REPORT (SAMPLE FORMAT)"),
    ("F1", 10, "Reply to police requisition under BNSS s.94 / IT Act s.79 - sample layout for TRACE"),
    ("F1", 10, "Requesting station: Cyber Police Station, Kochi City    Reference: requisition dated 05-10-2026"),
    ("F1", 10, "Responding intermediary: Example Telecom Ltd (sample)"),
    ("F1", 10, ""),
    ("F2", 10, "IP Address | Date/Time (IST) | ISP | PIN Code | Area"),
    ("F1", 10, "203.0.113.24 | 01-10-2026 10:20 | Example Telecom | 682304 | Maradu, Ernakulam"),
    ("F1", 10, "203.0.113.24 | 01-10-2026 14:22 | Example Telecom | 682304 | Maradu, Ernakulam"),
    ("F1", 10, "198.51.100.77 | 01-10-2026 14:40 | Sample Broadband | 682030 | Kakkanad, Ernakulam"),
    ("F1", 10, "192.0.2.150 | 02-10-2026 16:35 | Example Mobile | 695014 | Kazhakkoottam, Thiruvananthapuram"),
    ("F1", 10, ""),
    ("F1", 9, "Note: IP addresses in this sample are from documentation ranges (RFC 5737) and do not identify any person."),
]


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build() -> bytes:
    ops, y = ["BT"], 800
    for font, size, text in LINES:
        ops.append(f"/{font} {size} Tf 1 0 0 1 50 {y} Tm ({esc(text)}) Tj")
        y -= size + 10
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(build())
    print("wrote", os.path.abspath(OUT))
