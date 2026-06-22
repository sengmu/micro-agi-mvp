import itchat
import sys

def qr_callback(uuid, status, qrcode):
    print("Type of qrcode:", type(qrcode))
    if isinstance(qrcode, bytes):
        print("Length of qrcode bytes:", len(qrcode))
        print("First 20 bytes:", qrcode[:20])
    else:
        print("qrcode value:", qrcode)
    sys.exit(0)

try:
    itchat.auto_login(enableCmdQR=False, qrCallback=qr_callback)
except SystemExit:
    pass
except Exception as e:
    print("Error:", e)
