from SmartApi.smartConnect import SmartConnect

client_code = "A61056336"
mpin = "2611"  # your MPIN
totp = "956469"  # generate from authenticator app

obj = SmartConnect(api_key="6La9FonG")
session = obj.generateSessionByMobile(mpin=mpin, totp=totp)
print("✅ Login successful!")
print(session)
