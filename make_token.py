import sys
import time

import jwt

SECRET = "zerogate-dev-secret-key-change-me-0123456789"
user, role = sys.argv[1], sys.argv[2]
print(jwt.encode({"sub": user, "role": role, "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256"))
