#!/bin/bash
# Skill: check-python-syntax
# Desc: Checks all python files for syntax errors using flake8 or python -m py_compile

echo "--- Verificando sintaxe Python no Optimizer ---"
OUTPUT=$(find optimizer/src -name "*.py" -exec python3 -m py_compile {} + 2>&1)
STATUS=$?
FILTERED_OUTPUT=$(printf "%s\n" "$OUTPUT" | grep -v "recompiling")

if [ -n "$FILTERED_OUTPUT" ]; then
    printf "%s\n" "$FILTERED_OUTPUT"
fi

if [ $STATUS -eq 0 ]; then
    echo "✅ Nenhuma falha de sintaxe encontrada."
else
    echo "❌ Falhas de sintaxe detectadas acima."
fi
