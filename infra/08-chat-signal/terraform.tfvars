# Phase 4 Shadow Mode. Candidate까지만 만들며 Datadog·Dify·Bedrock은 호출하지 않는다.
enable_event_source = true

# 2026-08-25 운영 Incident handoff 승인. cutover 이전 Candidate는 전달하지 않는다.
chat_source_adapter_execution_enabled            = true
chat_source_adapter_event_source_enabled         = true
chat_source_adapter_operational_handoff_approved = true
chat_source_adapter_allowed_broadcast_ids        = []
chat_source_adapter_not_before_epoch             = 1787634074
