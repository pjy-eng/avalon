# Avalon v15.2 Redis Strict Recovery

This build is based on v15 Castle UI and focuses on game-state durability.

## What changed
- Redis/Upstash persistence is now treated as a critical dependency for key game operations when configured.
- Key operations are rolled back if the new room state cannot be saved:
  - ready/unready
  - start game
  - select team
  - speaker/phase controls
  - team vote
  - mission vote
  - continue after mission result
  - assassination
  - kick player
  - reset room
- Redis client now supports reconnect/retry when the server closes the connection.
- Optional Upstash REST support added:
  - UPSTASH_REDIS_REST_URL
  - UPSTASH_REDIS_REST_TOKEN
- If Redis is configured but temporarily unreachable after a Render restart, the server refuses to create a blank replacement room. This prevents accidentally overwriting a live game with a new empty room.
- LiveKit token endpoint now pauses if room recovery is unavailable, instead of treating the player as missing.

## Environment variables
Required for voice:
- LIVEKIT_URL
- LIVEKIT_API_KEY
- LIVEKIT_API_SECRET

Required for durable room recovery:
- REDIS_URL

Recommended for stronger Upstash stability:
- UPSTASH_REDIS_REST_URL
- UPSTASH_REDIS_REST_TOKEN

If REST variables are present, REST is tried first. TCP REDIS_URL remains as fallback.

## Important
No free platform can prevent Render from restarting. This build makes recovery safer:
- If a critical step cannot be persisted, it will not take effect.
- The previous saved state remains recoverable.
- Players can retry once Redis is available again.
