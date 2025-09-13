$ES_URL = $env:ES_URL; if (-not $ES_URL) { $ES_URL = "http://127.0.0.1:9200" }

$body = @{
  size = 1000
  sort = @(@{ data_end_time = @{ order = "asc" } })
  query = @{ bool = @{ filter = @(
    @{ range = @{ anomaly_grade = @{ gt = 0 } } }
    @{ range = @{ data_end_time = @{ gte = "now-24h" } } }
  ) } }
  _source = @("detector_id","detector_name","data_end_time","anomaly_grade","anomaly_score","feature_data")
} | ConvertTo-Json -Depth 10

$resp = Invoke-RestMethod -Method Post -Uri "$ES_URL/.opendistro-anomaly-results,.opendistro-anomaly-results-history-*/_search" -ContentType 'application/json' -Body $body
$rows = foreach ($h in $resp.hits.hits) {
  $e = $h._source
  $cnt = $e.feature_data[0].data; if (-not $cnt) { $cnt = $e.feature_data[0].feature_value }
  [pscustomobject]@{
    time_iso    = ([DateTimeOffset]::FromUnixTimeMilliseconds([int64]$e.data_end_time)).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ")
    detector_id = $e.detector_id
    grade       = $e.anomaly_grade
    score       = $e.anomaly_score
    count       = $cnt
  }
}
$rows | Export-Csv -Path ".\anomalies_last24h.csv" -NoTypeInformation -Encoding UTF8
"Exported $(($rows|Measure-Object).Count) rows to anomalies_last24h.csv"
