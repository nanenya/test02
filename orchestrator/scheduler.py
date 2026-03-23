#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/scheduler.py
"""APScheduler 기반 에이전트 스케줄러 싱글톤."""

import logging
from typing import Optional

import httpx

from . import graph_manager
from .constants import utcnow, DEFAULT_HOST, DEFAULT_PORT

logger = logging.getLogger(__name__)

_AGENT_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/agent/decide_and_act"


def _parse_cron(cron_expr: str) -> dict:
    """'분 시 일 월 요일' 형식의 cron 표현식을 APScheduler CronTrigger kwargs로 변환."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"cron 표현식은 5개 필드여야 합니다: '{cron_expr}'")
    minute, hour, day, month, day_of_week = parts
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": day_of_week,
    }


class AgentScheduler:
    """APScheduler AsyncIOScheduler 기반 스케줄러 싱글톤."""

    def __init__(self) -> None:
        self._scheduler = None
        self._running = False

    def _get_scheduler(self):
        if self._scheduler is None:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            self._scheduler = AsyncIOScheduler()
        return self._scheduler

    async def start(self) -> None:
        """DB에서 enabled 스케줄을 로드하여 APScheduler에 등록하고 시작."""
        if self._running:
            return
        scheduler = self._get_scheduler()
        tasks = graph_manager.list_scheduled_tasks()
        for task in tasks:
            if task.get("enabled"):
                self._register_job(scheduler, task)
        scheduler.start()
        self._running = True
        logger.info(f"[Scheduler] 시작 — {len([t for t in tasks if t.get('enabled')])}개 작업 등록")

    def stop(self) -> None:
        """스케줄러 종료."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("[Scheduler] 종료")

    def _register_job(self, scheduler, task: dict) -> None:
        """태스크 dict를 APScheduler 잡으로 등록."""
        try:
            from apscheduler.triggers.cron import CronTrigger
            cron_kwargs = _parse_cron(task["cron_expr"])
            trigger = CronTrigger(**cron_kwargs)
            job_id = f"task_{task['id']}"
            # 이미 등록된 잡이면 제거
            existing = scheduler.get_job(job_id)
            if existing:
                existing.remove()
            scheduler.add_job(
                self._run_task,
                trigger=trigger,
                args=[task["id"]],
                id=job_id,
                name=task["name"],
                replace_existing=True,
            )
        except Exception as e:
            logger.warning(f"[Scheduler] 잡 등록 실패 task_id={task['id']}: {e}")

    async def _run_task(self, task_id: int) -> None:
        """스케줄 태스크 실행 — httpx로 /agent/decide_and_act 호출."""
        task = graph_manager.get_scheduled_task(task_id)
        if not task:
            logger.warning(f"[Scheduler] task_id={task_id} 없음, 건너뜀")
            return

        logger.info(f"[Scheduler] 실행 시작: {task['name']} (id={task_id})")
        try:
            payload = {
                "user_input": task["query"],
                "conversation_id": task.get("convo_id") or f"sched_{task_id}",
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(_AGENT_URL, json=payload)
                resp.raise_for_status()
            logger.info(f"[Scheduler] 완료: {task['name']}")
        except Exception as e:
            logger.error(f"[Scheduler] 실패 task_id={task_id}: {e}")

        # 다음 실행 시간 계산
        next_run = ""
        try:
            scheduler = self._get_scheduler()
            job = scheduler.get_job(f"task_{task_id}")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
        except Exception:
            pass

        graph_manager.update_scheduled_task_run(task_id, next_run_at=next_run)

    def add_task(self, task: dict) -> None:
        """실행 중인 스케줄러에 새 태스크 등록."""
        if self._scheduler and self._running:
            self._register_job(self._scheduler, task)

    def remove_task(self, task_id: int) -> None:
        """실행 중인 스케줄러에서 태스크 제거."""
        if self._scheduler and self._running:
            job_id = f"task_{task_id}"
            job = self._scheduler.get_job(job_id)
            if job:
                job.remove()

    def list_tasks(self) -> list:
        """DB에서 스케줄 태스크 목록 반환."""
        return graph_manager.list_scheduled_tasks()


# 싱글톤 인스턴스
agent_scheduler = AgentScheduler()
