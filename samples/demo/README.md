# Demo evidence for evaluation

Three fictional cyber-fraud complaints, each with three files that TRACE reads. Upload all three files of a scenario to one case (Evidence tab), add a typed narration, and run Analysis. Jurisdiction Lookup picks up the PIN codes as soon as the IP trace report is uploaded.

| Scenario | Complainant | Files | What TRACE finds |
|---|---|---|---|
| KYC-update fraud (Kozhikode) | Anil Kumar | `kozhikode_whatsapp_chat.txt`, `kozhikode_bank_sms.txt`, `kozhikode_ip_trace.txt` | Phishing link, OTP request and OTP shared, 3 debits (₹49,999), PINs 673001 and 673004 |
| Part-time job / task fraud (Thrissur) | Meera Joseph | `thrissur_whatsapp_chat.txt`, `thrissur_bank_sms.txt`, `thrissur_ip_trace.txt` | Registration link, 2 UPI debits (₹40,000), a ₹500 bait credit, PINs 680001 and 680020 |
| Marketplace "army seller" fraud (Kannur) | Farhan Ali | `kannur_whatsapp_chat.txt`, `kannur_bank_sms.txt`, `kannur_ip_trace.txt` | Advance and full payment to the same UPI ID (₹38,000), PINs 670001 (Kannur) and 686001 (Kottayam, a second district) |

Formats:
- **Chats** are WhatsApp Android exports (`d/m/yy, h:mm am - Name: message`).
- **Bank alerts** are pasted SMS text in three common bank wordings.
- **IP trace reports** are a pipe-separated table: `IP Address | Date/Time (IST) | ISP | PIN Code | Area`, the same format as `samples/ip_trace_report_sample.pdf`.

All names, phone numbers, UPI IDs and links are made up, and links are defanged (`hxxp`, `[.]`). The IP addresses come from the documentation ranges (RFC 5737), so they can't identify anyone. The PIN codes are real Kerala PINs, so the lookup returns real stations.
