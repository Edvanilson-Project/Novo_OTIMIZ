#!/bin/bash
echo "🚀 INICIANDO AUDITORIA COMPLETA DO PROJETO OTIMIZ..."
./.claudetools/check_python.sh
./.claudetools/check_backend.sh
python3 .claudetools/analyze_logs.py optimizer/celery.log
echo "✅ Auditoria finalizada."
