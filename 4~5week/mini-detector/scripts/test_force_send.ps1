$ES_URL = $env:ES_URL; if (-not $ES_URL) { $ES_URL = "http://127.0.0.1:9200" }
$WEBHOOK = $env:SLACK_WEBHOOK_URL
if (-not $WEBHOOK) { Write-Error "SLACK_WEBHOOK_URL not set"; exit 1 }

$body = @{
  size = 3
  sort = @(@{ anomaly_grade = @{ order="desc" } }, @{ data_end_time = @{ order="desc" } })
  query = @{ range = @{ anomaly_grade = @{ gt = 0 } } }
  _source = @("detector_id","detector_name","data_end_time","anomaly_grade","anomaly_score","feature_data")
} | ConvertTo-Json -Depth 10

$resp = Invoke-RestMethod -Method Post -Uri "$ES_URL/.opendistro-anomaly-results,.opendistro-anomaly-results-history-*/_search" -ContentType 'application/json' -Body $body
$hits = $resp.hits.hits
foreach ($h in $hits) {
  $e = $h._source
  $cnt = $e.feature_data[0].data; if (-not $cnt) { $cnt = $e.feature_data[0].feature_value }
  $payload = @{
    text = "🚨 OpenSearch AD Anomaly"
    attachments = @(@{ fields = @(
      @{ title="detector_id"; value=$e.detector_id; short=$true },
      @{ title="grade"; value="$($e.anomaly_grade)"; short=$true },
      @{ title="score"; value="$($e.anomaly_score)"; short=$true },
      @{ title="count"; value=(if($cnt){"$cnt"}else{"n/a"}); short=$true },
      @{ title="time(ms)"; value="$($e.data_end_time)"; short=$true }
    )})
  } | ConvertTo-Json -Depth 10
  Invoke-RestMethod -Method Post -Uri $WEBHOOK -ContentType 'application/json' -Body $payload | Out-Null
}
"Force-sent $($hits.Count) messages to Slack."
