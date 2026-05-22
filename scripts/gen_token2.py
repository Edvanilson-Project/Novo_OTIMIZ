"""
Gerador de JWT para desenvolvimento/testes.
Requer JWT_SECRET via variável de ambiente — nunca hardcoded.
"""
import jwt
import os
import sys
import time

secret = os.environ.get("JWT_SECRET")
if not secret:
    print("Erro: JWT_SECRET não definido. Execute:", file=sys.stderr)
    print("  export JWT_SECRET=<seu_segredo_de_producao>", file=sys.stderr)
    sys.exit(1)

payload = {
    "id": int(os.environ.get("USER_ID", "15")),
    "sub": int(os.environ.get("USER_ID", "15")),
    "email": os.environ.get("USER_EMAIL", "admin@otimiz.com"),
    "companyId": int(os.environ.get("COMPANY_ID", "16")),
    "role": os.environ.get("USER_ROLE", "super_admin"),
    "iat": int(time.time()),
    "exp": int(time.time()) + 86400,
}
token = jwt.encode(payload, secret, algorithm="HS256")
print(token)
