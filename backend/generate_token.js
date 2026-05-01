const jwt = require('jsonwebtoken');
const token = jwt.sign({ sub: 15, email: "admin@otimiz.com", companyId: 16, role: "admin" }, "mudar_para_um_segredo_forte_em_producao", { expiresIn: '1d' });
console.log(token);
