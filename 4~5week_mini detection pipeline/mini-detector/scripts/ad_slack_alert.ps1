#!/usr/bin/env bash
set -euo pipefail

ES_URL="${ES_URL:-http://127.0.0.1:9200}"
RES_ALL='.opendistro-anomaly-results,.opendistro-anomaly-results-history-*'
: "${SLACK_WEBHOOK_URL:?Set SLACK_WEBHOOK_URL first}"
STATE_FILE="${STATE_FILE:-/tmp/ad_last_ts}"
DET_IDS="${DET_IDS:-}"   # 예: DET_IDS="dBy7...,BBwQ..."

command -v jq >/dev/null || { echo "jq 미설치"; exit 1; }
command -v curl >/dev/null || { echo "curl 미설치"; exit 1; }

DEFAULT_SINCE_MS=$(( $(date -u -d '30 minutes ago' +%s) * 1000 ))
LAST_TS=$( [ -s "$STATE_FILE" ] && cat "$STATE_FILE" || echo "$DEFAULT_SINCE_MS" )
[ -f "$STATE_FILE" ] || echo "$LAST_TS" > "$STATE_FILE"

# ✅ jq로 안전하게 쿼리 생성 (DET_IDS 포함 여부에 따라 terms 추가)
Q=$(jq -n \
  --argjson last "$LAST_TS" \
  --arg det_ids "${DET_IDS}" '
  {
    size: 200, track_total_hits: true,
    sort: [{data_end_time:{order:"asc"}}],
    query: { bool: { filter: [
      {range:{anomaly_grade:{gt:0}}},
      {range:{data_end_time:{gt:$last}}}
    ]}},
    _source: ["detector_id","detector_name","data_end_time","anomaly_grade","anomaly_score","feature_data","entity"]
  }
  | if ($det_ids|length)>0 then
      .query.bool.filter += [{terms:{detector_id: ($det_ids|split(",")|map(select(length>0)))}}]
    else .
    end
')

TMP=$(mktemp)
# 검색 → Slack payload 변환 → 임시파일로 저장
set +e
RESP=$(curl -s -XPOST "$ES_URL/$RES_ALL/_search" \
  -H 'Content-Type: application/json' -d "$Q")
CURL_RC=$?
set -e

if [ $CURL_RC -ne 0 ]; then
  echo "Elasticsearch 요청 실패"; echo "$RESP"; exit 1
fi

# jq 실패 시 에러 표시
echo "$RESP" | jq -c '
  .hits.hits[]?._source as $e
  | {text:"🚨 OpenSearch AD Anomaly",
     attachments:[{fields:[
       {title:"detector_id", value:($e.detector_id // "-"), short:true},
       {title:"grade",       value:($e.anomaly_grade|tostring), short:true},
       {title:"score",       value:($e.anomaly_score|tostring), short:true},
       {title:"count",       value:(($e.feature_data[0].data // $e.feature_data[0].feature_value // "n/a")|tostring), short:true},
       {title:"time",        value:(($e.data_end_time/1000)|todate), short:true}
     ]}]}
' | tee "$TMP" >/dev/null

N=$(wc -l < "$TMP")
if [ "$N" -eq 0 ]; then
  echo "No new anomalies since $(date -u -d @$((LAST_TS/1000)))Z"
else
  while IFS= read -r payload; do
    curl -s -XPOST -H 'Content-type: application/json' \
      --data "$payload" "$SLACK_WEBHOOK_URL" >/dev/null
    ts=$(echo "$payload" | jq -r '.attachments[0].fields[] | select(.title=="time") | .value' \
         | xargs -I{} date -u -d "{}" +%s)
    echo $((ts*1000)) > "$STATE_FILE"
  done < "$TMP"
  echo "Sent $N Slack alerts. Updated $STATE_FILE."
fi
rm -f "$TMP"
