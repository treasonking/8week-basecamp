$ES_URL = $env:ES_URL; if (-not $ES_URL) { $ES_URL = "http://127.0.0.1:9200" }
# 지난 분의 30초 지점으로 맞춰서 120건
$ts = (Get-Date).ToUniversalTime().AddSeconds(-70)
$tsStr = ('{0:yyyy-MM-ddTHH:mm}:30Z' -f $ts)

for ($i=1; $i -le 120; $i++) {
  $doc = @{
    '@timestamp' = $tsStr
    event = @{ category = 'authentication'; outcome = 'failure' }
    source = @{ ip = '127.0.0.1' }
    message = "burst $i"
  } | ConvertTo-Json -Compress
  Invoke-RestMethod -Method Post -Uri "$ES_URL/logs-manual/_doc" -ContentType 'application/json' -Body $doc | Out-Null
}
Invoke-RestMethod -Method Post -Uri "$ES_URL/logs-manual/_refresh" | Out-Null
"Injected 120 docs at $tsStr (UTC)"
