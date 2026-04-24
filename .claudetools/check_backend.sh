#!/bin/bash
# Skill: check-backend-types
# Desc: Runs tsc in the backend to catch type errors

echo "--- Verificando tipos TypeScript no Backend ---"
cd backend && npm run build

if [ $? -eq 0 ]; then
    echo "✅ Tipos TypeScript válidos."
else
    echo "❌ Erros de tipagem detectados."
fi
