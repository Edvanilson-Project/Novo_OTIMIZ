import jwt
import time

payload = {
    "id": 15,          # might be id instead of sub
    "sub": 15,
    "email": "admin@otimiz.com",
    "companyId": 16,
    "role": "super_admin",
    "iat": int(time.time()),
    "exp": int(time.time()) + 86400
}
try:
    token1 = jwt.encode(payload, "your_jwt_secret_here_min_32_chars", algorithm="HS256")
    print(token1)
except Exception as e:
    pass
