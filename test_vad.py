from google.genai import types
cfg = types.LiveConnectConfig(
    realtime_input_config=types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(
            disabled=True
            # or silence_duration_ms=2000
        )
    )
)
print(cfg)
