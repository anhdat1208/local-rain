param(
  [double]$Lat = 10.7626,
  [double]$Lng = 106.6602
)

$t0 = Get-Date
$near = Invoke-RestMethod "http://localhost:8000/api/nearest-rain?lat=$Lat&lng=$Lng&lang=vi"
$nearMs = [int]((Get-Date) - $t0).TotalMilliseconds

$t1 = Get-Date
$vec = Invoke-RestMethod "http://localhost:8000/api/rain-vectors?lat=$Lat&lng=$Lng&radius_km=100&limit=10"
$vecMs = [int]((Get-Date) - $t1).TotalMilliseconds

"nearest-rain ($nearMs ms):"
"  distance=$($near.distance)m dir=$($near.direction) motion=$($near.motionDirection) speed=$($near.speedKmh)km/h approaching=$($near.approaching) eta=$($near.eta)min"
"  explanation: $($near.explanation)"
"rain-vectors ($vecMs ms): $($vec.vectors.Count) vectors"
$vec.vectors | Select-Object -First 5 | ForEach-Object {
  "  $($_.direction) $($_.speedKmh)km/h dbz=$($_.dbz)"
}
