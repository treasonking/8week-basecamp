# Mini Detector (OpenSearch AD → Slack)

수집된 로그인 실패 로그(`logs-*`)를 OpenSearch Anomaly Detection(AD)로 분석하고,
이상치(grade>0)를 Slack Incoming Webhook으로 알림하는 최소 파이프라인.

## 빠른 시작 (Windows PowerShell)
1. OpenSearch가 이미 떠 있다면 이 단계는 건너뜀. (선택)
   ```powershell
   docker compose up -d
