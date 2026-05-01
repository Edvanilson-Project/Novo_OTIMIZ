import jwt
import time
import sys

payload = {
    "sub": 15,
    "email": "admin@otimiz.com",
    "companyId": 16,
    "role": "super_admin",
    "iat": int(time.time()),
    "exp": int(time.time()) + 86400
}
token = jwt.encode(payload, "otimiz-dev-jwt-secret-change-in-production", algorithm="HS256")
print(token)
