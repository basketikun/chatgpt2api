import asyncio
import logging
import httpx
from services.config import config
from utils.log import logger

def _captcha_solver_cfg() -> dict[str, str]:
    providers = config.data.get("providers") or {}
    flow = providers.get("flow") or {}
    return {
        "url": str(flow.get("captcha_solver_url") or "").rstrip("/"),
        "api_key": str(flow.get("captcha_solver_api_key") or ""),
    }

async def _warm_pass():
    """Run one warm pass over every enabled (provider, profile) pair."""
    cfg = _captcha_solver_cfg()
    url = cfg.get("url")
    api_key = cfg.get("api_key")
    if not url:
        return

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    providers = config.data.get("providers") or {}

    # Target configurations
    targets = [
        ("gemini_web", "gemini-web-default"),
        ("flow", "default"),
    ]

    # Warm ALL profiles per provider (wildcards expand to N) so every account
    # has an open tab on its target site. Without this, "Fast Failover" only
    # helps the first account — the others still cold-start (5-15s overhead).
    from services.providers.web_proxy import _expand_profiles
    plan: list[tuple[str, str]] = []
    for p_name, def_profile in targets:
        p_cfg = providers.get(p_name) or {}
        if p_cfg.get("enabled") is False:
            logger.info(f"web_prewarmer: skipping {p_name} (disabled in config)")
            continue
        # Per-provider prewarm opt-out — useful when a provider (e.g. gemini_web)
        # is currently being unlocked manually via noVNC and the warmup loop
        # would steal the lock from the human.
        if p_cfg.get("prewarm") is False:
            logger.info(f"web_prewarmer: skipping {p_name} (prewarm=false in config)")
            continue
        profile_str = str(p_cfg.get("profile") or def_profile)
        profiles = _expand_profiles(profile_str) or [def_profile]
        for profile in profiles:
            plan.append((p_name, profile))

    if not plan:
        return

    # Cap concurrency: too many simultaneous Chrome launches OOM the host.
    sem = asyncio.Semaphore(2)

    async def _warm_one(p_name: str, profile: str):
        async with sem:
            target_url = f"{url}/v1/session/{profile}/warmup?provider={p_name}"
            logger.info(f"web_prewarmer: warming {p_name}/{profile}")
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.get(target_url, headers=headers)
                if resp.status_code == 200:
                    logger.info(f"web_prewarmer: {p_name}/{profile} OK")
                else:
                    logger.warning(f"web_prewarmer: {p_name}/{profile} HTTP {resp.status_code}: {resp.text[:120]}")
            except Exception as e:
                logger.warning(f"web_prewarmer: {p_name}/{profile} failed: {e}")

    await asyncio.gather(*[_warm_one(p, prof) for p, prof in plan])
    logger.info(f"web_prewarmer: warm pass complete ({len(plan)} profiles)")

async def _prewarm_loop():
    """First warm pass after a 10s settle, then re-warm every 25 min so
    the captcha-solver idle-eviction (30 min) never sees a healthy
    warmed profile."""
    await asyncio.sleep(10)
    while True:
        try:
            await _warm_pass()
        except Exception as e:
            logger.warning(f"web_prewarmer: warm pass crashed: {e}")
        try:
            await asyncio.sleep(25 * 60)
        except asyncio.CancelledError:
            break


def start():
    asyncio.create_task(_prewarm_loop())
