# Read Path Degraded Status Contract

S3 조치 상태는 추정 지표가 아니라 Valkey 원본에서 읽는다.

```http
GET /api/admin/read-path-degraded?broadcast_id=bc_1042
X-Admin-Key: <READ_PATH_DEGRADED_ADMIN_KEY>
```

```json
{
  "broadcast_id": "bc_1042",
  "read_path_degraded_active": true
}
```

`read_path_degraded_active`는 `cfg:read_path_degraded:{broadcast_id}` 키의 존재
여부다. 인증은 상태 변경 POST와 같은 `X-Admin-Key`를 쓴다. 이 값은 방송별
제어 상태이므로 service 단위 Warm 지표나 Datadog gauge로 추정하지 않는다.
검증 단계가 조치 후 이 GET을 다시 호출해 Warm·Hot 지표와 같은 검증 번들에
결합한다.
