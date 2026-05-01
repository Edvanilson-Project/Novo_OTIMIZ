const jwt = require('jsonwebtoken');
const token = jwt.sign({ sub: 15, email: "admin@otimiz.com", companyId: 16, role: "admin" }, "fallback_dev_only", { expiresIn: '1d' });
console.log(token);
